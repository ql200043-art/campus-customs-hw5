"""Local FastAPI API. From backend/: uvicorn main:app --reload --port 8000."""
# Support the assignment's exact launch command as well as backend.main:app.
if __package__ in (None,''):
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import asyncio
import fcntl
import json
from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from backend.api_mcp import MCPGateway
from backend.api_models import HumanApproval, ResetRequest
from backend.audit import AuditTrail
from backend.models import Role
from backend.settings import ROOT
from backend.team import AgentTeam

ASSIGNMENT_TICKETS=(101,102,103)
FRONTEND_ORIGINS=['http://localhost:5173','http://127.0.0.1:5173']
LOCAL_ORIGINS=set(FRONTEND_ORIGINS+['http://localhost:8000','http://127.0.0.1:8000'])


def checked_control(result):
    if not result.get('ok'):
        status=404 if result.get('code')=='not_found' else 400 if result.get('code')=='invalid_approval' else 409
        raise HTTPException(status,detail={'status':'rejected','reason':result.get('reason','Control operation rejected')})
    return result


def ticket_view(record):
    raw=record['status']
    return {**record,'is_open':raw=='open','is_resolved':raw in ('closed','resolved'),
            'resolution_state':'resolved' if raw in ('closed','resolved') else 'open' if raw=='open' else 'unknown'}


