"""Fixed model and shared, whole-request limits; no model override/fallback."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = 'gpt-6-luna'
PORTKEY_URL = 'https://api.portkey.ai/v1'
MAX_AGENT_RUNS = 9
MAX_DELEGATIONS = 8
MAX_DEPTH = 3
MAX_MODEL_REQUESTS = 16
MAX_FUNCTION_CALLS = 40
MAX_MCP_CALLS = 24
MAX_RESULT_BYTES = 24000
MAX_TASK_CHARS = 2000
RUN_TIMEOUT_SECONDS = 180
MCP_TIMEOUT_SECONDS = 20
TOOL_NAMES = (
    'lookup_inventory', 'lookup_lease', 'lookup_pricing', 'get_shop_context',
    'list_tickets', 'get_ticket', 'list_vendors', 'get_vendor_status',
    'get_invoice', 'list_cash_accounts', 'list_payments', 'prepare_payment',
)
