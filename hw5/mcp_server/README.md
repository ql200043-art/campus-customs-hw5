# Campus Customs MCP server — through Problem 7

The existing FastMCP server supplies verified shop facts and read-only payment proposals to the five-agent team and Codex. It operates only on `data/campus_customs_new.db`. The original `data/campus_customs.db` remains untouched. The three Problem 3 tools retain their names, inputs and output structure.

## Complete tool list (12 tools)

| MCP tool | Tables read | Purpose / ticket | Expected users | Mode | Safety |
|---|---|---|---|---|---|
| `lookup_inventory` | inventory | Exact SKU/size availability and location for tickets 101 and 103. | Inventory, Customer Service, Boss | Read-only | Bound parameters; zero stock is a found row; no reservation. |
| `lookup_lease` | leases | Lease facts for ticket 102 via tickets.lease_id. | Facilities, Accounting, Boss | Read-only | No invented terms or due-date advancement. |
| `lookup_pricing` | pricing | Recorded SKU cost/list price for ticket 103 and tee quote context. | Accounting, Boss, Customer Service | Read-only | Per SKU, not size; no discount authorization. |
| `get_shop_context` | desk | Authoritative simulated today for all three tickets. | All five | Read-only | Require exactly one row and a valid ISO date; otherwise stop. |
| `list_tickets` | tickets | List open requests so Boss can route current work. | Boss; all five may inspect | Read-only | Exact open/closed status filter; 1–25 rows, explicit truncation. |
| `get_ticket` | tickets | Read full ticket details and lease/invoice/product references. | All five | Read-only | Not-found is explicit; no status changes. |
| `list_vendors` | vendors | Recorded supplier capabilities and lead_days for replenishment. | Inventory, Accounting, Boss | Read-only | 1–25 rows; specialty does not prove SKU suitability. |
| `get_vendor_status` | vendors, invoices | Expose the vendor invoice shipping blocker relevant to ticket 101. | Inventory, Accounting, Boss | Read-only | Any open invoice blocks shipping; display ≤25 invoices; no shipping promise. |
| `get_invoice` | invoices | Read ticket 101’s linked invoice and vendor_id. | Accounting, Inventory, Boss | Read-only | Missing invoice stops dependent action; no status change. |
| `list_cash_accounts` | cash_accounts | Discover actual account names/balances for rent and invoice proposals. | Accounting, Boss; Facilities may inspect | Read-only | 1–25 rows; never assume unrecorded income or account availability. |
| `list_payments` | payments | Review recorded payment history for invoice/rent duplicate checks. | Accounting, Facilities, Boss | Read-only | 1–25 rows; kind/ref_id links are inferred; no billing-period field. |
| `prepare_payment` | desk, invoices, vendors, leases, cash_accounts, payments | Prepare invoice/rent payment review for tickets 101/102 from stored obligation amounts. | Accounting, Boss; all five may propose for review | Read-only | Read-only proposal; reject insufficient cash, nonpositive/invalid amounts, ambiguous duplicates or missing data; no approval, reservation or execution. |

The public/agent connection still has **no mutating MCP tools**; the separate Problem 7 human-control mode is described below. Read connections enforce SQLite `mode=ro` and `query_only=ON`, reject aliases/hardlinks to the original, never create a missing database, and close after a consistent snapshot. All SQL is internal and parameterized; there is no agent-accessible SQL endpoint. `tools.py` registers the original three plus the nine functions in `operations.py`.

Single-row lookups return `found` and `record` (or a not-found message). Lists return `records` and `truncated`. Vendor status includes actual open invoices and an explicit policy-derived shipping blocker. Dates/amounts are stored facts; no stock receipt, purchase order, discount or message is fabricated. The new proposals use Decimal calculations rather than float subtraction. All agents must use `desk.date_today` for operational dates.

## Payment boundary

`prepare_payment(kind, ref_id, account)` supports `invoice` and `rent`. It derives amount/payee/due date from the obligation, rejects missing/ambiguous dates, non-open invoices, invalid money, insufficient cash and any previous matching payment reference. The latter is conservative because rent periods and payment reference types are not enforced by the schema. It returns a fingerprinted proposal with `human_approval_required=true` and `execution_enabled=false`. It does not reserve funds or persist a business record.

There is no execution tool on the public/agent connection and no agent phrase that grants approval. `backend/payment_boundary.py` fails closed even when passed a review object. Problem 7 adds an explicit local-human approval route and a private transactional writer (see below). That writer must re-read the obligation and balance, bind approval to the exact proposal and reviewer, prevent replay/duplicates, conditionally debit only sufficient cash, insert a payment with the true approver, update the invoice or verified lease period, and commit atomically or roll back. The agent-visible `execution_enabled` field remains false; the separate approval API is required.

## Setup and checks