def create_app(gateway=None,team_factory=None,audit=None):
    @asynccontextmanager
    async def lifespan(app):
        # No model construction, database writes, reset or ticket run at startup.
        yield

    app=FastAPI(title='Campus Customs API',version='0.7.0',lifespan=lifespan)
    app.state.gateway=gateway or MCPGateway()
    app.state.team_factory=team_factory or AgentTeam
    app.state.audit=audit or AuditTrail()
    app.state.operation_lock=asyncio.Lock()
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','testserver'])
    app.add_middleware(CORSMiddleware,allow_origins=FRONTEND_ORIGINS,allow_credentials=False,
                       allow_methods=['GET','POST'],allow_headers=['Content-Type'])

    @app.middleware('http')
    async def local_browser_writes(request:Request,call_next):
        # Local human API, not a login system. Prevent writes from arbitrary web origins.
        origin=request.headers.get('origin')
        if request.method=='POST' and origin is not None and origin not in LOCAL_ORIGINS:
            return JSONResponse(status_code=403,content={'detail':'Untrusted browser origin'})
        return await call_next(request)

    @app.exception_handler(Exception)
    async def unavailable(request,exc):
        return JSONResponse(status_code=503,content={'detail':'Operation unavailable; no fallback data. Inspect server logs or audit.'})

    async def require_ticket(ticket_id):
        if ticket_id not in ASSIGNMENT_TICKETS:raise HTTPException(404,'Unknown assignment ticket')
        result=await app.state.gateway.read('get_ticket',{'ticket_id':ticket_id})
        if not result.get('found'):raise HTTPException(404,'Ticket not found in working database')
        return result['record']

    def record(run_id,action,**kwargs):
        return app.state.audit.append(run_id=run_id,active_agent='Human/API',action=action,**kwargs)

    @app.get('/api/tickets')
    async def tickets():
        records=[ticket_view(await require_ticket(ticket_id)) for ticket_id in ASSIGNMENT_TICKETS]
        return {'tickets':records}

    @app.post('/api/tickets/{ticket_id}/run')
    async def run_ticket(ticket_id:int):
        async with app.state.operation_lock:
            ticket=await require_ticket(ticket_id)
            if ticket['status']!='open':raise HTTPException(409,'Ticket is not open')
            generation=checked_control(await app.state.gateway.control('control_get_state'))['generation']
            try:team=app.state.team_factory()
            except RuntimeError as exc:
                raise HTTPException(503,'Agent configuration unavailable; PORTKEY_API_KEY and Portkey routing are required') from exc
            request_id=str(uuid4())
            try:
                record(request_id,'ticket_run_requested',arguments={'ticket_id':ticket_id})
                result=await team.run(f'Investigate assignment ticket {ticket_id} only using get_ticket and MCP evidence. '
                    'Follow the existing role prompts. Return a bounded recommendation, drafts and payment proposals as needed. '
                    'Do not approve or execute payments, contact anyone, or claim ticket resolution.',Role.BOSS)
            finally:
                await team.close()
            pending=[];rejections=[]
            for candidate in result.get('payment_proposals',[]):
                queued=await app.state.gateway.control('control_stage_proposal',{
                    'candidate':candidate,'ticket_id':ticket_id,'run_id':result['run_id'],'generation':generation})
                if queued.get('ok'):
                    pending.append({**queued,'source_proposal_id':candidate['proposal_id'],'human_approval_required':True})
                else:rejections.append(queued.get('reason','Proposal rejected'))
            completion=None
            report=result.get('report') or {}
            if ticket_id==103 and report.get('disposition')=='declined_as_requested' and not pending and not rejections:
                record(result['run_id'],'operations_completion_requested',arguments={'ticket_id':103})
                completion=await app.state.gateway.control('control_complete_ticket103_operations',{
                    'run_id':result['run_id'],'generation':generation,'report':report,
                    'reports':result.get('completed_reports',[]),'evidence':result.get('mcp_evidence',{})})
                record(result['run_id'],'operations_completion_result',arguments={'ticket_id':103},
                       result_summary=completion.get('outcome',completion.get('reason','Completion rejected')))
            record(request_id,'ticket_run_complete',arguments={'ticket_id':ticket_id},
                   result_summary=f"agent_run={result['run_id']}; pending={len(pending)}; rejected={len(rejections)}",
                   human_approval_required=bool(pending),stop_reason=result.get('stop_reason') or result.get('report',{}).get('stop_reason'))
            return {'ticket_id':ticket_id,'run_id':result['run_id'],
                    'status':result.get('status') or result.get('report',{}).get('status','completed'),
                    'report':result.get('report'),'stop_reason':result.get('stop_reason'),
                    'pending_proposals':pending,'proposal_rejections':rejections,'business_records_changed':bool(completion and completion.get('ok') and completion.get('changed')),
                    'completion':completion}

    @app.post('/api/tickets/101/complete-operations')
    async def complete_operations(run_id: str):
        async with app.state.operation_lock:
            record(run_id,'operations_completion_requested',arguments={'ticket_id':101})
            result=checked_control(await app.state.gateway.control('control_complete_ticket101_operations',{'run_id':run_id}))
            record(run_id,'operations_completion_result',arguments={'ticket_id':101},
                   result_summary='Operations ticket closed; inventory unchanged; physical fulfillment unverified. Draft only; no payment or contact.')
            return result

    @app.get('/api/events')
    async def events(limit:int=Query(50,ge=1,le=200),run_id:str|None=None):
        path=app.state.audit.path
        if not path.exists():return {'events':[]}
        try:
            with path.open('r') as handle:
                fcntl.flock(handle,fcntl.LOCK_SH)
                entries=json.load(handle)
            if not isinstance(entries,list):raise ValueError('Invalid audit file')
        except (ValueError,OSError) as exc:raise HTTPException(503,'Audit trail unavailable; it was not reset') from exc
        fields={'timestamp','run_id','active_agent','action','delegation_target','mcp_tool','arguments',
                'result_summary','human_approval_required','stop_reason'}
        filtered=[entry for entry in entries if run_id is None or entry.get('run_id')==run_id]
        return {'events':[{k:v for k,v in entry.items() if k in fields} for entry in filtered[-limit:]],
                'order':'oldest_to_newest','total_matching':len(filtered)}

    @app.get('/api/proposals')
    async def proposals():
        return checked_control(await app.state.gateway.control('control_get_state'))

    @app.post('/api/approvals/{proposal_id}')
    async def approve(proposal_id:str,approval:HumanApproval):
        if approval.approved is not True:raise HTTPException(400,'Explicit approved=true is required; nothing executed')
        async with app.state.operation_lock:
            request_id=str(uuid4())
            # Audit before the action; a failed audit append prevents execution.
            record(request_id,'human_approval_requested',result_summary=f'proposal={proposal_id}; reviewer={approval.reviewer}',human_approval_required=True)
            result=await app.state.gateway.control('control_execute_payment',{'proposal_id':proposal_id,
                'approved':approval.approved,'reviewer':approval.reviewer,'next_due':approval.next_due})
            try:
                record(request_id,'human_approval_result',result_summary=f"proposal={proposal_id}; status={result.get('status','rejected')}; payment={result.get('payment_id')}",stop_reason=result.get('reason'))
            except (OSError,ValueError):
                # A committed payment must not be reported as rejected if audit storage fails.
                result['audit_warning']='JSON audit append failed; durable control receipt remains available'
            return checked_control(result)

    @app.get('/api/cash')
    async def cash():
        result=await app.state.gateway.read('list_cash_accounts',{'limit':25})
        checking=next((r for r in result['records'] if r['name']=='checking'),None)
        if checking is None:raise HTTPException(404,'Checking account not found in returned accounts')
        return {'account':checking['name'],'balance':checking['balance'],'date':checking['date']}

    @app.post('/api/reset')
    async def reset(body:ResetRequest):
        async with app.state.operation_lock:
            request_id=str(uuid4());record(request_id,'reset_requested')
            result=checked_control(await app.state.gateway.control('control_reset',body.model_dump()))
            try:record(request_id,'reset_complete',result_summary='Working copy restored; original and prior audit preserved')
            except (OSError,ValueError):result['audit_warning']='JSON audit append failed; reset was already completed'
            return result

    return app


app=create_app()
