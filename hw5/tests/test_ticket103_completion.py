"""Isolated fixtures only; never edit current shop records or append fake live events."""
import json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from mcp_server import database,control,completion
ROOT=Path(__file__).resolve().parents[1]
class DeclineTests(unittest.TestCase):
 def test_completed_decline_changes_only_ticket103_and_rejects_stale_evidence(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'output') as temp:
   p=Path(temp)
   for name in ['campus_customs.db','campus_customs_new.db']:shutil.copyfile(ROOT/'data'/name,p/name)
   shutil.copyfile(control.STATE_PATH,p/'state.db')
   with patch.object(database,'DATABASE_PATH',p/'campus_customs_new.db'),patch.object(control,'STATE_PATH',p/'state.db'),patch.object(completion,'AUDIT_PATH',p/'audit.json'):
    with control.control_transaction() as db:
     db.execute("UPDATE tickets SET status='open',notes='Fixture request' WHERE id=103")
    with database.read_connection() as db:
     before={t:[dict(r) for r in db.execute('SELECT * FROM '+t)] for t in ['tickets','inventory','pricing','payments','cash_accounts','invoices','leases']}
    ticket=next(r for r in before['tickets'] if r['id']==103);stock=next(r for r in before['inventory'] if r['sku']==ticket['sku'] and r['size']==ticket['size']);pricing=next(r for r in before['pricing'] if r['sku']==ticket['sku'])
    ev={};events=[{'run_id':'fixture','action':'agent_complete','active_agent':role} for role in ['Boss','Inventory','Accounting','Customer Service']]
    for i,(tool,row) in enumerate([('get_ticket',ticket),('lookup_inventory',stock),('lookup_pricing',pricing)]):
     key=f'fixture:mcp:{i}';ev[key]={'tool':tool,'data':{'record':row.copy()}};events.append({'run_id':'fixture','action':'mcp_result','mcp_tool':tool,'result_summary':'evidence='+key+'; found=True'})
    (p/'audit.json').write_text(json.dumps(events))
    generation=control.get_review_state()['generation'];report={'role':'Boss','status':'recommendation','disposition':'declined_as_requested','human_approval_required':False,'summary':'Fixture decline','customer_draft':'Fixture draft'};reports=[{'role':'Customer Service','customer_draft':'Fixture draft'}]
    ev['fixture:mcp:1']['data']['record']['qty']+=1
    with self.assertRaises(control.Rejected):completion.complete_ticket103('fixture',generation,report,reports,ev)
    ev['fixture:mcp:1']['data']['record']['qty']-=1
    with self.assertRaises(control.Rejected):completion.complete_ticket103('fixture',generation,{**report,'human_approval_required':True},reports,ev)
    self.assertTrue(completion.complete_ticket103('fixture',generation,report,reports,ev)['ok'])
    with database.read_connection() as db:
     after={t:[dict(r) for r in db.execute('SELECT * FROM '+t)] for t in before}
    for t in before:
     if t!='tickets':self.assertEqual(before[t],after[t])
    self.assertEqual([r for r in before['tickets'] if r['id']!=103],[r for r in after['tickets'] if r['id']!=103])
    self.assertEqual(next(r for r in after['tickets'] if r['id']==103)['status'],'closed')
