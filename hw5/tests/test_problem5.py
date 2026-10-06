"""Offline unit/real-stdio smoke tests. No live inference or business DB writes."""
import asyncio
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import re
from uuid import uuid4
from unittest.mock import patch

import httpx
from backend.audit import AuditTrail
from backend.gateway import enforce_gateway
from backend.models import Role, AgentReport, Evidence, PaymentReviewRequest
from backend.runtime import RunState, RunStopped
from backend.settings import ROOT, TOOL_NAMES, MAX_MCP_CALLS, MAX_MODEL_REQUESTS
from backend.team import AgentTeam, PROMPTS, Dependencies, delegate_task
from backend.mcp_connection import new_client, call_shop
from backend.payment_boundary import execute_payment, PaymentExecutionDisabled
from mcp_server.server import mcp
from mcp_server import operations
from mcp_server.database import read_connection

BASELINE = '23686a90d698f7fa6f901a3f0a9774db9cbb31e13151c9e5717275f3321f360a'
SMOKE_BASELINE = '8d67d57bc5692e49d1926f861adb05719bce2af9b5dc8376ce306a113d19b0f2'


class SafetyTests(unittest.TestCase):
    def test_cash_rejection(self):
        self.assertEqual(operations.checked_balance(10,10),0)
        self.assertEqual(str(operations.checked_balance('10.00','0.01')), '9.99')
        for balance,amount in [(1,2),(-1,1),(3,0),(3,-1),('NaN',1),(3,'Infinity'),(3,'0.001')]:
            with self.assertRaises(ValueError): operations.checked_balance(balance,amount)

    def test_payment_execution_disabled_even_with_claimed_approval(self):
        with self.assertRaises(PaymentExecutionDisabled): execute_payment()
        with self.assertRaises(PaymentExecutionDisabled):
            execute_payment(PaymentReviewRequest(proposal_id='not-authority',run_id='validation'))
        with self.assertRaises(Exception):
            PaymentReviewRequest(proposal_id='x',run_id='v',status='approved')
        self.assertNotIn('execute_payment',TOOL_NAMES)

    def test_database_readonly_and_original_guard(self):
        from mcp_server import database
        with read_connection() as db:
            self.assertEqual(db.execute('PRAGMA query_only').fetchone()[0],1)
        with patch.object(database,'DATABASE_PATH',ROOT/'data/campus_customs.db'):
            with self.assertRaises(RuntimeError):
                with read_connection(): pass

    def test_proposal_refuses_insufficient_cash_duplicates_and_nonopen_invoice(self):
        # All changed rows in this test exist ONLY in a disposable in-memory fixture.
        with read_connection() as source:
            fixture=sqlite3.connect(':memory:'); fixture.row_factory=sqlite3.Row
            source.backup(fixture)
        @contextmanager
        def fixture_connection(): yield fixture
        with patch.object(operations,'read_connection',fixture_connection):
            fixture.execute('UPDATE cash_accounts SET balance=1')
            self.assertEqual(operations.prepare_payment('invoice',501,'checking')['status'],'blocked')
            fixture.execute('UPDATE cash_accounts SET balance=3400')
            fixture.execute("UPDATE invoices SET status='paid'")
            self.assertEqual(operations.prepare_payment('invoice',501,'checking')['status'],'blocked')
            fixture.execute("UPDATE invoices SET status='open'")
            fixture.execute("INSERT INTO payments VALUES(1,'invoice',501,840,'checking','2026-08-31','test fixture only')")
            self.assertEqual(operations.prepare_payment('invoice',501,'checking')['status'],'blocked')
            self.assertEqual(operations.prepare_payment('rent',999,'checking')['status'],'blocked')
            fixture.execute('DELETE FROM desk')
            self.assertEqual(operations.get_shop_context()['found'],False)
        fixture.close()

    def test_append_only_audit_across_instances(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'output') as temp:
            p=Path(temp)/'audit.json'; audit=AuditTrail(p)
            first=audit.append(run_id='one',active_agent='Inventory',action='validation',arguments={'sku':'X','secret':'redact'})
            prefix=p.read_bytes()[:p.read_bytes().rfind(b']')]
            AuditTrail(p).append(run_id='two',active_agent='Accounting',action='validation')
            self.assertTrue(p.read_bytes().startswith(prefix))
            events=json.loads(p.read_text());self.assertEqual(events[0],first);self.assertEqual(len(events),2)
            self.assertNotIn('secret',events[0]['arguments'])
            p.write_text('corrupt')
            with self.assertRaises(json.JSONDecodeError): audit.append(run_id='three',active_agent='Boss',action='validation')
            self.assertEqual(p.read_text(),'corrupt')

    def test_shared_limits_and_cycles(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'output') as temp:
            audit=AuditTrail(Path(temp)/'audit.json')
            for counter,limit in [('mcp_calls',24),('model_requests',16),('agent_runs',9),('delegations',8)]:
                state=RunState(audit=audit)
                for _ in range(limit):state.consume(counter,limit,Role.BOSS)
                with self.assertRaises(RunStopped):state.consume(counter,limit,Role.ACCOUNTING)
            state=RunState(audit=audit)
            self.assertFalse(state.delegate(Role.INVENTORY,Role.BOSS,(Role.BOSS,Role.INVENTORY)))
            self.assertFalse(state.stopped)
            state=RunState(audit=audit)
            with self.assertRaises(RunStopped):state.enter(Role.CUSTOMER_SERVICE,(Role.BOSS,Role.INVENTORY,Role.ACCOUNTING,Role.FACILITIES))

    def test_backend_has_no_database_or_direct_server_access(self):
        for p in (ROOT/'backend').glob('*.py'):
            text=p.read_text()
            self.assertNotIn('import sqlite3',text)
            self.assertNotIn('from mcp_server',text)
            self.assertNotIn('campus_customs_new.db',text)
        self.assertEqual(len(list((ROOT/'backend/prompts').glob('*.md'))),5)
        self.assertEqual(len({(ROOT/'backend/prompts'/p).read_text() for p in PROMPTS.values()}),5)

    def test_preserved_artifacts(self):
        for name in ('campus_customs.db','campus_customs_new.db'):
            self.assertEqual(hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest(),BASELINE)
        self.assertEqual(hashlib.sha256((ROOT/'output/mcp_smoke.json').read_bytes()).hexdigest(),SMOKE_BASELINE)
        self.assertIn('## Problem 6 —',(ROOT/'AI_prompts.md').read_text())  # Section persists after later work fills it.

    def test_documentation_matches_tools_and_limits(self):
        readme=(ROOT/'mcp_server/README.md').read_text()
        documented=set(re.findall(r'^\| `([a-z_]+)` \|',readme,re.M))
        self.assertEqual(documented,set(TOOL_NAMES))
        harness=(ROOT/'output/harness.md').read_text().split('## Problem 5 —',1)[1]
        for name in TOOL_NAMES:self.assertIn('`'+name+'`',harness)
        for role in Role:self.assertIn('| '+role.value+' |',harness)
        for table in ['desk','tickets','inventory','pricing','vendors','leases','cash_accounts','payments','invoices']:
            self.assertIn(table,harness)
        self.assertIn('24000',harness)
        self.assertIn('append-only',harness)
        self.assertIn('gpt-6-luna',harness)


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_agents_construct_and_twenty_directed_delegation_edges(self):
        with patch.dict(os.environ,{'PORTKEY_API_KEY':'offline-validation-placeholder'}):team=AgentTeam()
        try:
            self.assertEqual(set(team.agents),set(Role))
            self.assertEqual(team.model.model_name,'gpt-6-luna')
            self.assertEqual(str(team.model.client.base_url),'https://api.portkey.ai/v1/')
            self.assertEqual(team.model.client.max_retries,0)
            for source in Role:
                self.assertEqual(set(team.connectivity[source]),set(Role)-{source})
                tools=team.agents[source]._function_toolset.tools
                self.assertEqual(set(tools),{'query_shop','delegate_task'})
                self.assertTrue(tools['delegate_task'].sequential)
            # Exercise every routing edge without inference or database access.
            from types import SimpleNamespace
            from backend.models import DelegationRequest
            async def fake_run(role,task,state,client,stack):
                return AgentReport(role=role,status='blocked',summary='Offline routing validation only',stop_reason='validation')
            with patch.object(team,'_run',fake_run):
                for source in Role:
                    for target in team.connectivity[source]:
                        state=RunState(run_id='validation-routing-'+str(uuid4()))
                        ctx=SimpleNamespace(deps=Dependencies(team,state,None,source,(source,)))
                        result=await delegate_task(ctx,DelegationRequest(target=target,task='Offline routing validation only'))
                        self.assertEqual(result['role'],target.value)
        finally: await team.close()

    async def test_missing_key_fails_closed_and_gateway_rejects_bad_route(self):
        with patch.dict(os.environ,{'PORTKEY_API_KEY':''}):
            with self.assertRaises(RuntimeError): AgentTeam()
        await enforce_gateway(httpx.Request('POST','https://api.portkey.ai/v1/chat/completions',json={'model':'gpt-6-luna'}))
        with self.assertRaises(RuntimeError):
            await enforce_gateway(httpx.Request('POST','https://example.invalid/v1/chat/completions',json={'model':'gpt-6-luna'}))
        with self.assertRaises(RuntimeError):
            await enforce_gateway(httpx.Request('POST','https://api.portkey.ai/v1/chat/completions',json={'model':'INVALID_TEST_VALUE'}))

    async def test_all_twelve_tools_over_real_stdio_mcp(self):
        self.assertEqual({t.name for t in await mcp.list_tools()},set(TOOL_NAMES))
        for tool in await mcp.list_tools(): self.assertTrue(tool.annotations.readOnlyHint)
        probes={
            'lookup_inventory':{'sku':'CC-TEE-WHITE','size':'S'}, 'lookup_lease':{'lease_id':1},
            'lookup_pricing':{'sku':'CC-HOOD-NAVY'}, 'get_shop_context':{}, 'list_tickets':{},
            'get_ticket':{'ticket_id':101}, 'list_vendors':{}, 'get_vendor_status':{'vendor_id':1},
            'get_invoice':{'invoice_id':501},'list_cash_accounts':{},'list_payments':{},
            'prepare_payment':{'kind':'invoice','ref_id':501,'account':'checking'},
        }
        results={}; state=RunState(run_id='validation-mcp-'+str(uuid4()))
        async with new_client() as client:
            self.assertEqual({t.name for t in await client.list_tools()},set(TOOL_NAMES))
            for name,args in probes.items():results[name]=(await call_shop(client,state,Role.BOSS,name,args))['data']
            missing=await client.call_tool('lookup_inventory',{'sku':'NONEXISTENT_TEST_KEY','size':'S'})
            self.assertFalse(missing.structured_content['found'])
            capped=await client.call_tool('list_tickets',{'limit':1})
            self.assertTrue(capped.structured_content['truncated'])
        self.assertEqual(results['lookup_inventory']['record']['qty'],0)
        self.assertEqual(results['lookup_lease']['record']['monthly_rent'],2400)
        self.assertEqual(results['lookup_pricing']['record']['unit_cost'],22)
        self.assertEqual(results['get_shop_context']['record']['date_today'],'2026-08-31')
        self.assertEqual(len(results['list_tickets']['records']),3)
        self.assertEqual(results['get_ticket']['record']['invoice_id'],501)
        self.assertEqual(len(results['list_vendors']['records']),3)
        self.assertTrue(results['get_vendor_status']['shipping_blocked_by_open_invoice'])
        self.assertEqual(results['get_vendor_status']['vendor']['lead_days'],5)
        self.assertEqual(results['get_invoice']['record']['amount'],840)
        self.assertEqual(results['list_cash_accounts']['records'][0]['balance'],3400)
        self.assertEqual(results['list_payments']['records'],[])
        proposal=results['prepare_payment']
        self.assertEqual(proposal['status'],'requires_human_approval')
        self.assertFalse(proposal['execution_enabled'])
        self.assertEqual(proposal['proposal']['balance_if_paid'],'2560.0')
        self.assertEqual(len(state.proposals),1)
        (ROOT/'output/problem5_mcp_checks.json').write_text(json.dumps(results,indent=2)+'\n')

    async def test_bounded_pydantic_loop_mock_http_real_mcp(self):
        # The actual configured model remains gpt-6-luna. Mock only HTTP responses;
        # no alternative model implementation and no network inference request.
        real_client=httpx.AsyncClient; captured=[]; counts={}
        def handler(request):
            body=json.loads(request.content); captured.append(body)
            self.assertEqual(body['model'],'gpt-6-luna')
            self.assertEqual(body['reasoning_effort'],'none')
            self.assertEqual(request.url.host,'api.portkey.ai')
            self.assertEqual(request.headers['x-portkey-api-key'],'offline-validation-placeholder')
            content=str(body['messages'])
            role=Role.ACCOUNTING if 'You are Accounting,' in content else Role.INVENTORY
            counts[role]=counts.get(role,0)+1
            if counts[role]==1:
                name='query_shop' if role==Role.ACCOUNTING else 'delegate_task'
                args={'tool':'get_invoice','arguments':{'invoice_id':501}} if role==Role.ACCOUNTING else {'request':{'target':'Accounting','task':'Validation only: read invoice 501 through MCP, report blocked, and stop.'}}
                message={'role':'assistant','content':None,'tool_calls':[{'id':'validation-call-'+str(len(captured)), 'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
                finish='tool_calls'
            else:
                report={'role':role.value,'status':'blocked','summary':'Offline validation only; no operational recommendation.','stop_reason':'Validation complete'}
                message={'role':'assistant','content':None,'tool_calls':[{'id':'validation-output-'+str(len(captured)),'type':'function','function':{'name':'final_result','arguments':json.dumps(report)}}]}
                finish='tool_calls'
            return httpx.Response(200,json={'id':'offline-validation','object':'chat.completion','created':0,
                'model':'gpt-6-luna','choices':[{'index':0,'message':message,'finish_reason':finish}],
                'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}})
        class MockHttpClient(real_client):
            def __init__(self,*args,**kwargs):
                kwargs['transport']=httpx.MockTransport(handler)
                super().__init__(*args,**kwargs)
        with patch.dict(os.environ,{'PORTKEY_API_KEY':'offline-validation-placeholder'}), patch('backend.gateway.httpx.AsyncClient',MockHttpClient):
            team=AgentTeam()
        try:
            result=await team.run('Offline validation only: ask Accounting to read invoice 501, then stop. Do not resolve tickets.',Role.INVENTORY)
            AuditTrail().append(run_id=result['run_id'],active_agent='Inventory',action='validation_method',result_summary='Mock Portkey HTTP responses; real MCP reads; no live inference or operational recommendation.')
            self.assertIn('report',result, result)
            self.assertEqual(result['report']['status'],'blocked')
            self.assertEqual(set(counts),{Role.INVENTORY,Role.ACCOUNTING})
            self.assertEqual(len(captured),4)
            events=[e for e in json.loads((ROOT/'output/audit_trail.json').read_text()) if e['run_id']==result['run_id']]
            self.assertTrue(any(e['action']=='delegate' and e['delegation_target']=='Accounting' for e in events))
            self.assertTrue(any(e['mcp_tool']=='get_invoice' for e in events))
            self.assertEqual(sum(e['action']=='model_request' for e in events),4)
        finally: await team.close()

    async def test_unknown_tool_and_unknown_evidence_fail_closed(self):
        state=RunState()
        with self.assertRaises(RunStopped): await call_shop(None,state,Role.BOSS,'execute_payment',{'approved':True})
        state=RunState()
        report=AgentReport(role=Role.BOSS,status='recommendation',summary='test',stop_reason='test',
                           evidence=[Evidence(evidence_id='invented',tool='get_invoice',summary='test')])
        with self.assertRaises(RunStopped):AgentTeam.validate_report(report,Role.BOSS,state)


if __name__ == '__main__': unittest.main()
