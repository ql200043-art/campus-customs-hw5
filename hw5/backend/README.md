# Campus Customs agent team and API — through Problem 7

`team.py` creates exactly five PydanticAI agents: Boss, Inventory, Accounting, Facilities and Customer Service. Their distinct instructions live in `prompts/`; structured models live in `models.py`. `runtime.py` holds shared counters and `audit.py` appends safe events. `mcp_connection.py` is a transport-only adapter to the existing FastMCP server; there is no second database-access layer. Problem 7 adds the FastAPI API in main.py.

## Model setup

Install `backend/requirements.txt` into the existing `mcp_server/.venv`. Set `PORTKEY_API_KEY` in your shell without committing it. `gateway.py` fixes the model to `gpt-6-luna`, authenticates to Portkey, disables retries and rejects any request directed to another host/endpoint/model. No model-name or base-URL environment override exists. The account must already have provider routing for that exact model; if needed, `PORTKEY_VIRTUAL_KEY` selects its stored provider credential. Problem 8 follow-up verified live account routing. All five agents set `openai_reasoning_effort: none` (sent as `reasoning_effort: none`): this account’s upstream rejects function tools with default reasoning on chat/completions. The sent model remains exactly `gpt-6-luna`. Missing keys fail at construction; there is no fallback.

For later authorized investigation, import `AgentTeam`, instantiate it, call `await team.run(task, role=Role.BOSS)` and finally `await team.close()`. Do not run all tickets automatically. The starting role is selectable. All five agents share `query_shop` (allowlisted MCP calls) and `delegate_task` (structured requests to any other role). The runtime supplies shop context through MCP at each agent invocation.

Whole-request bounds: 9 agent invocations, 8 delegations, depth 3, 16 model requests, 40 function calls, 24 MCP calls, 180 seconds. Active-role cycles are blocked. Reports are evidence-cited recommendations with optional customer drafts and pending payment proposals; they are not execution records. Bounded fields and result caps are documented in `output/harness.md`.

## Payment safety

The only payment tool prepares a read-only proposal and refuses insufficient funds or ambiguous duplicates. `PaymentReviewRequest` is pending-only and carries a proposal fingerprint/run ID for a future human interface. `payment_boundary.execute_payment` always refuses execution and is not an agent tool. Those restrictions remain on the agent-facing connection. Problem 7 adds a separate human-only control path described below; no customer-email or vendor contact capability exists. See the Problem 7 section below for the separate local-human approval and atomic-transaction path.

## Validation

From Homework 5: `mcp_server/.venv/bin/python -m unittest discover -s tests -v`.

These checks use actual PydanticAI construction and MCP subprocess reads, plus mocked HTTP responses for `gpt-6-luna` (no live network inference). A small specialist-to-specialist loop stops after validation. Safety fixtures mutate only a temporary in-memory database, never the shop files. The shared audit log is append-only; tests also append explicitly validation-related events. Real-world UTC audit timestamps are separate from desk.date_today.

## Problem 7: start the API

From the Homework 5 `backend/` folder, activate the installed environment once:

```sh
source ../mcp_server/.venv/bin/activate
```

Then use exactly:

```sh
uvicorn main:app --reload --port 8000
```

API: `http://localhost:8000`; interactive API documentation: `http://localhost:8000/docs`.
No key is required for read routes or startup. Agent inference requires `PORTKEY_API_KEY` and the existing Portkey routing; only `gpt-6-luna` is configured. Startup never resets or runs agents.

| Method | Path | Purpose |
|---|---|---|
| GET | /api/tickets | Return tickets 101–103 from MCP, original fields plus is_open/is_resolved/resolution_state. |
| POST | /api/tickets/{ticket_id}/run | Investigate one open ticket with the existing five-agent team; stage verified proposals for review only. |
| GET | /api/events | Last 1–200 existing audit events (default 50), optional run_id filter; no private reasoning. |
| GET | /api/proposals | Durable pending/executed proposals in the current reset generation, bounded to 200 with truncation indicator. |
| POST | /api/approvals/{proposal_id} | Explicit local-human approval of an existing pending proposal; transactional execution after revalidation. |
| GET | /api/cash | Current checking balance and recorded date from MCP. |
| POST | /api/reset | Explicitly restore only the working database from the original, invalidate pending approvals, preserve audit history. |

The run response includes an agent report, stop/status fields, pending proposal queue IDs and any proposal rejection reasons. A queue ID (UUID) is distinct from the model-visible source fingerprint. Only IDs returned in pending_proposals or GET /api/proposals can be submitted for approval. Unknown tickets/proposals return 404; invalid bodies 422; explicit disapproval 400; stale/duplicate/insufficient-funds conflicts 409; missing provider configuration or infrastructure failures 503. A blocked agent recommendation is returned as structured data without making business changes.

Human invoice approval body:

```json
{"approved": true, "reviewer": "Your actual name"}
```

Human rent approval additionally requires `next_due`, a human-confirmed ISO date after the recorded period and simulated shop date. The API does not guess a calendar/lease policy. For the current lease, a reviewer could confirm `2026-10-02` if that is the intended next period; this is not an automatic approval or date default.

Reset body:

```json
{"confirmation": "RESET_WORKING_DATABASE"}
```

## Human boundary and data consistency

This is a trusted local-operator API, not a production identity system. The explicit POST approval plus strict boolean and reviewer name is the human action; the name is recorded, not externally authenticated. CORS permits only localhost/127.0.0.1 Vite origins on port 5173. Unexpected browser origins cannot POST. Uvicorn binds loopback by default. Do not deploy this API publicly without real authentication/authorization.

Agents retain their original 12 read-only tools and cannot access control operations. FastAPI launches the same MCP module in a private control mode using a random in-process capability passed only to its subprocess. No secret is put into prompts, ordinary agent tools, Codex config or audit. Shop SQL remains exclusively in mcp_server/. No second agent architecture is introduced.

`output/payment_review_state.db` stores proposal/replay metadata and durable receipts; it is not a replacement shop database. Staging independently verifies each proposed field against MCP-side live facts and never trusts model claims of approval. Execution locks the shop and rechecks pending state, ticket linkage, invoice/vendor or lease state, shop date, exact snapshot, duplicates and cash in one transaction. The working DB and attached receipt database use rollback journals and FULL synchronization. Cash debit, payment insert, invoice/lease update, applicable rent-ticket closure and proposal consumption commit together or roll back.

An invoice payment sets invoice status to paid but leaves customer ticket 101 open: it does not replenish stock. Rent payment records the human-confirmed next_due and closes only the linked rent_notice ticket. No inventory is changed, income invented, customer contacted or vendor contacted. Existing payment references are treated conservatively: because this schema lacks rent billing periods and enforced polymorphic reference types, ambiguous historical references require review rather than risk double payment. Arbitrary purchase orders are unsupported because no such proposal/tool/table exists.

Reset verifies an exact temporary copy of the original, takes an exclusive file lock, invalidates old pending approvals, and atomically replaces only the working file. It rejects unexpected database sidecars and never runs on startup. A generation token rejects proposals left over from a pre-reset run. The original and append-only JSON audit remain intact. Historical execution receipts remain in control metadata even after reset.

## Validation

`../mcp_server/.venv/bin/python -m unittest discover -s ../tests -v` from backend, or run discovery from the Homework 5 root as before. Payment/reset tests use disposable copies under output and clean them up. The route test uses a mock of the SAME team's interface, actual MCP protocol calls and no live inference. Real HTTP reads were also checked at localhost:8000. See output/problem7_validation.json and output/problem7_http_smoke.json.
