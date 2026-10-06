"""Explicit local-human request bodies; not tools available to the agents."""
from typing import Literal
from pydantic import Field, StrictBool, field_validator
from .models import StrictModel


class HumanApproval(StrictModel):
    approved: StrictBool
    reviewer: str = Field(min_length=1,max_length=100)
    next_due: str | None = None

    @field_validator('reviewer')
    @classmethod
    def reviewer_not_empty(cls,value):
        value=value.strip()
        if not value:raise ValueError('A human reviewer name is required')
        return value


class ResetRequest(StrictModel):
    confirmation: Literal['RESET_WORKING_DATABASE']
