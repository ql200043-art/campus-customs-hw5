"""Human-control operations on the SAME shop database, never exposed to agents.

Proposal/receipt metadata lives in a sidecar SQLite file, not invented shop columns.
Payment, obligation, ticket and proposal receipt changes share one attached-DB
rollback-journal transaction. Reset uses an exclusive lock and atomic replacement.
"""
from contextlib import contextmanager, closing
from datetime import date, datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from uuid import uuid4

from . import database
from .operations import payment_snapshot, checked_balance

STATE_PATH = Path(__file__).resolve().parents[1] / 'output' / 'payment_review_state.db'


class Rejected(Exception):
    def __init__(self, message, code='conflict'):
        super().__init__(message)
        self.code = code


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def _initialize_state():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    for p in (database.DATABASE_PATH, database.original_path()):
        if STATE_PATH.resolve() == p.resolve() or (STATE_PATH.exists() and p.exists() and STATE_PATH.samefile(p)):
            raise Rejected('Control metadata must not alias a shop database')
    with closing(sqlite3.connect(STATE_PATH)) as db:
        db.executescript('''
            PRAGMA journal_mode=DELETE;
            CREATE TABLE IF NOT EXISTS generation (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS proposals (
                id TEXT PRIMARY KEY, generation TEXT NOT NULL, fingerprint TEXT NOT NULL,
                ticket_id INTEGER NOT NULL, run_id TEXT NOT NULL, snapshot TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','executed','invalidated')),
                created_at TEXT NOT NULL, executed_at TEXT, reviewer TEXT, payment_id INTEGER,
                UNIQUE(generation, fingerprint, ticket_id)
            );
        ''')
        db.execute('INSERT OR IGNORE INTO generation VALUES(1,?)', (str(uuid4()),))
        db.commit()


