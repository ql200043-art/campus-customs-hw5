import unittest,tempfile,json
from pathlib import Path
from backend.runtime import RunState,RunStopped
from backend.audit import AuditTrail
from backend.models import Role
class CycleTests(unittest.TestCase):
 def test_skip_does_not_invoke_child_or_stop_but_budget_remains(self):
  with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'output') as temp:
   s=RunState(audit=AuditTrail(Path(temp)/'audit.json'))
   for i in range(8):self.assertFalse(s.delegate(Role.CUSTOMER_SERVICE,Role.BOSS,(Role.BOSS,Role.CUSTOMER_SERVICE)))
   self.assertFalse(s.stopped);self.assertEqual(s.agent_runs,0)
   records=json.loads(s.audit.path.read_text());self.assertEqual(records[0]['delegation_target'],'Boss')
   with self.assertRaises(RunStopped):s.delegate(Role.CUSTOMER_SERVICE,Role.BOSS,(Role.BOSS,Role.CUSTOMER_SERVICE))
 def test_depth_still_fails_closed(self):
  with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'output') as temp:
   s=RunState(audit=AuditTrail(Path(temp)/'audit.json'))
   with self.assertRaises(RunStopped):s.delegate(Role.ACCOUNTING,Role.FACILITIES,(Role.BOSS,Role.INVENTORY,Role.CUSTOMER_SERVICE,Role.ACCOUNTING))
