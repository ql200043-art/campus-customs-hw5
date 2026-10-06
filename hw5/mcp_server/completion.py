"""Narrow operations-desk completion, distinct from physical fulfillment."""
import json
from pathlib import Path
from .control import control_transaction, Rejected, _generation

AUDIT_PATH = Path(__file__).resolve().parents[1]/'output/audit_trail.json'
OUTCOME = ('Operations investigation complete; physical fulfillment not completed. '
           'CC-TEE-WHITE size S remains out of stock (recorded quantity 0). '
           'Invoice 501 was paid after explicit human approval; the vendor unpaid-invoice blocker is removed. '
           'Replenishment, shipment, receipt and delivery remain unverified; no shipment or delivery promise is made. '
           'No further payment is required for this ticket. Customer communication is a draft only; nobody was contacted.')
DRAFT = ('Draft only — Your requested size S Bulldog tee is currently out of stock. '
         'We cannot confirm replenishment, shipment or delivery timing. No fulfillment promise is made.')


def complete_ticket101(run_id: str) -> dict:
    # The model cannot supply closure text, quantities, dates, approvals or money.
    with control_transaction() as db:
        events=json.loads(AUDIT_PATH.read_text())
        evidence=[e for e in events if e.get('run_id')==run_id]
        completed={e.get('active_agent') for e in evidence if e.get('action')=='agent_complete'}
        if not {'Boss','Inventory','Customer Service'} <= completed or any(e.get('action')=='run_failed' for e in evidence):
            raise Rejected('A completed Boss/Inventory/Customer Service investigation is required')
        calls=[e for e in evidence if e.get('action')=='mcp_call']
        if not any(e.get('mcp_tool')=='get_ticket' and e.get('arguments',{}).get('ticket_id')==101 for e in calls):
            raise Rejected('Investigation must concern Ticket 101')
        t=db.execute('SELECT * FROM tickets WHERE id=101').fetchone()
        invoice=db.execute('SELECT * FROM invoices WHERE id=501').fetchone()
        stock=db.execute("SELECT qty FROM inventory WHERE sku='CC-TEE-WHITE' AND size='S'").fetchone()
        if not t or t['type']!='customer_order' or t['sku']!='CC-TEE-WHITE' or t['size']!='S' or t['qty']!=1 or t['invoice_id']!=501:
            raise Rejected('Ticket does not match this narrow completion policy')
        if not invoice or invoice['status']!='paid' or not stock or stock['qty']!=0:
            raise Rejected('Requires paid invoice and unchanged out-of-stock state')
        if db.execute("SELECT 1 FROM invoices WHERE vendor_id=? AND status='open'",(invoice['vendor_id'],)).fetchone():
            raise Rejected('Vendor still has a payment blocker')
        receipts=db.execute("SELECT p.*,r.executed_at FROM payments p JOIN review.proposals r ON r.payment_id=p.id WHERE r.generation=? AND r.ticket_id=101 AND r.status='executed' AND p.kind='invoice' AND p.ref_id=501",(_generation(db),)).fetchall()
        if len(receipts)!=1 or receipts[0]['amount']!=invoice['amount'] or not receipts[0]['approved_by']:
            raise Rejected('Exactly one matching human-approved execution receipt is required')
        if any(e.get('timestamp','')<receipts[0]['executed_at'] for e in evidence):
            raise Rejected('Investigation must be completed after human payment')
        if db.execute("SELECT 1 FROM review.proposals WHERE generation=? AND ticket_id=101 AND status='pending'",(_generation(db),)).fetchone():
            raise Rejected('Pending human review prevents completion')
        if db.execute('SELECT 1 FROM cash_accounts WHERE balance<0').fetchone():
            raise Rejected('Invalid negative cash state')
        marker='[Operations completion; run '+run_id+']'
        if t['status']=='closed' and marker in (t['notes'] or ''):
            return {'ok':True,'status':'closed','changed':False,'outcome':OUTCOME,'customer_draft':DRAFT}
        if t['status']!='open':raise Rejected('Ticket must remain open')
        notes=(t['notes'] or '')+'\n\n'+marker+'\n'+OUTCOME+'\n'+DRAFT
        db.execute("UPDATE tickets SET status='closed',notes=? WHERE id=101 AND status='open'",(notes,))
        return {'ok':True,'ticket_id':101,'status':'closed','changed':True,'outcome':OUTCOME,'customer_draft':DRAFT,'notes':notes,'physical_fulfillment_completed':False}


