"""FastAPI's transport-only MCP gateway. No shop database access in backend."""
import secrets
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from .mcp_connection import new_client
from .settings import ROOT, MCP_TIMEOUT_SECONDS, TOOL_NAMES

CONTROL_TOOLS={'control_get_state','control_stage_proposal','control_execute_payment','control_reset','control_complete_ticket101_operations','control_complete_ticket103_operations'}


class MCPGateway:
    def __init__(self):
        self.capability=secrets.token_urlsafe(48)

    def shop_client(self):
        return new_client()

    def control_client(self):
        return Client(StdioTransport(command=str(ROOT/'mcp_server/.venv/bin/python'),
                      args=['-m','mcp_server.server','--control'],cwd=str(ROOT),
                      env={'CC_CONTROL_TOKEN':self.capability},keep_alive=False),timeout=MCP_TIMEOUT_SECONDS)

    async def read(self,name,arguments=None):
        if name not in TOOL_NAMES:raise ValueError('Not a public shop tool')
        async with self.shop_client() as client:
            result=await client.call_tool(name,arguments or {})
        if result.is_error or not isinstance(result.structured_content,dict):raise RuntimeError('MCP read failed')
        return result.structured_content

    async def control(self,name,arguments=None):
        if name not in CONTROL_TOOLS:raise ValueError('Not a control operation')
        async with self.control_client() as client:
            result=await client.call_tool(name,{'capability':self.capability,**(arguments or {})})
        if result.is_error or not isinstance(result.structured_content,dict):raise RuntimeError('MCP control failed')
        return result.structured_content
