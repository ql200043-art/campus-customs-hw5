"""Transport-only MCP adapter. No SQLite, direct server imports, or fallback facts."""
import asyncio
import json
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from .settings import ROOT, TOOL_NAMES, MCP_TIMEOUT_SECONDS, MAX_RESULT_BYTES
from .models import Role
from .runtime import RunState


def new_client() -> Client:
    return Client(StdioTransport(command=str(ROOT/'mcp_server/.venv/bin/python'),
                                 args=['-m','mcp_server.server'], cwd=str(ROOT), keep_alive=False),
                  timeout=MCP_TIMEOUT_SECONDS)


async def call_shop(client: Client, state: RunState, role: Role, name: str, arguments: dict) -> dict:
    if name not in TOOL_NAMES:
        state.stop(role, 'Unknown or prohibited MCP tool')
    if len(json.dumps(arguments).encode()) > 2000:
        state.stop(role, 'Tool arguments too large')
    state.mcp_step(role)
    call_number = state.mcp_calls
    state.audit.append(run_id=state.run_id, active_agent=role, action='mcp_call', mcp_tool=name,
                       arguments=arguments, human_approval_required=name=='prepare_payment')
    try:
        result = await asyncio.wait_for(client.call_tool(name, arguments), timeout=MCP_TIMEOUT_SECONDS)
        data = result.structured_content
        if not isinstance(data, dict) or result.is_error:
            raise RuntimeError('MCP returned an error or invalid structured result')
        if len(json.dumps(data).encode()) > MAX_RESULT_BYTES:
            state.stop(role, 'MCP result exceeds size cap; narrow the query')
        evidence_id = f'{state.run_id}:mcp:{call_number}'
        state.evidence[evidence_id] = {'tool':name, 'arguments':arguments, 'data':data}
        if name == 'prepare_payment' and data.get('status') == 'requires_human_approval':
            state.proposals[data['proposal_id']] = data
        state.audit.append(run_id=state.run_id, active_agent=role, action='mcp_result', mcp_tool=name,
                           result_summary=f"evidence={evidence_id}; found={data.get('found')}; status={data.get('status')}; rows={len(data.get('records', []))}",
                           human_approval_required=name=='prepare_payment')
        return {'evidence_id':evidence_id, 'tool':name, 'data':data}
    except Exception as exc:
        state.stop(role, f'MCP call failed ({type(exc).__name__}); no fallback facts')
