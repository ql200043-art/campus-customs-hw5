"""Safe diagnostics never copy provider body or credential values."""
import os
import unittest
from unittest.mock import patch
from pydantic_ai.exceptions import ModelHTTPError
from backend.gateway import safe_configuration, safe_http_failure

class DiagnosticsTests(unittest.TestCase):
    def test_http_error_summary_excludes_untrusted_body(self):
        error=ModelHTTPError(400,'gpt-6-luna',{'message':'secret-provider-body'})
        result=safe_http_failure(error)
        self.assertIn('HTTP 400',result)
        self.assertIn('invalid_request',result)
        self.assertNotIn('secret-provider-body',result)

    def test_configuration_records_only_key_presence(self):
        with patch.dict(os.environ,{'PORTKEY_API_KEY':'do-not-log-this-secret'}):
            result=safe_configuration()
        self.assertIn('PORTKEY_API_KEY_present=True',result)
        self.assertNotIn('do-not-log-this-secret',result)
