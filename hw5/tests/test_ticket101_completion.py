"""Completion checks on disposable post-payment copies, never live mutations."""
import json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from mcp_server import database,control,completion
ROOT=Path(__file__).resolve().parents[1]
class CompletionTests(unittest.TestCase):
 def test_reject_and_complete_without_money_or_stock_changes(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'output') as tmp:
   p=Path(tmp)
   for name in ['campus_customs.db','campus_customs_new.db']:shutil.copyfile(ROOT/'data'/name,p/name)
   shutil.copyfile(control.STATE_PATH,p/'state.db');shutil.copyfile(completion.AUDIT_PATH,p/'audit.json')
   events=json.loads((p/'audit.json').read_text());run=next(e['run_id'] for e in reversed(events) if e['action']=='agent_complete' and e['active_agent']=='Boss')
   with patch.object(database,'DATABASE_PATH',p/'campus_customs_new.db'),patch.object(control,'STATE_PATH',p/'state.db'),patch.object(completion,'AUDIT_PATH',p/'audit.json'):
    with control.control_transaction() as db:
     db.execute("UPDATE tickets SET status='open',notes='Needs a tee in size S.' WHERE id=101")
    with self.assertRaises(control.Rejected):completion.complete_ticket101('nonexistent-run')
    with database.read_connection() as db:
     before={t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in ['inventory','payments','cash_accounts','invoices']}
    result=completion.complete_ticket101(run);self.assertTrue(result['changed']);self.assertFalse(result['physical_fulfillment_completed'])
    self.assertFalse(completion.complete_ticket101(run)['changed'])
    with database.read_connection() as db:
     after={t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in before}
     self.assertEqual(db.execute('SELECT status FROM tickets WHERE id=101').fetchone()[0],'closed')
    self.assertEqual(before,after)