@contextmanager
def control_transaction():
    with database.shop_lock(exclusive=True):
        database.protect_original()
        _initialize_state()
        if any(Path(str(database.DATABASE_PATH)+suffix).exists() for suffix in ('-wal','-shm')):
            raise Rejected('Unexpected WAL sidecars; stop and inspect before writing')
        db = sqlite3.connect(database.DATABASE_PATH.resolve().as_uri()+'?mode=rw', uri=True, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            if db.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
                raise Rejected('Payment execution requires rollback-journal mode')
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('ATTACH DATABASE ? AS review', (str(STATE_PATH),))
            db.execute('PRAGMA review.synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()


def _generation(db):
    return db.execute('SELECT value FROM review.generation WHERE id=1').fetchone()[0]


def _ticket(db, ticket_id, proposal):
    row = db.execute('SELECT * FROM tickets WHERE id=?', (ticket_id,)).fetchone()
    if row is None or row['status'] != 'open':
        raise Rejected('Referenced ticket must exist and remain open')
    if proposal['kind'] == 'invoice':
        valid = row['invoice_id'] == proposal['ref_id']
    else:
        valid = row['type'] == 'rent_notice' and row['lease_id'] == proposal['ref_id']
    if not valid:
        raise Rejected('Proposal is not linked to this ticket by its actual obligation reference')
    return row


def get_review_state():
    with control_transaction() as db:
        rows = db.execute("SELECT * FROM review.proposals WHERE generation=? ORDER BY created_at DESC LIMIT 201", (_generation(db),)).fetchall()
        items=[]
        for row in rows[:200]:
            item=dict(row);item['proposal']=json.loads(item.pop('snapshot'));items.append(item)
        return {'ok':True, 'generation':_generation(db), 'proposals':items, 'truncated':len(rows)>200}


def stage_proposal(candidate: dict, ticket_id: int, run_id: str, generation: str):
    with control_transaction() as db:
        if generation != _generation(db):
            raise Rejected('Reset occurred during the run; prepare again')
        p = candidate.get('proposal',{})
        if candidate.get('status') != 'requires_human_approval' or p.get('kind') not in ('invoice','rent'):
            raise Rejected('Only previously prepared invoice/rent proposals are supported')
        if not {'ref_id','account'}.issubset(p):
            raise Rejected('Malformed proposal')
        _ticket(db,ticket_id,p)
        fresh = payment_snapshot(db,p['kind'],p['ref_id'],p['account'])
        if fresh.get('status') != 'requires_human_approval':
            raise Rejected(fresh.get('reason','Proposal no longer valid'))
        if candidate.get('proposal_id') != fresh['proposal_id'] or p != fresh['proposal']:
            raise Rejected('Proposal differs from current database facts; prepare again')
        prior=db.execute('SELECT id,status FROM review.proposals WHERE generation=? AND fingerprint=? AND ticket_id=?',
                         (generation,fresh['proposal_id'],ticket_id)).fetchone()
        if prior:
            if prior['status'] != 'pending':raise Rejected('This proposal is no longer pending')
            return {'ok':True,'proposal_id':prior['id'],'status':'pending'}
        proposal_id=str(uuid4())
        db.execute('INSERT INTO review.proposals(id,generation,fingerprint,ticket_id,run_id,snapshot,status,created_at) VALUES(?,?,?,?,?,?,?,?)',
                   (proposal_id,generation,fresh['proposal_id'],ticket_id,run_id,json.dumps(p,sort_keys=True),'pending',utc_now()))
        return {'ok':True,'proposal_id':proposal_id,'status':'pending'}


def execute_proposal(proposal_id: str, reviewer: str, approved: bool, next_due: str | None = None):
    if approved is not True or not reviewer.strip():
        raise Rejected('Explicit human approval and reviewer name are required','invalid_approval')
    with control_transaction() as db:
        row=db.execute('SELECT * FROM review.proposals WHERE id=?',(proposal_id,)).fetchone()
        if row is None:raise Rejected('Proposal not found','not_found')
        if row['status'] != 'pending' or row['generation'] != _generation(db):
            raise Rejected('Proposal is executed or invalidated; it is not pending')
        p=json.loads(row['snapshot']);ticket=_ticket(db,row['ticket_id'],p)
        fresh=payment_snapshot(db,p['kind'],p['ref_id'],p['account'])
        if fresh.get('status') != 'requires_human_approval':
            raise Rejected(fresh.get('reason','Current obligation is not payable'))
        if fresh['proposal_id'] != row['fingerprint'] or fresh['proposal'] != p:
            raise Rejected('Stale proposal: cash, date or obligation changed; prepare again')
        after=checked_balance(p['balance_observed'],p['amount'])
        if p['kind']=='rent':
            if not next_due:raise Rejected('Human must explicitly confirm the next rent due date','invalid_approval')
            try: later=date.fromisoformat(next_due)
            except ValueError:raise Rejected('next_due must be an ISO date','invalid_approval')
            if later <= max(date.fromisoformat(p['due_date']), date.fromisoformat(p['shop_date'])):
                raise Rejected('Next rent due date must follow this period and the shop date','invalid_approval')
        elif next_due is not None:
            raise Rejected('next_due applies only to rent','invalid_approval')
        # Duplicate check in payment_snapshot runs under this same write transaction.
        debit=db.execute('UPDATE cash_accounts SET balance=?,date=? WHERE name=? AND balance=? AND balance>=?',
                         (float(after),p['shop_date'],p['account'],float(p['balance_observed']),float(p['amount'])))
        if debit.rowcount != 1:raise Rejected('Cash changed or is insufficient')
        payment=db.execute('INSERT INTO payments(kind,ref_id,amount,account,paid_at,approved_by) VALUES(?,?,?,?,?,?)',
                           (p['kind'],p['ref_id'],float(p['amount']),p['account'],p['shop_date'],reviewer.strip()))
        payment_id=payment.lastrowid
        if p['kind']=='invoice':
            changed=db.execute("UPDATE invoices SET status='paid' WHERE id=? AND status='open'",(p['ref_id'],))
            # Paying an invoice does NOT fulfill the customer's out-of-stock order.
            ticket_status=ticket['status']
        else:
            changed=db.execute('UPDATE leases SET next_due=? WHERE id=? AND next_due=?',(next_due,p['ref_id'],p['due_date']))
            closed=db.execute("UPDATE tickets SET status='closed' WHERE id=? AND status='open' AND type='rent_notice' AND lease_id=?",
                              (row['ticket_id'],p['ref_id']))
            if closed.rowcount!=1:raise Rejected('Rent ticket changed during approval')
            ticket_status='closed'
        if changed.rowcount != 1:raise Rejected('Referenced obligation changed')
        db.execute("UPDATE review.proposals SET status='executed',executed_at=?,reviewer=?,payment_id=? WHERE id=?",
                   (utc_now(),reviewer.strip(),payment_id,proposal_id))
        return {'ok':True,'status':'executed','proposal_id':proposal_id,'payment_id':payment_id,
                'kind':p['kind'],'amount':p['amount'],'account':p['account'],'balance':str(after),
                'ticket_id':row['ticket_id'],'ticket_status':ticket_status,'next_due':next_due}


def reset_working_database(confirmation: str):
    if confirmation!='RESET_WORKING_DATABASE':raise Rejected('Reset confirmation required','invalid_approval')
    with database.shop_lock(exclusive=True):
        database.protect_original()
        original=database.original_path();working=database.DATABASE_PATH
        if any(Path(str(p)+s).exists() for p in (working,original) for s in ('-wal','-shm','-journal')):
            raise Rejected('Database sidecars present; refusing unsafe reset')
        source=original.read_bytes();digest=hashlib.sha256(source).hexdigest()
        fd,name=tempfile.mkstemp(prefix='.reset-',suffix='.db',dir=working.parent)
        temporary=Path(name)
        try:
            with os.fdopen(fd,'wb') as handle:
                handle.write(source);handle.flush();os.fsync(handle.fileno())
            with closing(sqlite3.connect(temporary.as_uri()+'?mode=ro',uri=True)) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise Rejected('Original copy failed integrity check')
                if db.execute('PRAGMA foreign_key_check').fetchall():raise Rejected('Original has broken foreign keys')
            _initialize_state()
            # Invalidate approvals BEFORE replacement; a crash cannot replay a pre-reset approval.
            with closing(sqlite3.connect(STATE_PATH)) as state:
                state.execute("UPDATE proposals SET status='invalidated' WHERE status='pending'")
                state.execute('UPDATE generation SET value=? WHERE id=1',(str(uuid4()),))
                state.commit()
            os.replace(temporary,working)
            dirfd=os.open(working.parent,os.O_RDONLY)
            try:os.fsync(dirfd)
            finally:os.close(dirfd)
            if working.read_bytes()!=source or hashlib.sha256(original.read_bytes()).hexdigest()!=digest:
                raise Rejected('Reset verification failed')
            return {'ok':True,'status':'reset','working_database':'data/campus_customs_new.db',
                    'sha256':digest,'original_unchanged':True,'pending_proposals_invalidated':True,'audit_preserved':True}
        finally:
            temporary.unlink(missing_ok=True)


def register_control_tools(server, token):
    """Private process capability supplied only by the API, never to model context."""
    def authorize(capability):
        if not token or not hmac.compare_digest(token,capability):raise PermissionError('Private API capability required')
    def wrap(fn):
        def safely(*args,**kwargs):
            try:return fn(*args,**kwargs)
            except Rejected as exc:return {'ok':False,'code':exc.code,'reason':str(exc)}
        return safely
    @server.tool()
    def control_get_state(capability: str) -> dict:
        authorize(capability);return wrap(get_review_state)()
    @server.tool()
    def control_stage_proposal(capability: str, candidate: dict, ticket_id: int, run_id: str, generation: str) -> dict:
        authorize(capability);return wrap(stage_proposal)(candidate,ticket_id,run_id,generation)
    @server.tool()
    def control_execute_payment(capability: str, proposal_id: str, reviewer: str, approved: bool,
                                next_due: str | None = None) -> dict:
        authorize(capability);return wrap(execute_proposal)(proposal_id,reviewer,approved,next_due)
    @server.tool()
    def control_reset(capability: str, confirmation: str) -> dict:
        authorize(capability);return wrap(reset_working_database)(confirmation)

    @server.tool()
    def control_complete_ticket101_operations(capability: str, run_id: str) -> dict:
        authorize(capability)
        from .completion import complete_ticket101
        return wrap(complete_ticket101)(run_id)

    @server.tool()
    def control_complete_ticket103_operations(capability: str, run_id: str, generation: str,
                                               report: dict, reports: list, evidence: dict) -> dict:
        authorize(capability)
        from .completion import complete_ticket103
        return wrap(complete_ticket103)(run_id,generation,report,reports,evidence)
