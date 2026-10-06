"""Focused investigation and payment preparation; no operational mutations."""
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Literal

from .database import fetch_one, fetch_page, read_connection


def get_shop_context() -> dict:
    """Read the single authoritative desk row; reject missing/ambiguous shop dates."""
    with read_connection() as connection:
        rows = connection.execute('SELECT date_today, notes FROM desk LIMIT 2').fetchall()
    if len(rows) != 1:
        return {'found': False, 'message': 'Expected exactly one desk row; stop date-sensitive work.'}
    row = dict(rows[0])
    date.fromisoformat(row['date_today'])
    return {'found': True, 'record': row}


def list_tickets(status: Literal['open', 'closed'] = 'open', limit: int = 25) -> dict:
    """List current tickets by exact status, at most 25 rows; report truncation."""
    return fetch_page('SELECT * FROM tickets WHERE status=? ORDER BY id', (status,), limit)


def get_ticket(ticket_id: int) -> dict:
    """Read all stored fields of a ticket, including lease/invoice references."""
    return fetch_one('SELECT * FROM tickets WHERE id=?', (ticket_id,))


def list_vendors(limit: int = 25) -> dict:
    """Read vendor capabilities and recorded lead_days; no product suitability assumptions."""
    return fetch_page('SELECT id, name, specialty, lead_days FROM vendors ORDER BY id', (), limit)


def get_vendor_status(vendor_id: int) -> dict:
    """Read a vendor and open invoices; any open invoice blocks shipment under shop rules."""
    with read_connection() as connection:
        vendor = connection.execute('SELECT * FROM vendors WHERE id=?', (vendor_id,)).fetchone()
        if vendor is None:
            return {'found': False, 'message': 'Vendor not found.'}
        invoices = connection.execute(
            "SELECT * FROM invoices WHERE vendor_id=? AND status='open' ORDER BY id LIMIT 26",
            (vendor_id,),
        ).fetchall()
    return {'found': True, 'vendor': dict(vendor), 'open_invoices': [dict(r) for r in invoices[:25]],
            'truncated': len(invoices)>25, 'shipping_blocked_by_open_invoice': bool(invoices),
            'rule': 'A vendor will not ship new product while an open unpaid invoice remains.',
            'caution': 'No open invoice is not proof of stock, shipment or SKU suitability.'}


def get_invoice(invoice_id: int) -> dict:
    """Read invoice amount/status, due date and its declared vendor_id reference."""
    return fetch_one('SELECT * FROM invoices WHERE id=?', (invoice_id,))


def list_cash_accounts(limit: int = 25) -> dict:
    """Read account names, recorded balances and dates without assuming an account name."""
    return fetch_page('SELECT name, balance, date FROM cash_accounts ORDER BY name', (), limit)


def list_payments(kind: Literal['invoice', 'rent'] | None = None,
                  ref_id: int | None = None, limit: int = 25) -> dict:
    """Read payment history; kind/ref_id are inferred business links, not foreign keys."""
    return fetch_page('SELECT * FROM payments WHERE (? IS NULL OR kind=?) AND (? IS NULL OR ref_id=?) ORDER BY id',
                      (kind, kind, ref_id, ref_id), limit)


def checked_balance(balance, amount) -> Decimal:
    """Reject invalid money or insufficient cash; never propose a negative balance."""
    try:
        balance, amount = Decimal(str(balance)), Decimal(str(amount))
    except InvalidOperation as exc:
        raise ValueError('Invalid monetary data') from exc
    if not balance.is_finite() or not amount.is_finite() or balance < 0 or amount <= 0:
        raise ValueError('Money must be finite, balance nonnegative, amount positive')
    if amount != amount.quantize(Decimal('0.01')) or balance != balance.quantize(Decimal('0.01')):
        raise ValueError('Money has unsupported sub-cent precision')
    if amount > balance:
        raise ValueError('Insufficient cash; payment refused')
    return balance - amount


def prepare_payment(kind: Literal['invoice', 'rent'], ref_id: int, account: str) -> dict:
    """Prepare a read-only payment proposal from an actual obligation; NEVER approve or execute.

    Amount, payee, due date and shop date come from the database. Checks cash and
    possible duplicates. Rent history requires manual review because no billing-
    period field exists. This neither reserves money nor changes invoice/lease state.
    """
    with read_connection() as connection:
        return payment_snapshot(connection, kind, ref_id, account)


def payment_snapshot(connection, kind: str, ref_id: int, account: str) -> dict:
    """Derive/revalidate one proposal inside a caller-owned consistent transaction."""
    if kind not in ('invoice', 'rent'):
        raise ValueError('Only invoice or rent obligations are supported')
    desk = connection.execute('SELECT date_today FROM desk LIMIT 2').fetchall()
    cash = connection.execute('SELECT * FROM cash_accounts WHERE name=?', (account,)).fetchone()
    query = 'SELECT * FROM invoices WHERE id=?' if kind == 'invoice' else 'SELECT * FROM leases WHERE id=?'
    obligation = connection.execute(query, (ref_id,)).fetchone()
    if len(desk) != 1 or cash is None or obligation is None:
        return {'status': 'blocked', 'reason': 'Missing or ambiguous shop date, account or obligation.', 'human_approval_required': True}
    today = desk[0]['date_today']
    date.fromisoformat(today)
    if kind == 'invoice':
        if obligation['status'] != 'open':
            return {'status': 'blocked', 'reason': 'Invoice is not open.', 'human_approval_required': True}
        vendor = connection.execute('SELECT * FROM vendors WHERE id=?', (obligation['vendor_id'],)).fetchone()
        if vendor is None:
            return {'status': 'blocked', 'reason': 'Invoice vendor is missing.', 'human_approval_required': True}
        amount, payee, due = obligation['amount'], vendor['name'], obligation['due_date']
    else:
        amount, payee, due = obligation['monthly_rent'], obligation['landlord'], obligation['next_due']
    date.fromisoformat(due)
    # Conservatively flag ANY matching reference, including ambiguous kind strings.
    prior = connection.execute('SELECT id FROM payments WHERE ref_id=? LIMIT 1', (ref_id,)).fetchone()
    if prior is not None:
        return {'status': 'blocked', 'reason': 'Existing payment reference requires human duplicate/period review.', 'human_approval_required': True}
    try:
        after = checked_balance(cash['balance'], amount)
    except ValueError as exc:
        return {'status': 'blocked', 'reason': str(exc), 'human_approval_required': True}
    proposal = {'kind': kind, 'ref_id': ref_id, 'account': account, 'amount': str(Decimal(str(amount))),
                'payee': payee, 'due_date': due, 'shop_date': today,
                'balance_observed': str(Decimal(str(cash['balance']))), 'balance_if_paid': str(after)}
    fingerprint = hashlib.sha256(json.dumps(proposal, sort_keys=True).encode()).hexdigest()
    return {'status': 'requires_human_approval', 'human_approval_required': True,
            'execution_enabled': False, 'proposal_id': fingerprint, 'proposal': proposal,
            'notice': 'Proposal only; not approved, paid or reserved. Revalidate all facts at any future execution.'}


NEW_TOOLS = (get_shop_context, list_tickets, get_ticket, list_vendors, get_vendor_status,
             get_invoice, list_cash_accounts, list_payments, prepare_payment)