def complete_ticket103(run_id: str, generation: str, report: dict, reports: list, evidence: dict) -> dict:
    """Commit only a validated decline; never grant discounts or alter stock/money."""
    with control_transaction() as db:
        if generation != _generation(db):raise Rejected('Reset occurred during investigation')
        events=[e for e in json.loads(AUDIT_PATH.read_text()) if e.get('run_id')==run_id]
        roles={e.get('active_agent') for e in events if e.get('action')=='agent_complete'}
        if not {'Boss','Inventory','Accounting','Customer Service'}<=roles or any(e.get('action') in ('run_failed','stop') for e in events):
            raise Rejected('All required agents must complete without a fatal run stop')
        if report.get('role')!='Boss' or report.get('disposition')!='declined_as_requested' or report.get('status')!='recommendation' or report.get('human_approval_required') or report.get('payment_proposal_ids'):
            raise Rejected('Requires a final decline with no pending approval/payment')
        drafts=[r.get('customer_draft') for r in reports if r.get('role')=='Customer Service' and r.get('customer_draft')]
        if not drafts or not report.get('customer_draft'):raise Rejected('A completed Customer Service draft and final Boss draft are required')
        if db.execute("SELECT 1 FROM review.proposals WHERE generation=? AND ticket_id=103 AND status='pending'",(generation,)).fetchone():raise Rejected('Pending proposal prevents completion')
        ticket=db.execute('SELECT * FROM tickets WHERE id=103').fetchone()
        if not ticket or ticket['type']!='price_override' or ticket['invoice_id'] is not None or ticket['lease_id'] is not None:raise Rejected('Unexpected ticket/obligation')
        stock=db.execute('SELECT * FROM inventory WHERE sku=? AND size=?',(ticket['sku'],ticket['size'])).fetchone()
        pricing=db.execute('SELECT * FROM pricing WHERE sku=?',(ticket['sku'],)).fetchone()
        if not stock or not pricing or not 0<=stock['qty']<ticket['qty']:raise Rejected('Verified shortfall required')
        for tool,record in [('get_ticket',ticket),('lookup_inventory',stock),('lookup_pricing',pricing)]:
            sources=[(key,value) for key,value in evidence.items() if value.get('tool')==tool and value.get('data',{}).get('record')==dict(record)]
            if not any(key.startswith(run_id+':mcp:') and any(e.get('action')=='mcp_result' and e.get('mcp_tool')==tool and ('evidence='+key+';') in e.get('result_summary','') for e in events) for key,value in sources):
                raise Rejected('Current facts must match audited run evidence for '+tool)
        if db.execute('SELECT 1 FROM cash_accounts WHERE balance<0').fetchone():raise Rejected('Negative cash state')
        if ticket['status']!='open':raise Rejected('Ticket is not open')
        outcome=(f"Request declined as stated: {ticket['qty']} units of {ticket['sku']}, size {ticket['size']}; recorded stock {stock['qty']}, shortfall {ticket['qty']-stock['qty']}. "
                 'No supported bulk-discount authorization was established. No discount applied and no stock reserved or replenished. '
                 'Exact-variant replenishment and delivery are unverified; no shipment promise. No payment required or executed. '
                 'Customer response is a draft only; nobody contacted. Operations investigation complete; the requested order was not accepted or fulfilled.')
        notes=(ticket['notes'] or '')+'\n\n[Operations decline; run '+run_id+']\n'+outcome+'\nBoss disposition: '+report['summary']+'\nCustomer Service draft only: '+drafts[-1]
        db.execute("UPDATE tickets SET status='closed',notes=? WHERE id=103 AND status='open'",(notes,))
        return {'ok':True,'changed':True,'ticket_id':103,'status':'closed','outcome':outcome,'customer_draft':drafts[-1],'notes':notes,'physical_fulfillment_completed':False}
