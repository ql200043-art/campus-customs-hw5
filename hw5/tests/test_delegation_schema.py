import asyncio,unittest
from unittest.mock import patch
from pydantic import ValidationError
from backend.models import DelegationRequest,Role
from backend.gateway import safe_validation_diagnostics
from backend.team import AgentTeam
class DelegationSchemaTests(unittest.IsolatedAsyncioTestCase):
 async def test_provider_strict_schema_and_roles(self):
  with patch.dict('os.environ',{'PORTKEY_API_KEY':'offline-placeholder'}):team=AgentTeam()
  try:
   for agent in team.agents.values():
    tool=agent._function_toolset.tools['delegate_task']
    self.assertTrue(tool.strict)
    self.assertEqual(tool.function_schema.json_schema['$defs']['Role']['enum'],[r.value for r in Role])
   with self.assertRaises(ValidationError) as caught:DelegationRequest(target='NOT_A_ROLE',task='test')
   diag=safe_validation_diagnostics(caught.exception)
   self.assertIn('target:enum',diag);self.assertNotIn('NOT_A_ROLE',diag)
  finally:await team.close()
