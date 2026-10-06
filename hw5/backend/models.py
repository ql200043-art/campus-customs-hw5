"""Structured requests, evidence and recommendations; never payment authorization."""
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Role(StrEnum):
    BOSS = 'Boss'
    INVENTORY = 'Inventory'
    ACCOUNTING = 'Accounting'
    FACILITIES = 'Facilities'
    CUSTOMER_SERVICE = 'Customer Service'


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class DelegationRequest(StrictModel):
    target: Role
    task: str = Field(min_length=1, max_length=2000)


class Evidence(StrictModel):
    evidence_id: str
    tool: str
    summary: str = Field(max_length=600, description='Brief supported fact; no private reasoning.')


class AgentReport(StrictModel):
    disposition: Literal['none', 'declined_as_requested'] = 'none'
    role: Role
    status: Literal['recommendation', 'blocked', 'needs_human_approval']
    summary: str = Field(max_length=1500)
    evidence: list[Evidence] = Field(default_factory=list, max_length=20)
    missing_information: list[str] = Field(default_factory=list, max_length=15)
    recommended_actions: list[str] = Field(default_factory=list, max_length=15)
    payment_proposal_ids: list[str] = Field(default_factory=list, max_length=5)
    customer_draft: str | None = Field(default=None, max_length=3000)
    human_approval_required: bool = False
    stop_reason: str = Field(max_length=250)


class PaymentReviewRequest(StrictModel):
    """Data for a FUTURE trusted human UI; not an approval token or execution API."""
    proposal_id: str
    run_id: str
    status: Literal['pending_human_review'] = 'pending_human_review'
    execution_enabled: Literal[False] = False
