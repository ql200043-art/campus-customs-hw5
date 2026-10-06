# Homework 5 — Campus Customs Multi-Agent Operations

Completed Problems 1–11. The submission lives in the repository's `hw5/` directory. Run all setup commands from there unless another directory is shown.

## Completed state and evidence

Tickets 101, 102 and 103 are closed; open tickets and pending proposals are zero. Checking is **160.00**: starting 3400.00 less the human-approved invoice payment of 840.00 and rent payment of 2400.00. Ticket 101 closed as an operations investigation without physical fulfillment; Ticket 103 closed as a supported decline, without a discount, stock change or payment.

- `data/campus_customs.db` is the untouched original. SHA-256: `23686a90d698f7fa6f901a3f0a9774db9cbb31e13151c9e5717275f3321f360a`.
- `data/campus_customs_new.db` contains the completed real run. **Do not copy over it during installation.** Both databases are deliberately included.
- Open `output/desk_tickets.html` locally for the preserved Expected plans, final Actual results, Cash reconciliation and completed Reflection.
- `output/resolved_board.html` references three real dashboard images in `output/screenshots/`; keep that folder beside the page.
- `output/resolved_tickets.json` contains agent contributions and executed human-approval receipts. `output/audit_trail.json` preserves all real and labeled validation events; never truncate it.
- `output/harness.md` documents schema, tools, agents, API, limits and safeguards. `AI_prompts.md` records the student's prompts.

## Requirements and installation

Use macOS/Linux or WSL (the implementation uses `fcntl`), Python **3.11+** (validated with 3.14.7), and Node **22.12+** (validated with 24.20.0). Use the committed npm lockfile. No model calls are made during installation or API startup.

```sh
# From the cloned repository:
cd hw5
python3 -m venv mcp_server/.venv
source mcp_server/.venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# Edit .env locally to set your PORTKEY_API_KEY; never commit it.
set -a
source .env
set +a
cd frontend
npm ci
cd ..
```

The exact `mcp_server/.venv` location matters: the existing backend launches MCP with that interpreter. `.env` is not automatically loaded by the application; source it as shown before starting the backend. Only `PORTKEY_API_KEY` is required. Optional `PORTKEY_VIRTUAL_KEY` selects configured classroom routing if your Portkey account requires it. All five agents use only `gpt-6-luna` via `https://api.portkey.ai/v1` with OpenAI-compatible chat/completions, provider header `openai`, and `reasoning_effort=none`. The account must have access to that route. No direct OpenAI key or alternate model is used.

## Start the application

In the activated, configured terminal:

```sh
cd backend
uvicorn main:app --reload --port 8000
```

API: http://localhost:8000; API documentation: http://localhost:8000/docs. Startup never resets data or runs agents.

In another terminal:

```sh
cd hw5/frontend  # relative to the repository root
npm run dev
```

Open **http://localhost:5173**. Local Vite CORS is configured. The queue should show all tickets resolved and checking 160.00. A refreshed browser's Run brief may say “Awaiting a run” because it is transient UI state; closed ticket state and the preserved audit are authoritative. Do not rerun tickets merely to populate that brief.

The backend automatically launches the FastMCP server through stdio; **no separate MCP daemon is needed**. For a compatible MCP client, activate the environment and launch from `hw5/` with `python -m mcp_server.server`. `.mcp.json` supplies that stdio command for clients supporting this format. The public connection exposes 12 factual/proposal tools. Private capability-protected backend control mode adds six tools and is unavailable to agents.

Codex uses `.codex/config.toml`, not `.mcp.json`. The submission includes a portable config that assumes `hw5/` as cwd and the environment activated. From there, `python -m mcp_server.codex_project` explicitly loads that project entry. The original local absolute-path config is preserved outside the submission checkout.

## Human control and optional fresh demonstration

Agents can prepare proposals but cannot approve or execute them. A human reviews the proposal in the dashboard and explicitly approves through `POST /api/approvals/{proposal_id}`. Execution rechecks the current obligation, cash, reset generation and duplicates, then updates records atomically. Rent additionally needs a human-confirmed next due date. No negative balance, customer email, vendor contact or invented receipt is permitted. This is a trusted **local** operator API, not a publicly hosted production backend.

Local proposal/replay metadata (`output/payment_review_state.db`) is intentionally excluded from Git as runtime state. On a clean clone it initializes with no pending proposals. Existing executed payments remain in the working database; their receipts and approval evidence are preserved in resolved_tickets.json and the audit. The clone does not pretend those historical proposals are newly pending. Starting a fresh demonstration creates new metadata; do not try to replay historical approvals.

To deliberately start a new demonstration, first preserve any evidence you wish to keep, then use **Reset working database** in the dashboard and confirm. The API route is `POST /api/reset` with `{"confirmation":"RESET_WORKING_DATABASE"}`. It safely restores only the working database from the original, invalidates pending proposals and preserves audit history. This is the supported equivalent of copying the original over the working copy; do not overwrite a live database manually. Reset before a fresh full three-ticket run, then process tickets one at a time and approve payments yourself. This submission was **not reset**.

## Validation and submission

`npm run build` in frontend verifies the production bundle. Backend import/lifespan and `/openapi.json` can be checked without a model key or agent execution. The broader development tests are retained as reference; some assume original starting data or append audit events, so do not run the entire suite against preserved submission evidence. Payment/reset fixtures use temporary copies.

Only source, setup files, required databases, final deliverables, screenshots and tests are submitted. Secrets, virtual environments, npm caches, build products, temporary diagnostics, local locks and proposal metadata are excluded. The public URL is in `output/github_url.txt`. A `hw5.zip` generated from the final Git commit is kept locally beside the submission checkout and is not committed.
