"""Shared counters and audit context for a single request and all its delegates."""
from dataclasses import dataclass, field
from uuid import uuid4
from pydantic_ai.usage import RunUsage
from .audit import AuditTrail
from .models import Role
from .settings import MAX_AGENT_RUNS, MAX_DELEGATIONS, MAX_DEPTH, MAX_MCP_CALLS, MAX_MODEL_REQUESTS


class RunStopped(RuntimeError):
    pass


@dataclass
class RunState:
    run_id: str = field(default_factory=lambda: str(uuid4()))
    audit: AuditTrail = field(default_factory=AuditTrail)
    usage: RunUsage = field(default_factory=RunUsage)
    agent_runs: int = 0
    delegations: int = 0
    mcp_calls: int = 0
    model_requests: int = 0
    evidence: dict = field(default_factory=dict)
    proposals: dict = field(default_factory=dict)
    completed_reports: list = field(default_factory=list)
    stopped: bool = False

    def stop(self, role: Role, reason: str):
        self.stopped = True
        self.audit.append(run_id=self.run_id, active_agent=role, action='stop', stop_reason=reason)
        raise RunStopped(reason)

    def consume(self, name: str, limit: int, role: Role):
        if self.stopped or getattr(self, name) >= limit:
            self.stop(role, f'{name} limit reached or request stopped')
        setattr(self, name, getattr(self, name)+1)

    def enter(self, role: Role, stack: tuple[Role,...]):
        if role in stack:
            self.stop(role, 'Delegation cycle blocked')
        if len(stack) > MAX_DEPTH:
            self.stop(role, 'Delegation depth limit reached')
        self.consume('agent_runs', MAX_AGENT_RUNS, role)

    def delegate(self, source: Role, target: Role, stack: tuple[Role,...]):
        if target == source or target in stack:
            self.consume('delegations', MAX_DELEGATIONS, source)
            self.audit.append(run_id=self.run_id, active_agent=source, action='delegation_skipped',
                              delegation_target=target, result_summary='Active path: '+ ' -> '.join(stack),
                              stop_reason='Self-delegation or active-path cycle blocked; no child invoked')
            return False
        if len(stack) >= MAX_DEPTH + 1:
            self.stop(source, 'Delegation depth limit reached')
        self.consume('delegations', MAX_DELEGATIONS, source)
        self.audit.append(run_id=self.run_id, active_agent=source, action='delegate', delegation_target=target)
        return True

    def model_step(self, role: Role):
        self.consume('model_requests', MAX_MODEL_REQUESTS, role)
        self.audit.append(run_id=self.run_id, active_agent=role, action='model_request',
                          result_summary='Requesting a structured recommendation; private reasoning not logged.')

    def mcp_step(self, role: Role):
        self.consume('mcp_calls', MAX_MCP_CALLS, role)
