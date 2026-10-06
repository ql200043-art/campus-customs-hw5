"""Fail-closed boundary reserved for a later authenticated human approval workflow."""
from .models import PaymentReviewRequest


class PaymentExecutionDisabled(PermissionError):
    pass


def execute_payment(review: PaymentReviewRequest | None = None) -> None:
    """No payment writer exists in Problem 5, even if an agent claims approval."""
    raise PaymentExecutionDisabled(
        'Payment execution is disabled. A proposal is not human approval. '
        'A future authenticated human approval path and atomic MCP transaction are required.'
    )
