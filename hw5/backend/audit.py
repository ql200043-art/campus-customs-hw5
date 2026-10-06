"""Append-only event records in a JSON array. No reset/delete API or model traces."""
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
from .settings import ROOT

SAFE_ARGUMENTS = {'sku','size','lease_id','ticket_id','invoice_id','vendor_id','ref_id','kind','account','name','status','limit'}


def safe_arguments(arguments: dict) -> dict:
    return {k: (str(v)[:100] if isinstance(v, str) else v)
            for k,v in arguments.items() if k in SAFE_ARGUMENTS and isinstance(v, (str,int,float,bool,type(None)))}


class AuditTrail:
    def __init__(self, path: Path = ROOT/'output/audit_trail.json'):
        self.path = path

    def append(self, *, run_id: str, active_agent: str, action: str,
               delegation_target: str | None = None, mcp_tool: str | None = None,
               arguments: dict | None = None, result_summary: str = '',
               human_approval_required: bool = False, stop_reason: str | None = None):
        event = {'timestamp': datetime.now(timezone.utc).isoformat(), 'run_id':run_id,
                 'active_agent':str(active_agent), 'action':action[:160],
                 'delegation_target':delegation_target, 'mcp_tool':mcp_tool,
                 'arguments':safe_arguments(arguments or {}), 'result_summary':result_summary[:400],
                 'human_approval_required':human_approval_required, 'stop_reason':stop_reason}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Lock the data file across readers/writers. Existing event bytes are never rewritten.
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        with os.fdopen(fd, 'r+b') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            content = handle.read()
            if content:
                existing = json.loads(content)  # corruption fails closed; never wipe a log
                if not isinstance(existing, list):
                    raise ValueError('Audit trail must be a JSON array')
                position = content.rfind(b']')
                handle.seek(position)
                prefix = b',\n' if existing else b'\n'
            else:
                prefix = b'[\n'
            handle.write(prefix + json.dumps(event, ensure_ascii=False).encode('utf-8') + b'\n]\n')
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
        return event
