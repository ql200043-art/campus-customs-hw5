"""Exactly five PydanticAI agents; any role may delegate to any other role."""
import asyncio
import json
from dataclasses import dataclass
from typing import Literal
from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits
from .gateway import create_model, safe_configuration, safe_http_failure, safe_validation_diagnostics
from .models import Role, AgentReport, DelegationRequest, PaymentReviewRequest
from .runtime import RunState, RunStopped
from .mcp_connection import new_client, call_shop
from .settings import (ROOT, TOOL_NAMES, MAX_TASK_CHARS, MAX_MODEL_REQUESTS,
                       MAX_FUNCTION_CALLS, RUN_TIMEOUT_SECONDS)

ShopTool = Literal['lookup_inventory','lookup_lease','lookup_pricing','get_shop_context',
                   'list_tickets','get_ticket','list_vendors','get_vendor_status',
                   'get_invoice','list_cash_accounts','list_payments','prepare_payment']
PROMPTS = {Role.BOSS:'boss.md', Role.INVENTORY:'inventory.md', Role.ACCOUNTING:'accounting.md',
           Role.FACILITIES:'facilities.md', Role.CUSTOMER_SERVICE:'customer_service.md'}


@dataclass
class Dependencies:
    team: 'AgentTeam'
    state: RunState
    client: object
    role: Role
    stack: tuple[Role,...]


async def query_shop(ctx: RunContext[Dependencies], tool: ShopTool, arguments: dict) -> dict:
    """Call one allowlisted MCP tool. Discover inputs in the role prompt; never submit SQL."""
    d = ctx.deps
    return await call_shop(d.client, d.state, d.role, tool, arguments)


async def delegate_task(ctx: RunContext[Dependencies], request: DelegationRequest) -> dict:
    """Ask any OTHER agent for a bounded evidence-backed subtask; no recursive active-role cycles."""
    d = ctx.deps
    if not d.state.delegate(d.role, request.target, d.stack):
        return {'status':'delegation_skipped','target':request.target.value,
                'reason':'Self-delegation or active-path cycle blocked. No child ran; no facts changed. Finish from verified evidence or state missing facts; do not repeat this delegation.'}
    report = await d.team._run(request.target, request.task, d.state, d.client, d.stack)
    return report.model_dump(mode='json')


class AgentTeam:
    def __init__(self):
        self.model = create_model()
        self.agents = {}
        for role in Role:
            agent = Agent(self.model, name=role.value, deps_type=Dependencies, output_type=AgentReport,
                          instructions=(ROOT/'backend/prompts'/PROMPTS[role]).read_text(), retries=0,
                          model_settings={'max_tokens':2500, 'parallel_tool_calls':False,
                                          'openai_reasoning_effort':'none'})
            agent.tool(query_shop, sequential=True)
            agent.tool(delegate_task, sequential=True, strict=True)
            self.agents[role] = agent
        self.connectivity = {role: tuple(other for other in Role if other != role) for role in Role}

    async def close(self):
        await self.model.client.close()

    async def _run(self, role: Role, task: str, state: RunState, client, stack: tuple[Role,...]) -> AgentReport:
        state.enter(role, stack)
        deps = Dependencies(self, state, client, role, (*stack, role))
        state.audit.append(run_id=state.run_id, active_agent=role, action='agent_start')
        # Every agent gets current simulated date via MCP before reasoning, never the OS date.
        context = await call_shop(client, state, role, 'get_shop_context', {})
        if not context['data'].get('found'):
            state.stop(role, 'Missing authoritative shop date')
        user_input = (task+'\nVerified shop context from MCP:\n'+str(context)
                      +'\nActive path (do not delegate to these roles): '+', '.join(deps.stack)
                      +'\nVerified MCP evidence already collected this run:\n'+json.dumps(state.evidence)
                      +'\nCompleted reports (advice; cite the underlying MCP evidence):\n'+json.dumps(state.completed_reports))
        async with self.agents[role].iter(user_input, deps=deps, usage=state.usage,
                usage_limits=UsageLimits(request_limit=MAX_MODEL_REQUESTS, tool_calls_limit=MAX_FUNCTION_CALLS)) as run:
            async for node in run:
                if Agent.is_model_request_node(node):
                    state.model_step(role)
                else:
                    state.audit.append(run_id=state.run_id, active_agent=role, action='agent_step',
                                       result_summary=type(node).__name__)
            report = run.result.output
        self.validate_report(report, role, state)
        state.completed_reports.append(report.model_dump(mode='json'))
        state.audit.append(run_id=state.run_id, active_agent=role, action='agent_complete',
                           result_summary=f'status={report.status}; {report.summary}',
                           human_approval_required=report.human_approval_required, stop_reason=report.stop_reason)
        return report

    @staticmethod
    def validate_report(report: AgentReport, role: Role, state: RunState):
        if report.role != role:
            state.stop(role, 'Output role mismatch')
        if report.status != 'blocked' and not report.evidence:
            state.stop(role, 'Recommendation lacks MCP evidence')
        for evidence in report.evidence:
            source = state.evidence.get(evidence.evidence_id)
            if not source or source['tool'] != evidence.tool:
                state.stop(role, 'Unknown evidence citation')
        if any(p not in state.proposals for p in report.payment_proposal_ids):
            state.stop(role, 'Payment proposal not backed by MCP')
        if report.payment_proposal_ids:
            report.status = 'needs_human_approval'
        if report.status == 'needs_human_approval':
            report.human_approval_required = True

    async def run(self, task: str, role: Role = Role.BOSS) -> dict:
        if not 1 <= len(task) <= MAX_TASK_CHARS:
            raise ValueError('Task must contain 1–2000 characters')
        state = RunState()
        state.audit.append(run_id=state.run_id, active_agent=role, action='model_configuration',
                           result_summary=safe_configuration())
        try:
            async with asyncio.timeout(RUN_TIMEOUT_SECONDS):
                async with new_client() as client:
                    names = {t.name for t in await client.list_tools()}
                    if not set(TOOL_NAMES).issubset(names):
                        state.stop(role, 'Required MCP tools unavailable')
                    report = await self._run(role, task, state, client, ())
            return {'run_id':state.run_id, 'report':report.model_dump(mode='json'),
                    'completed_reports':state.completed_reports,'mcp_evidence':state.evidence,
                    'payment_reviews':[PaymentReviewRequest(proposal_id=k,run_id=state.run_id).model_dump()
                                       for k in state.proposals],
                    'payment_proposals':list(state.proposals.values())}
        except Exception as exc:
            state.audit.append(run_id=state.run_id, active_agent=role, action='exception_diagnostic',
                               result_summary=safe_validation_diagnostics(exc))
            reason = str(exc) if isinstance(exc, RunStopped) else safe_http_failure(exc)
            state.audit.append(run_id=state.run_id, active_agent=role, action='run_failed',
                               stop_reason=reason)
            return {'run_id':state.run_id, 'status':'blocked',
                    'stop_reason':reason,
                    'payment_reviews':[PaymentReviewRequest(proposal_id=k,run_id=state.run_id).model_dump()
                                       for k in state.proposals],
                    'payment_proposals':list(state.proposals.values())}
