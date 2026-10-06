"""Public read-only MCP by default; private human-control mode only for FastAPI."""
from fastmcp import FastMCP
from .tools import register_tools


def create_server(control_token: str | None = None):
    instance=FastMCP('Campus Customs')
    register_tools(instance)
    if control_token is not None:
        if len(control_token)<32:raise ValueError('Private capability is too short')
        from .control import register_control_tools
        register_control_tools(instance,control_token)
    return instance


mcp=create_server()

if __name__=='__main__':
    import argparse
    import os
    parser=argparse.ArgumentParser()
    parser.add_argument('--control',action='store_true')
    args=parser.parse_args()
    server=create_server(os.environ.pop('CC_CONTROL_TOKEN','')) if args.control else mcp
    server.run(show_banner=False)