Use the existing environment from Homework 5; Python 3.11+ is required by the new project code (validated with Python 3.14):

```sh
mcp_server/.venv/bin/python -m pip install -r backend/requirements.txt
mcp_server/.venv/bin/python -m unittest discover -s tests -v
mcp_server/.venv/bin/python -m mcp_server.validate
```

Unit tests construct actual PydanticAI agents and use mocked HTTP responses for the fixed model, plus real stdio MCP read calls. No live inference, real approvals, real DB mutations or full ticket run occurs. Safety fixtures change only an in-memory clone. See `backend/README.md` for model settings and runtime bounds.

## Codex connection preserved from Problem 4

`.codex/config.toml` still configures `campus_customs` using the local Python environment, `-m mcp_server.server` and Homework 5 as cwd. Codex's untrusted-folder behavior is unchanged; the project-scoped launcher explicitly loads only this entry without global trust/config changes:

```sh
mcp_server/.venv/bin/python -m mcp_server.codex_project
```

Repeat the actual Codex MCP smoke check with `mcp_server/.venv/bin/python -m mcp_server.smoke_codex`. The updated checker permits additional tools and writes `output/mcp_smoke_problem5.json`, preserving the original `output/mcp_smoke.json` from Problem 4. It uses an ephemeral Codex app-server thread without inference, calls the original three tools through MCP, checks SQLite afterward and stops the process. Temporary Codex state remains under `output/.codex-runtime/`.

For later authorized use, `mcp_server/.venv/bin/python -m mcp_server.server` starts stdio. No HTTP/FastAPI server or React dashboard is included.

References: [FastMCP tools](https://github.com/prefecthq/fastmcp/blob/main/docs/servers/tools.mdx), [Codex MCP configuration](https://developers.openai.com/codex/mcp).

## Problem 7: private human-control mode

The public default and Codex connection still register exactly the 12 tools above. FastAPI can launch the same `mcp_server.server` module with `--control` and a private `CC_CONTROL_TOKEN`. Only that private connection additionally registers:

- `control_get_state`: read bounded proposal/receipt metadata and reset generation; creates the metadata schema on first use.
- `control_stage_proposal`: independently revalidate an agent-prepared invoice/rent proposal, then persist pending metadata (no shop-record change).
- `control_execute_payment`: require the API capability, explicit human approval and an existing pending proposal; transactionally debit cash, record payment, update invoice or lease and the applicable rent ticket, and consume the proposal.
- `control_reset`: require explicit reset confirmation; invalidate pending proposals and atomically restore only the working DB from the untouched original.

These four are NOT present in agent discovery or the Codex public configuration. A process-only capability is not a login system; the API is for a trusted local human. Details, JSON bodies and local security scope are in backend/README.md. Direct backend/payment_boundary.execute_payment remains disabled, so agents cannot acquire a new execution interface by calling the old stub.

`database.py` now coordinates read/write/reset access with a file lock. `operations.payment_snapshot` is shared by the existing read-only proposal tool and transactional revalidation. `control.py` is the sole mutation layer. Metadata is in output/payment_review_state.db and attaches to the working DB transaction; existing shop tables/columns are preserved. Payments are assignment-ledger updates only, not real banking transfers. No generic purchase-order executor or vendor contact was invented.

Insufficient funds, stale facts, duplicate references, missing records, wrong ticket links and old reset generations fail closed. Rent requires a human-supplied next_due; invoice payment never implies stock receipt or customer-order completion. The supplied control tests execute/reset only temporary database copies.

### Ticket 101 operations completion (Problem 9)

Private MCP tool `control_complete_ticket101_operations(capability, run_id)` reads tickets, inventory, invoices, payments, cash_accounts, review receipts and completed audit evidence. It writes only ticket 101 status/notes in a transaction. It requires a completed post-payment Boss/Inventory/Customer Service investigation, matching human execution receipt, no pending review, no vendor invoice blocker, zero exact-variant stock and nonnegative cash. Closure means operations investigation complete, explicitly not physical fulfillment. No inventory or payment writes; unchanged agent-facing 12-tool list. Repeated completion of the same run is idempotent. The private capability is unavailable to agents.

### Ticket 103 terminal decline (Problem 9)

Private tool `control_complete_ticket103_operations(capability, run_id, generation, report, reports, evidence)` reads tickets, inventory, pricing, cash_accounts, proposal metadata and completed audit events. It requires completed Boss/Inventory/Accounting/Customer Service reports, a final declined_as_requested recommendation with no approval/payment requirement, a Customer Service draft, no pending proposal, matching current ticket/stock/pricing MCP evidence and unchanged reset generation. It writes only ticket 103 status and notes in a transaction. It does not apply a discount, change stock, execute a payment or contact anyone. Called by the existing backend run route only when the supported disposition is present; unsuccessful/incomplete runs remain open. Public agent tool list remains unchanged.
