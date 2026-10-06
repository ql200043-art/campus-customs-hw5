"""Launch Codex with this project's MCP entry explicitly loaded; no global edits."""
import json
import os
from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def config_overrides():
    config = tomllib.loads((ROOT / '.codex/config.toml').read_text())
    arguments = []
    for key, value in config['mcp_servers']['campus_customs'].items():
        arguments += ['-c', f'mcp_servers.campus_customs.{key}='+json.dumps(value)]
    return arguments


if __name__ == '__main__':
    os.chdir(ROOT)
    os.execvp('codex', ['codex', *config_overrides(), '-C', str(ROOT), *sys.argv[1:]])
