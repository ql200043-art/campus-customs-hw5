"""Factual lookups; business decisions and operational changes are out of scope."""
from .database import fetch_one
from .operations import NEW_TOOLS


def lookup_inventory(sku: str, size: str) -> dict:
    """Return inventory for an exact SKU and size, including on-hand qty and location.

    Helps investigate ticket 101's requested tee variant. Zero stock is a found
    record, not a missing record. Does not reserve stock or promise fulfillment.
    """
    return fetch_one(
        "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
        (sku, size),
    )


def lookup_lease(lease_id: int) -> dict:
    """Return a lease by its id, including landlord, monthly_rent and next_due.

    Use tickets.lease_id for ticket 102. Dates are returned as stored; later
    agents must use desk.date_today, not the computer date, to assess urgency.
    """
    return fetch_one(
        "SELECT id, space_name, landlord, monthly_rent, next_due, notes FROM leases WHERE id = ?",
        (lease_id,),
    )


def lookup_pricing(sku: str) -> dict:
    """Return stored unit_cost and list_price for an exact SKU.

    Supports ticket 103's hoodie discount investigation. Pricing is per SKU,
    not per size; this lookup does not invent or approve a discount.
    """
    return fetch_one(
        "SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?", (sku,),
    )


def register_tools(server) -> None:
    """Preserve the initial three tools and register focused Problem 5 tools."""
    for tool in (lookup_inventory, lookup_lease, lookup_pricing, *NEW_TOOLS):
        server.tool(annotations={"readOnlyHint": True, "destructiveHint": False,
                                 "idempotentHint": True, "openWorldHint": False})(tool)
