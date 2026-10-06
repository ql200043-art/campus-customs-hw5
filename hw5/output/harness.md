# Campus Customs operational harness

## Problem 2 — Study the Campus Customs Database

### Inspection scope and simulated date

Inspected the complete sqlite_schema, every application table’s columns and declared foreign keys, all current tickets, and representative rows through a SQLite URI with mode=ro. No operational writes were performed. Field meanings below are interpretations of the schema and current data, not additional enforced rules.

**Use desk.date_today = 2026-08-31 as the simulated current date for all later operational decisions, never the computer’s real-world date.** Due dates, lateness and lead-time assessments must use that value. desk currently has one row, but its schema does not enforce a singleton.

### Complete schema inventory

Nine application tables: `cash_accounts`, `desk`, `inventory`, `invoices`, `leases`, `payments`, `pricing`, `tickets`, `vendors`. No views or triggers exist. The only indexes are three SQLite automatic primary-key indexes on cash_accounts, inventory and pricing.

All tables are ordinary non-STRICT SQLite tables. There are no explicit CHECK constraints, DEFAULT values, or additional UNIQUE constraints. NOT NULL and primary-key/foreign-key constraints are detailed below. Types are declared SQLite affinities; dates are TEXT, money is REAL, and currency is not specified. Nonnegative quantities/amounts, permitted statuses, valid dates and human approvals are not enforced by this schema.

INTEGER PRIMARY KEY columns alias rowid and uniquely identify rows, despite PRAGMA reporting notnull=0. The TEXT PRIMARY KEY columns cash_accounts.name and pricing.sku lack explicit NOT NULL; ordinary SQLite rowid tables can therefore permit NULL in those keys. inventory’s composite key explicitly requires both components. All three declared foreign keys use NO ACTION for delete/update. Foreign-key enforcement is connection-specific; declarations alone do not guarantee future connections enforce them.

| Table | Current rows |
|---|---:|
| `cash_accounts` | 1 |
| `desk` | 1 |
| `inventory` | 10 |
| `invoices` | 1 |
| `leases` | 1 |
| `payments` | 0 |
| `pricing` | 4 |
| `tickets` | 3 |
| `vendors` | 3 |

### Table: `cash_accounts`

| Field | SQLite type | Constraints | Meaning |
|---|---|---|---|
| `name` | TEXT | PK | Account identifier/name. |
| `balance` | REAL | NOT NULL | Recorded available account balance. |
| `date` | TEXT | NOT NULL | Date associated with the recorded balance; inferred as its as-of date. |

**Agent relevance and relationships:** Accounting checks funding; Boss can consider competing obligations. Inferred: payments.account matches cash_accounts.name; no foreign key.

**Representative rows (read-only):**

```json
[
  {
    "name": "checking",
    "balance": 3400.0,
    "date": "2026-08-31"
  }
]
```

### Table: `desk`

| Field | SQLite type | Constraints | Meaning |
|---|---|---|---|
| `date_today` | TEXT | NOT NULL | Authoritative simulated shop current date. |
| `notes` | TEXT | Nullable | Optional shop-wide context or notes. |

**Agent relevance and relationships:** All agents must read date_today for time-sensitive decisions. It supplies shared temporal context to tickets, leases, invoices, cash accounts and payments without a join key.

**Representative rows (read-only):**

```json
[
  {
    "date_today": "2026-08-31",
    "notes": null
  }
]
```

### Table: `inventory`

| Field | SQLite type | Constraints | Meaning |
|---|---|---|---|
| `sku` | TEXT | PK component 1 of (sku, size); NOT NULL | Product identifier shared across sizes. |
| `name` | TEXT | NOT NULL | Product display name. |
| `size` | TEXT | PK component 2 of (sku, size); NOT NULL | Size or variant label. |
| `qty` | INTEGER | NOT NULL | Recorded on-hand unit count. |
| `location` | TEXT | NOT NULL | Physical storage location. |

**Agent relevance and relationships:** Inventory checks availability; Customer Service and Boss assess fulfillment. Inferred: tickets.(sku,size) matches inventory.(sku,size), and inventory.sku matches pricing.sku. No foreign keys are declared.

**Representative rows (read-only):**

```json
[
  {
    "sku": "CC-HOOD-NAVY",
    "name": "Basic Hoodie Big Yale",
    "size": "S",
    "qty": 4,
    "location": "Aisle A"
  },
  {
    "sku": "CC-HOOD-NAVY",
    "name": "Basic Hoodie Big Yale",
    "size": "M",
    "qty": 8,
    "location": "Aisle A"
  },
  {
    "sku": "CC-HOOD-NAVY",
    "name": "Basic Hoodie Big Yale",
    "size": "L",
    "qty": 14,
    "location": "Aisle A"
  }
]
```

### Table: `invoices`

| Field | SQLite type | Constraints | Meaning |
|---|---|---|---|
| `id` | INTEGER | PK | Invoice identifier. |
| `vendor_id` | INTEGER | NOT NULL; FK → vendors.id | Vendor owed money. |
| `amount` | REAL | NOT NULL | Invoice amount. |
| `due_date` | TEXT | NOT NULL | Payment due date. |
| `status` | TEXT | NOT NULL | Invoice workflow status; currently open. |
| `description` | TEXT | Nullable | Optional description of billed goods/services. |

**Agent relevance and relationships:** Accounting evaluates vendor obligations. Declared: vendor_id → vendors.id; tickets.invoice_id → invoices.id. Inferred: payments may reference invoices through kind/ref_id; description may mention a SKU but is not a structured product link.

**Representative rows (read-only):**

```json
[
  {
    "id": 501,
    "vendor_id": 1,
    "amount": 840.0,
    "due_date": "2026-08-28",
    "status": "open",
    "description": "Rush reprint CC-TEE-WHITE S"
  }
]
```

### Table: `leases`

| Field | SQLite type | Constraints | Meaning |
|---|---|---|---|
| `id` | INTEGER | PK | Lease identifier. |
| `space_name` | TEXT | NOT NULL | Name of rented premises. |
| `landlord` | TEXT | NOT NULL | Landlord name. |
| `monthly_rent` | REAL | NOT NULL | Recurring monthly rent amount. |
| `next_due` | TEXT | NOT NULL | Next rent due date. |
| `notes` | TEXT | Nullable | Optional lease context. |

**Agent relevance and relationships:** Facilities tracks premises and rent; Accounting evaluates payment. Declared incoming relationship: tickets.lease_id → leases.id. Inferred: payments.kind/ref_id may identify a lease; landlord text may match a ticket requester.

**Representative rows (read-only):**

```json
[
  {
    "id": 1,
    "space_name": "Chapel Street shop",
    "landlord": "Elm City Properties",
    "monthly_rent": 2400.0,
    "next_due": "2026-09-02",
    "notes": null
  }
]
```

### Table: `payments`

| Field | SQLite type | Constraints | Meaning |
|---|---|---|---|
| `id` | INTEGER | PK | Payment identifier. |
| `kind` | TEXT | NOT NULL | Payment category; intended values are not defined by the schema. |
| `ref_id` | INTEGER | Nullable | Optional business-object reference, interpreted with kind; target is not declared. |
| `amount` | REAL | NOT NULL | Paid amount. |
| `account` | TEXT | NOT NULL | Account used for payment. |
| `paid_at` | TEXT | NOT NULL | Payment date/time stored as text. |
| `approved_by` | TEXT | NOT NULL | Recorded approver identity; text alone does not enforce human approval. |

**Agent relevance and relationships:** Accounting would record approved payments and check for duplicates. Inferred: account → cash_accounts.name and kind/ref_id → a business object such as an invoice or lease. No foreign keys or approval enforcement exist; exact kind conventions remain to be defined in later problems.

**Representative rows (read-only):**

```json
[]
```

### Table: `pricing`

| Field | SQLite type | Constraints | Meaning |
|---|---|---|---|
| `sku` | TEXT | PK | Product identifier; pricing is per SKU, not per size. |
| `unit_cost` | REAL | NOT NULL | Recorded cost per unit. |
| `list_price` | REAL | NOT NULL | Listed selling price per unit. |

**Agent relevance and relationships:** Boss and Accounting assess discounts and margins; Customer Service can use approved pricing. Inferred: sku matches inventory.sku and tickets.sku. No foreign keys.

**Representative rows (read-only):**

```json
[
  {
    "sku": "CC-HOOD-NAVY",
    "unit_cost": 22.0,
    "list_price": 58.0
  },
  {
    "sku": "CC-TEE-WHITE",
    "unit_cost": 8.0,
    "list_price": 28.0
  },
  {
    "sku": "CC-HAT-BLUE",
    "unit_cost": 6.0,
    "list_price": 22.0
  }
]
```

### Table: `tickets`

| Field | SQLite type | Constraints | Meaning |
|---|---|---|---|
| `id` | INTEGER | PK | Ticket identifier. |
| `type` | TEXT | NOT NULL | Request category. |
| `requester` | TEXT | NOT NULL | Requester name. |
| `subject` | TEXT | NOT NULL | Short request subject. |
| `sku` | TEXT | Nullable | Optional related product SKU. |
| `size` | TEXT | Nullable | Optional requested size. |
| `qty` | INTEGER | Nullable | Optional requested unit count. |
| `lease_id` | INTEGER | Nullable; FK → leases.id | Optional related lease identifier. |
| `invoice_id` | INTEGER | Nullable; FK → invoices.id | Optional related invoice identifier. |
| `status` | TEXT | NOT NULL | Ticket workflow status; all three currently open. |
| `notes` | TEXT | Nullable | Optional request details. |
| `created_at` | TEXT | NOT NULL | Creation timestamp, including UTC offset in current rows. |

**Agent relevance and relationships:** Boss routes work to specialists; Customer Service tracks requests. Declared: lease_id → leases.id and invoice_id → invoices.id. Inferred: (sku,size) → inventory and sku → pricing. Requester is free text, not a customer/vendor foreign key.

**Representative rows (read-only):**

```json
[
  {
    "id": 101,
    "type": "customer_order",
    "requester": "Tauhid Zaman",
    "subject": "Bulldog tee",
    "sku": "CC-TEE-WHITE",
    "size": "S",
    "qty": 1,
    "lease_id": null,
    "invoice_id": 501,
    "status": "open",
    "notes": "Needs a tee in size S.",
    "created_at": "2026-08-31T09:15:00-04:00"
  },
  {
    "id": 102,
    "type": "rent_notice",
    "requester": "Elm City Properties",
    "subject": "Rent due",
    "sku": null,
    "size": null,
    "qty": null,
    "lease_id": 1,
    "invoice_id": null,
    "status": "open",
    "notes": "Email: shop rent due in 2 days.",
    "created_at": "2026-08-31T11:05:00-04:00"
  },
  {
    "id": 103,
    "type": "price_override",
    "requester": "Yale AI Club",
    "subject": "Bulk hoodie discount",
    "sku": "CC-HOOD-NAVY",
    "size": "M",
    "qty": 20,
    "lease_id": null,
    "invoice_id": null,
    "status": "open",
    "notes": "Student org wants 20 hoodies, size M, asking for a bulk discount.",
    "created_at": "2026-08-31T16:55:00-04:00"
  }
]
```

### Table: `vendors`

| Field | SQLite type | Constraints | Meaning |
|---|---|---|---|
| `id` | INTEGER | PK | Vendor identifier. |
| `name` | TEXT | NOT NULL | Vendor business name. |
| `specialty` | TEXT | NOT NULL | Description of vendor capabilities. |
| `lead_days` | INTEGER | NOT NULL | Recorded lead time in days; calendar/business-day convention is unspecified. |

**Agent relevance and relationships:** Inventory can assess supplier capabilities and lead time; Accounting identifies invoice payees. Declared incoming relationship: invoices.vendor_id → vendors.id. Specialty-based product suitability is inferred; no vendor-to-SKU mapping exists.

**Representative rows (read-only):**

```json
[
  {
    "id": 1,
    "name": "Bulldog Print Co",
    "specialty": "apparel reprint",
    "lead_days": 5
  },
  {
    "id": 2,
    "name": "Elm City Gifts",
    "specialty": "mugs and small goods",
    "lead_days": 3
  },
  {
    "id": 3,
    "name": "QuickShip CT",
    "specialty": "local courier",
    "lead_days": 1
  }
]
```

### The three open tickets — inspection only

#### Ticket 101 — Bulldog tee

```json
{
  "id": 101,
  "type": "customer_order",
  "requester": "Tauhid Zaman",
  "subject": "Bulldog tee",
  "sku": "CC-TEE-WHITE",
  "size": "S",
  "qty": 1,
  "lease_id": null,
  "invoice_id": 501,
  "status": "open",
  "notes": "Needs a tee in size S.",
  "created_at": "2026-08-31T09:15:00-04:00"
}
```

**Request and identifiers:** Tauhid Zaman requests one Classic Bulldog Tee, size S. Ticket id=101 identifies the request; sku=CC-TEE-WHITE and size=S identify the stock variant; invoice_id=501 identifies a related invoice. lease_id is NULL.

**Connected facts:** The inferred SKU/size match has qty=0 at Aisle B. pricing has unit_cost=8 and list_price=28. The declared invoice link reaches invoice 501, amount 840, status open, due 2026-08-28 (three days before the simulated date), described as “Rush reprint CC-TEE-WHITE S.” Its declared vendor_id=1 links to Bulldog Print Co, specialty apparel reprint, lead_days=5. The description’s product connection is inferred, not an invoice-to-inventory foreign key. checking has 3400 and payments is empty; these are business-context connections only.

**Checks before eventual resolution:** Verify physical availability/reservations and whether reprinted stock has arrived; confirm invoice validity, what quantity it covers, delivery timing, and whether it was paid outside this database. The invoice amount does not prove a quantity received. Confirm the customer’s fulfillment expectations. Any eventual payment needs funding/duplicate checks and human approval; paying an invoice alone does not prove stock is available.

**Most relevant role:** Customer Service owns the customer request, supported by Inventory for fulfillment and Accounting for invoice verification; Boss coordinates dependencies.

#### Ticket 102 — Rent due

```json
{
  "id": 102,
  "type": "rent_notice",
  "requester": "Elm City Properties",
  "subject": "Rent due",
  "sku": null,
  "size": null,
  "qty": null,
  "lease_id": 1,
  "invoice_id": null,
  "status": "open",
  "notes": "Email: shop rent due in 2 days.",
  "created_at": "2026-08-31T11:05:00-04:00"
}
```

**Request and identifiers:** Elm City Properties reports rent due in two days. Ticket id=102 and lease_id=1 identify the request and premises obligation. Product fields and invoice_id are NULL.

**Connected facts:** The declared lease link reaches Chapel Street shop, landlord Elm City Properties, monthly_rent=2400, next_due=2026-09-02. This is two days after desk.date_today, consistent with the ticket note. checking has 3400 dated 2026-08-31 and no payments are recorded. Account and potential payment links are inferred, not declared foreign keys.

**Checks before eventual resolution:** Verify the lease, amount, due date, current balance and whether rent is already paid elsewhere; look for duplicate payments and competing obligations, including the 840 invoice. The two recorded obligations total 3240, leaving 160 arithmetically, but this is not payment authorization or proof that all commitments are represented. Obtain human approval before any later payment.

**Most relevant role:** Facilities handles the lease/rent issue, with Accounting for funding and payment review and Boss for prioritization.

#### Ticket 103 — Bulk hoodie discount

```json
{
  "id": 103,
  "type": "price_override",
  "requester": "Yale AI Club",
  "subject": "Bulk hoodie discount",
  "sku": "CC-HOOD-NAVY",
  "size": "M",
  "qty": 20,
  "lease_id": null,
  "invoice_id": null,
  "status": "open",
  "notes": "Student org wants 20 hoodies, size M, asking for a bulk discount.",
  "created_at": "2026-08-31T16:55:00-04:00"
}
```

**Request and identifiers:** Yale AI Club requests a bulk discount for 20 navy hoodies in size M. Ticket id=103, sku=CC-HOOD-NAVY, size=M and qty=20 identify the request and product variant. Both lease_id and invoice_id are NULL.

**Connected facts:** Inferred inventory match: Basic Hoodie Big Yale, size M, qty=8 at Aisle A, a shortage of 12 against the request. pricing gives unit_cost=22 and list_price=58. For 20 units, listed revenue would be 1160 and recorded unit-cost total 440, a difference of 720 before other costs and any discount. Neither this arithmetic nor list price establishes an approved discount. vendors can provide capability/lead-time context, but no schema link identifies a hoodie supplier.

**Checks before eventual resolution:** Verify available stock and reservations, replenishment feasibility and timing, the customer’s deadline and requested discount, current costs, minimum-margin/discount policy and approval authority. No discount percentage or promised delivery date is present. Specialty text alone does not confirm a vendor can supply this exact hoodie.

**Most relevant role:** Boss evaluates the price exception, supported by Accounting for margin analysis, Inventory for supply and Customer Service for request details.

### Exact schema DDL

```sql
CREATE TABLE cash_accounts (
            name TEXT PRIMARY KEY,
            balance REAL NOT NULL,
            date TEXT NOT NULL
        );
CREATE TABLE desk (
            date_today TEXT NOT NULL,
            notes TEXT
        );
CREATE TABLE inventory (
            sku TEXT NOT NULL,
            name TEXT NOT NULL,
            size TEXT NOT NULL,
            qty INTEGER NOT NULL,
            location TEXT NOT NULL,
            PRIMARY KEY (sku, size)
        );
CREATE TABLE invoices (
            id INTEGER PRIMARY KEY,
            vendor_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            due_date TEXT NOT NULL,
            status TEXT NOT NULL,
            description TEXT,
            FOREIGN KEY (vendor_id) REFERENCES vendors(id)
        );
CREATE TABLE leases (
            id INTEGER PRIMARY KEY,
            space_name TEXT NOT NULL,
            landlord TEXT NOT NULL,
            monthly_rent REAL NOT NULL,
            next_due TEXT NOT NULL,
            notes TEXT
        );
CREATE TABLE payments (
            id INTEGER PRIMARY KEY,
            kind TEXT NOT NULL,
            ref_id INTEGER,
            amount REAL NOT NULL,
            account TEXT NOT NULL,
            paid_at TEXT NOT NULL,
            approved_by TEXT NOT NULL
        );
CREATE TABLE pricing (
            sku TEXT PRIMARY KEY,
            unit_cost REAL NOT NULL,
            list_price REAL NOT NULL
        );
CREATE TABLE tickets (
            id INTEGER PRIMARY KEY,
            type TEXT NOT NULL,
            requester TEXT NOT NULL,
            subject TEXT NOT NULL,
            sku TEXT,
            size TEXT,
            qty INTEGER,
            lease_id INTEGER,
            invoice_id INTEGER,
            status TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (lease_id) REFERENCES leases(id),
            FOREIGN KEY (invoice_id) REFERENCES invoices(id)
        );
CREATE TABLE vendors (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            specialty TEXT NOT NULL,
            lead_days INTEGER NOT NULL
        );
```

### Validation and boundaries

- Original SHA-256 before and after inspection/copy: `23686a90d698f7fa6f901a3f0a9774db9cbb31e13151c9e5717275f3321f360a`.
- Working-copy SHA-256: `23686a90d698f7fa6f901a3f0a9774db9cbb31e13151c9e5717275f3321f360a`; byte-for-byte equality verified.
- Original and copy size: 53,248 bytes each.
- SQLite integrity_check returned ok; foreign_key_check returned no violations.
- Nine application tables and three open tickets (101, 102, 103) verified.
- No tickets, statuses, payments, inventory or other business records changed in either database.
- Future work must use data/campus_customs_new.db and preserve data/campus_customs.db.
- Later agents: Boss, Inventory, Accounting, Facilities and Customer Service; only gpt-6-luna through Portkey using PORTKEY_API_KEY. Payments require human approval; no actual customer emails or vendor contact.
- No server, backend, dashboard or agents were built. Problem 3 was not started.

## Problem 3 — Build the MCP Server

Implemented exactly three read-only tools using FastMCP 3.4.8. Before implementation, inspected the actual inventory, leases, pricing and tickets schemas and rows in the working database. The server connects only to `data/campus_customs_new.db` using SQLite `mode=ro` and `query_only=ON`; all lookup values use bound parameters. It refuses a working path that aliases the original and never creates a missing database.

| Tool | Table | Ticket | Why this tool is appropriate |
|---|---|---|---|
| `lookup_inventory(sku, size)` | `inventory` | 101 — Bulldog tee | Looking up the ticket's `CC-TEE-WHITE`, size `S`, reveals recorded quantity 0 at Aisle B, establishing the stock issue that must be investigated before fulfillment. |
| `lookup_lease(lease_id)` | `leases` | 102 — Rent due | Looking up the ticket's declared foreign key `lease_id=1` identifies Chapel Street shop, Elm City Properties, rent 2400 and next due date 2026-09-02. |
| `lookup_pricing(sku)` | `pricing` | 103 — Bulk hoodie discount | Looking up `CC-HOOD-NAVY` supplies stored unit cost 22 and list price 58 as factual inputs to a later discount decision without inventing or approving a discount. |

Inventory matching by SKU/size and pricing matching by SKU are inferred relationships, not declared ticket foreign keys. Pricing has no size field. Tools return stored columns unchanged, with `found: true` and `record`; a missing row returns `found: false`, `record: null` and a clear message. Zero stock remains a found row. Tools do not infer fulfillment, discount policy or payment authorization. Later date-sensitive decisions must use `desk.date_today`, not the computer date.

### Files and extension structure

- `mcp_server/__init__.py`: package marker.
- `mcp_server/database.py`: shared read-only connection and lookup helper.
- `mcp_server/tools.py`: the three lookup functions and registration function.
- `mcp_server/server.py`: FastMCP instance and guarded entry point; import does not run it.
- `mcp_server/requirements.txt`: pinned FastMCP version.
- `mcp_server/README.md`: purpose, tools, read-only behavior and offline validation instructions.
- `mcp_server/validate.py`: repeatable offline validation.
- `mcp_server/.gitignore`: excludes the local `.venv/` and Python bytecode.
- `AI_prompts.md`: exact Problem 3 prompt recorded; no follow-up needed.

Dependencies were installed in `mcp_server/.venv/`. Future tools can extend the registration function while preserving the existing functions. No agents or LLM calls are part of this problem.

### Offline validation results

Ran `mcp_server/.venv/bin/python -m mcp_server.validate` successfully:

- All source files compile and the real FastMCP server module imports.
- FastMCP's in-process `list_tools()` returns exactly the three names above, with read-only annotations.
- Called registered functions directly, using inputs read from tickets 101–103; results exactly match independent read-only SELECT queries for each real row.
- Missing-key and SQL-like input probes return clear not-found results; these probes are test inputs, not asserted operational facts.
- No transport was started, no MCP client connected, and no network listener was opened.
- Both databases retain SHA-256 `23686a90d698f7fa6f901a3f0a9774db9cbb31e13151c9e5717275f3321f360a`, matching the Problem 2 baseline before and after validation. No database writes or business-record changes occurred.
- No tickets were resolved. No agents, FastAPI backend or React dashboard were created. Problem 4 was not started.

Reference: [official FastMCP tool documentation](https://github.com/prefecthq/fastmcp/blob/main/docs/servers/tools.mdx).

## Problem 4 — Add the MCP Server to the Vibe Coder and Test Each Tool

Saved the project-scoped stdio server configuration in `.codex/config.toml` (`mcp_servers.campus_customs`). It launches `mcp_server/.venv/bin/python -m mcp_server.server` with Homework 5 as cwd and continues to use only `data/campus_customs_new.db`. This is the [documented Codex project configuration format](https://developers.openai.com/codex/mcp).

Codex currently treats this folder as untrusted and does not automatically load its local config. To keep configuration changes inside Homework 5, `mcp_server/codex_project.py` explicitly loads the local server settings as Codex CLI overrides. Launch with `mcp_server/.venv/bin/python -m mcp_server.codex_project`; no global configuration/trust edits are needed. Automatic loading in an ordinary Codex session still requires trusting/opening this folder; the current conversation was not hot-reloaded.

Actual discovery and calls succeeded using Codex app-server's `mcpServerStatus/list` and `mcpServer/tool/call` APIs over the configured stdio MCP connection. The vibe coder mapped the three exact natural-language requests to tool arguments; the server, not prior notes or direct SQL, supplied each answer. Codex reported the server as connected and discovered exactly the three tools. No LLM turn was run.

| Exact request | MCP tool and arguments | Actual result | Matches working DB |
|---|---|---|---|
| Check the inventory for SKU CC-TEE-WHITE in size S. | `lookup_inventory(sku="CC-TEE-WHITE", size="S")` | Classic Bulldog Tee, quantity 0, Aisle B | Yes |
| Look up lease 1. | `lookup_lease(lease_id=1)` | Chapel Street shop; Elm City Properties; monthly rent 2400; next due 2026-09-02; notes null | Yes |
| Look up the pricing for SKU CC-HOOD-NAVY. | `lookup_pricing(sku="CC-HOOD-NAVY")` | Unit cost 22; list price 58 | Yes |

`output/mcp_smoke.json` contains discovery evidence, prompts, arguments, complete actual MCP outputs, and independent validation. Only after all MCP calls finished were read-only SQLite comparisons performed. No expected-value discrepancy was found. Both databases retained SHA-256 `23686a90d698f7fa6f901a3f0a9774db9cbb31e13151c9e5717275f3321f360a`; no business records changed. The temporary app-server was stopped. No agents, backend, dashboard or resolution logic was created. Problem 5 was not started.

## Problem 5 — Build the Agent Team and Grow the MCP Tools

### Agent implementation and full connectivity

`backend/team.py` constructs exactly five PydanticAI `Agent` objects with `AgentReport` output and shared dependency/state models. `backend/models.py` defines role, delegation, evidence, report and pending-human-review structures. Each agent has its own detailed prompt under `backend/prompts/`. Agents return recommendations, never execution receipts.

Every agent has the same two runtime interfaces: `query_shop(tool, arguments)`, an allowlisted MCP transport adapter to all 12 tools below, and `delegate_task(DelegationRequest)`. Any role may directly invoke any of the other four (20 directed edges), including Inventory→Accounting, Facilities→Accounting, Customer Service→Inventory and any specialist→Boss. The common dispatcher validates the target, forbids self/active-path cycles, shares whole-request budgets and returns a structured specialist report. This is not a Boss-only tree. A maximum depth of three bounds any single chain, while sibling requests can reach other roles.

| Agent | Prompt file | Responsibilities / primary tables | Main MCP tools | May delegate to | Safety constraints |
|---|---|---|---|---|---|
| Boss | `backend/prompts/boss.md` | Route tickets, reconcile evidence, prioritize obligations and make final recommendations; tickets, desk and all specialist tables | list_tickets, get_ticket, get_shop_context; all other tools for verification | Inventory, Accounting, Facilities, Customer Service | No unsupported final decisions; human payment approval mandatory; never claim a recommendation executed |
| Inventory | `backend/prompts/inventory.md` | Exact SKU/size stock, shortages, replenishment facts, vendor capability/lead time; inventory, vendors, invoices, tickets, pricing, desk | lookup_inventory, list_vendors, get_vendor_status, get_invoice, get_ticket, lookup_pricing, get_shop_context | Boss, Accounting, Facilities, Customer Service | No SKU suitability from specialty alone; open invoices block shipping; no invented purchase order, arrival or receipt |
| Accounting | `backend/prompts/accounting.md` | Invoice/rent obligations, cash, duplicates, margin calculations and payment preparation; invoices, cash_accounts, payments, pricing, vendors, leases, desk, tickets | get_invoice, list_cash_accounts, list_payments, prepare_payment, lookup_pricing, get_vendor_status, lookup_lease, get_ticket, get_shop_context | Boss, Inventory, Facilities, Customer Service | Reject insufficient cash; cash only goes out; proposal is not approval; no payment execution |
| Facilities | `backend/prompts/facilities.md` | Premises, rent dates, property obligations; leases, tickets, desk, payments, cash_accounts | lookup_lease, get_ticket, get_shop_context, list_payments, list_cash_accounts, prepare_payment | Boss, Inventory, Accounting, Customer Service | Use simulated date; no invented lease terms/late fees; no landlord contact or premature due-date advancement |
| Customer Service | `backend/prompts/customer_service.md` | Understand requests and draft evidence-backed responses; tickets, inventory, pricing, desk, plus supporting invoices/vendors/leases | get_ticket, lookup_inventory, lookup_pricing, get_shop_context; other tools when specialist facts require verification | Boss, Inventory, Accounting, Facilities | Drafts only; no invented contact address, discounts, stock or arrival promises; protect unnecessary financial details |

The table lists typical use, not a narrower access restriction: **all five may call every read-only MCP tool**. Every invocation automatically reads the authoritative shop context through MCP before reasoning. `backend/mcp_connection.py` is transport only; it contains no SQLite or direct server calls. MCP replies receive run-scoped evidence IDs; reports must cite known IDs/tool names, and payment IDs must originate from the proposal tool. Citation checks detect nonexistent references but do not prove every sentence is semantically entailed; prompts and human review remain necessary.

### Complete MCP tool inventory

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

All 12 are read-only. `prepare_payment` creates only a returned review proposal, not a business record. There are no mutation, arbitrary-SQL, email, vendor-contact, ticket-close or purchase-order tools. The schema has no purchase-order, reservation, customer-contact or approval table; no such tables/fields were invented.

### Human approval and future execution contract

Payment readiness is checked in one read-only snapshot using the actual invoice/rent amount, named account, desk date and payment history. Missing records, non-open invoices, invalid/nonpositive/sub-cent monetary amounts, negative/insufficient cash and ambiguous matching historical payment references block proposals. A vendor's open invoice independently blocks shipping. No promised lead date is inferred from vendor capability text.

A proposal includes immutable-by-convention source fields, a SHA-256 fingerprint, current balance and calculated balance-if-paid. It requires human review and explicitly disables execution. `PaymentReviewRequest` is pending-only; `execute_payment` in `backend/payment_boundary.py` always raises and is not registered with MCP or any agent. An agent cannot create an approval token or mark a proposal approved. No approval was fabricated during validation.

A later authenticated human interface must bind reviewer identity and explicit consent to the exact proposal and use a separate guarded MCP transaction. That future writer must re-read live cash/obligation/desk facts, refuse stale or duplicate approvals, debit only when sufficient cash remains, insert the true approver in payments, and update the relevant invoice status or validated lease billing period atomically. Do not advance rent next_due by an invented calendar rule; this schema lacks a billing-period history. This contract is documented, not implemented prematurely. Multiple proposals do not reserve funds.

### Runtime specifications

| Setting | Enforced value / behavior |
|---|---|
| Model | Only `gpt-6-luna`; fixed in backend/settings.py; no alternate model/fallback |
| Gateway | `https://api.portkey.ai/v1`; `PORTKEY_API_KEY` required; request hook rejects a different host, endpoint or model |
| Credentials | Only Portkey credential path; optional PORTKEY_VIRTUAL_KEY selects existing stored provider credentials, not another model. No credentials saved or logged |
| Inference validation | No live calls; offline construction plus mocked responses for the same configured model. Portkey account routing/credential validity remains untested |
| Agent invocations | 9 total per root request including descendants |
| Delegations | 8 total; depth ≤3 edges; self-delegation and active-path cycles rejected |
| Model requests | 16 shared across the team; no HTTP retries; Pydantic retries=0 |
| Function calls | 40 shared PydanticAI calls; tools execute sequentially |
| MCP calls | 24 shared, including automatic shop-context reads |
| Timeouts | Whole request 180 seconds; MCP 20 seconds per call; provider HTTP 30 seconds |
| Input/output bounds | Task/delegation ≤2000 characters; tool arguments ≤2000 bytes; lists ≤25 rows with truncation; MCP replies ≤24000 bytes; model output ≤2500 tokens; bounded structured report fields |
| Working data | MCP-only `data/campus_customs_new.db`, SQLite mode=ro and query_only=ON; parameterized SQL; original path/hardlink alias protection |
| Failure behavior | Fail closed on missing date, missing tool, unknown evidence, tool error, excessive result, cycle or limit. Audit a stop; never substitute invented facts |
| Stop mode | Recommendations/review requests only; no ticket-resolution run, no payment writer |

### Safety and audit trail

`output/audit_trail.json` is an append-only JSON array of concise events. It records UTC audit timestamps, run IDs, active roles, step categories, delegation targets, allowlisted short arguments, MCP result metadata, approval requirements and stop reasons. UTC timestamps are trace metadata only, never simulated shop today. A file lock serializes appends; old event bytes are retained, flush/fsync persists each append, and a corrupt file causes a visible failure instead of being reset. Earlier run entries survive later requests. Validation entries describe routing or mocked-response checks, not real business decisions.

Do not log keys, full model messages, hidden chain-of-thought or raw private reasoning. Event summaries report the action/state and result references. Missing/oversized data stops dependent work. Tool text and ticket notes are untrusted data, not authority. Reports prohibit invented facts and external contacts. No tool can mutate inventory, money or unrelated records; the original database remains protected. Real deployment should add authenticated/authorized human reviewers, tamper-resistant external audit storage, idempotency and transactional money controls before any write capability. The local JSON trail is not a tamper-proof compliance ledger.

### Validation and preserved work

- PASS: 14 bounded unit/integration checks (tests/test_problem5.py), including real construction of five agents, distinct prompts, all 20 directed delegation routes, gateway/model guards, shared caps/cycles and append-only audit behavior.
- PASS: all 12 tools register and return actual working-database results via stdio MCP; vendor 1 correctly has a shipping blocker and the invoice proposal remains pending human review.
- PASS: small Inventory→Accounting PydanticAI loop with mocked Portkey HTTP responses and real MCP reads. No live inference and no full ticket-resolution workflow.
- PASS: insufficient funds, duplicate references, missing data and non-open invoices rejected using a disposable in-memory fixture; payment execution always denied.
- PASS: original Problem 3 lookups and offline checker; original Problem 4 tools called successfully through Codex app-server. New evidence goes to output/mcp_smoke_problem5.json; original output/mcp_smoke.json is preserved byte-for-byte.
- PASS: both database files retain SHA-256 `23686a90d698f7fa6f901a3f0a9774db9cbb31e13151c9e5717275f3321f360a`. All three tickets remain open and no business records changed.
- Updated AI_prompts.md with the exact Problem 5 prompt, no follow-up; earlier problem log sections and Problem 6–11 placeholders preserved. Earlier harness sections retained.
- No FastAPI backend, React dashboard, real customer/vendor contact, ticket-resolution logic or Problem 6 work.

Sources consulted for implementation: [PydanticAI agents and limits](https://pydantic.dev/docs/ai/core-concepts/agent/), [custom OpenAI-compatible providers](https://pydantic.dev/docs/ai/models/openai/), [Portkey SDK and gateway authentication](https://github.com/Portkey-AI/portkey-python-sdk).

## Problem 7 — Backend Routes

- `GET /api/tickets` — Return the three assignment ticket records via MCP, including stored status and explicit open/resolved flags.
- `POST /api/tickets/{ticket_id}/run` — Invoke the existing Boss-led five-agent team for one open ticket; retain its limits/model/MCP access, append audit events, and stage verified proposals without executing them.
- `GET /api/events` — Return recent existing audit events with bounded limit and optional run_id; high-level actions and tool activity only.
- `GET /api/proposals` — Return durable review proposals and receipts for the current reset generation (up to 200, with truncation indicated).
- `POST /api/approvals/{proposal_id}` — Explicit human approval and guarded transactional payment of a pre-existing pending invoice/rent proposal.
- `GET /api/cash` — Read the current checking balance/date via MCP, never a cache or hard-coded balance.
- `POST /api/reset` — Restore only campus_customs_new.db from campus_customs.db, invalidate old pending approvals and preserve audit history.

Start from `backend/`, with the existing virtual environment activated, using exactly `uvicorn main:app --reload --port 8000`. The API runs at `http://localhost:8000`; `/docs` exposes its schemas. Startup does not run agents, require inference credentials, execute payments or reset data. CORS permits only the local Vite origins `http://localhost:5173` and `http://127.0.0.1:5173` for GET/POST with Content-Type. Untrusted browser-origin POSTs are rejected.

### Human approval boundary

The API is a trusted local-human interface, not production authentication. Approval requires a strict boolean `approved: true`, a nonblank human `reviewer` and an existing pending proposal ID. Rent additionally requires an explicitly human-confirmed ISO `next_due` later than the old due date and simulated shop date. No lease recurrence policy is guessed. Model claims of approval are ignored; the run route only stages proposals. GET /api/proposals and run responses supply the queue IDs for later human review. Invoice/rent proposals are supported; arbitrary purchase orders are not invented because the existing tools/schema have no such proposal type.

The same MCP server has an API-only control mode with six additional tools: control_get_state (metadata read), control_stage_proposal (pending metadata write), control_execute_payment (transactional shop/receipt write), control_reset (working-copy restore and metadata invalidation), control_complete_ticket101_operations (evidence-checked operations closure), and control_complete_ticket103_operations (evidence-checked decline closure). This mode requires a random process capability that is never shared with the five agents. Their public connection and the Codex configuration still expose only the original 12 read-only tools. backend/api_mcp.py only transports MCP calls; SQL and shop mutations remain in mcp_server/control.py and database.py. The old direct agent payment boundary stays disabled.

Proposal state and receipts persist in output/payment_review_state.db. Fresh proposals are rederived from actual DB values before staging. At approval, a file lock and BEGIN IMMEDIATE transaction recheck pending generation, ticket/obligation linkage, open invoice and vendor, lease due date, authoritative desk date, cash snapshot and duplicate references. Invalid/insufficient cash is rejected before debit. The cash balance can never become negative through this writer. The conditional debit, payments insert (real reviewer; simulated paid_at), invoice/lease update, applicable rent-ticket closure and proposal consumption commit atomically across the attached rollback-journal databases. A failure rolls back everything. No income or stock is invented.

Invoice payment updates cash_accounts, payments and invoices but leaves customer ticket 101 open. Rent payment updates cash_accounts, payments, leases.next_due and only its linked rent_notice ticket to closed. Ticket 103 is unaffected. Pending snapshots become stale if cash or obligation facts change and must be prepared again. Existing payment references are conservatively rejected when their billing period/type is ambiguous, avoiding double payment. No contact is made with customers/vendors.

### Reset and validation

Reset requires `{"confirmation":"RESET_WORKING_DATABASE"}`. Under an exclusive lock it validates/fsyncs a temporary byte copy of the original, invalidates pending approvals with a new generation, and atomically replaces only data/campus_customs_new.db. Sidecar/journal ambiguity stops reset. The original DB and audit log are never reset or overwritten. Old approval IDs cannot be replayed into the fresh run; historical receipts remain in metadata.

Payment, concurrency, rollback and reset tests use temporary database copies under output, not the current Problem 6 state. Validation covers the seven routes, real MCP reads, mock team invocation, explicit human approval, stale/duplicate/insufficient-funds rejection, atomic invoice/rent updates, exact reset and original-file protection. Existing Problem 3–6 checks are retained. Live HTTP reads of tickets/cash/events passed after starting the exact Uvicorn command in backend/. No live gpt-6-luna call or full ticket-resolution run was made. Problem 8 was not started. See output/problem7_validation.json, problem7_http_smoke.json and problem7_test_output.txt.

Implementation references: [FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/) and [FastAPI TestClient](https://fastapi.tiangolo.com/reference/testclient/).

Final Problem 7 result: **27 tests passed, 0 failures, 0 errors**; original Problem 3 checker and live Codex MCP regression also passed. Both shop database hashes and the Problem 6 planning HTML remain unchanged. Updated the old Problem 5 test’s placeholder expectation to allow the completed Problem 6 prompt section; its original safety assertions remain in place. No live model inference was performed.

## Problem 8 — Agent Dashboard

React + Vite + TypeScript dashboard lives in `frontend/`; design notes are in `output/design.md`. Existing backend, MCP tools, model configuration and CORS were preserved without code changes.

| UI section/action | Existing API |
| --- | --- |
| Ticket queue and open/resolved status | `GET /api/tickets` |
| Selected ticket → Run agent team | `POST /api/tickets/{ticket_id}/run` |
| Activity timeline and per-agent completion summaries | `GET /api/events`; filtered by returned run ID after completion |
| Pending Human review cards | `GET /api/proposals` |
| Explicit named human confirmation | `POST /api/approvals/{proposal_id}` with `approved: true`; verified next due date required for rent |
| Checking balance, refreshed after approval | `GET /api/cash` |
| Separately confirmed reset | `POST /api/reset` with exact reset confirmation |

Start the backend from `backend/`: activate `../mcp_server/.venv`, then `uvicorn main:app --reload --port 8000`. From `frontend/`, use `npm ci` then `npm run dev`. Open `http://localhost:5173`; API stays at `http://localhost:8000`. No agent run occurs on startup. The frontend never accesses SQLite or Portkey directly and never infers ticket resolution or cash changes. In-flight audit history is desk-wide and polls every 2.5 seconds; completed views use a run-filtered window of up to 200 events. Human approvals and reset never automatically retry.

Validation: production build passed, six frontend component/API tests passed, and all 27 existing Problem 5–7 Python tests passed. Real browser checks loaded all three tickets, selected ticket 103, displayed audit events and checking balance 3,400.00. Four read-only HTTP routes and Vite CORS passed. Approval/payment/reset checks used isolated frontend fixtures and existing disposable-database backend tests; neither current shop database was mutated. No live model calls. SHA-256 evidence is in `output/problem8_validation.json`; test/build logs and read-only HTTP evidence have the `problem8_` prefix. Problem 9 was not started.

### Problem 8 follow-up — live Portkey failure

The original offline validation did not exercise the provider's function-tool/reasoning compatibility. Reproduction with the actual Boss schema returned HTTP 400 `invalid_request_error`: the upstream Azure OpenAI route rejects function tools with default reasoning for its internal `gpt-6-luna-global` deployment on chat/completions. The public request still sends exactly `gpt-6-luna`. A plain text probe succeeded, isolating the issue from credentials, network and MCP.

Minimal fix: all five agents now use PydanticAI `openai_reasoning_effort='none'`, which serializes as `reasoning_effort: 'none'`, as explicitly supported by the provider error. Endpoint remains `https://api.portkey.ai/v1/chat/completions`; `PORTKEY_API_KEY`, `x-portkey-api-key`, `x-portkey-provider: openai` and existing optional virtual-key behavior are unchanged. No provider keys or endpoint/model fallback were introduced. Installed PydanticAI 1.107.7, OpenAI SDK 3.24.0 and HTTPX 0.28.1 successfully completed live structured/tool responses without dependency changes.

Safe per-run configuration diagnostics record only key presence and fixed routing/settings. HTTP failures now preserve numeric status and a fixed error category, never raw provider bodies or credentials. The actual API process reported key present and virtual key absent; a separate smoke launched from the documented backend directory also inherited the correct environment.

Live validation: corrected structured smoke returned OK. Exactly one Ticket 103 backend-route run, `50d71fde-1caa-4507-869f-be9b2291c71d`, used 11 model requests and real MCP reads. Boss delegated to Inventory and Accounting; Inventory, Accounting and Boss all produced completion summaries. No HTTP/run failure occurred. Final report is business-blocked due to 8 recorded medium hoodies against 20 requested, unverified replenishment, and missing discount/approval policy. No payment proposals, approvals, payments, ticket closure or shop database changes occurred; checking remains 3400. Both database hashes stayed byte-identical. Evidence: `problem8_live_smoke.json`, `problem8_ticket103_live.json`, `problem8_live_events.json`, `problem8_live_validation.json`. All 29 regression/diagnostic tests passed, including an outgoing-request assertion for reasoning_effort none. Dashboard, API routes, MCP tools and approval safeguards are unchanged. Problem 9 was not started.

Diagnostic call accounting: before the final isolated structured smoke, the original plain-text probe succeeded, the original Boss tool schema reproduced HTTP 400, and two corrected Boss-only probes received live tool responses but their isolated test harness lacked tool dependencies. Those harness attempts were not ticket runs and performed no shop calls. The final isolated smoke used the same model/settings with a small output schema and succeeded; the full route validation then used the real team dependencies and MCP transport.

## Problem 9 — final completed system

All three tickets are closed, with zero open tickets and zero pending proposals. Checking reconciles 3400.00 − 840.00 − 2400.00 + 0.00 = **160.00**. Original database remains unchanged. The Expected sections in desk_tickets.html remain historical Problem 6 plans; Actual sections, resolved_tickets.json and real dashboard captures document final outcomes. Earlier debugging evidence remains in output/problem9 and the append-only audit, rather than being presented as current state.

### Full current MCP inventory

There are **18 tools in private control mode: 12 public tools plus 6 private tools**. The public agent/Codex connection exposes only the 12 public tools. The complete public inventory and table/safety details are listed above under Problem 5: lookup_inventory, lookup_lease, lookup_pricing, get_shop_context, list_tickets, get_ticket, list_vendors, get_vendor_status, get_invoice, list_cash_accounts, list_payments, prepare_payment. All twelve are read-only for shop records; prepare_payment returns a proposal, never an approval or execution.

| Private tool | Reads / writes | Safety and purpose |
|---|---|---|
| control_get_state | Reads proposal receipts/reset-generation metadata; initializes metadata schema when needed | API capability only; not a pure byte-preserving metadata read |
| control_stage_proposal | Reads obligation/cash/payment facts; writes pending proposal metadata | Independent revalidation; no money moves |
| control_execute_payment | Reads desk, invoice/vendor or lease, cash, payments, ticket and proposal; writes cash_accounts, payments, invoices or leases/tickets, and execution receipt | Existing pending proposal, explicit human approval, reviewer, current generation, refreshed facts/cash and duplicate checks; atomic commit or rollback |
| control_reset | Reads original DB; restores working DB and invalidates review metadata | Explicit reset only; never startup; original remains untouched |
| control_complete_ticket101_operations | Reads tickets, inventory, invoices, vendor blocker, payments, cash, receipts and completed audit evidence; writes only ticket 101 status/notes | Requires matching paid invoice and human receipt, completed post-payment reports, no pending proposal; closure explicitly excludes physical fulfillment |
| control_complete_ticket103_operations | Reads tickets, inventory, pricing, cash, proposals and completed audit evidence; writes only ticket 103 status/notes | Requires completed Boss/Inventory/Accounting/Customer Service reports, supported declined_as_requested disposition, factual draft, matching current evidence and generation, no outstanding approval/payment |

### Final completion paths

**101 — Bulldog tee:** Initial Boss → Inventory → Accounting investigation prepared invoice 501 for 840; later redundant work reached the unchanged MCP cap. The already-validated proposal was recovered through private staging, not fabricated. Liang Qiao explicitly approved proposal a1af63ed-97a4-4b01-b8ca-30e63d20318e; backend executed payment 1 at 2026-10-05T13:48:37.285635+00:00, reducing cash to 2560. Final post-payment run ab80a645-81f6-4105-afd7-4f12ec4e6485 used Boss → Inventory, Boss → Customer Service, Boss → Inventory and completed those reports. They established zero size-S stock, paid invoice, cleared vendor blocker, and unverified shipment/receipt. The explicit operations-completion route resumed that evidence through control_complete_ticket101_operations. Only status/notes changed during closure. Customer response remains a draft; no physical fulfillment was claimed.

**102 — Rent due:** Run 72b5a159-02bc-4fa0-bdc1-8b5094dfea8e used Boss → Facilities and Boss → Accounting to verify lease 1, Chapel Street shop, Elm City Properties, 2400 due 2026-09-02, against desk date 2026-08-31. After the user clarified that payments is the authoritative modeled ledger, run cfe6359d-ea13-403a-aeb4-ab0962be91a1 had Boss prepare the rent proposal directly. Anthony Qiao explicitly approved proposal 2b9b4c3b-ab18-4b1a-9048-3effd0c0caa7. The backend called control_execute_payment and executed payment 2 at 2026-10-05T23:50:14.877350+00:00. The transaction debited 2400, inserted the payment, updated the lease using the human-provided next due date, consumed the proposal and closed Ticket 102. Cash became 160. This ticket is resolved and has no pending approval.

**103 — Bulk hoodie discount:** Final run 7dea3f7b-153c-4026-9dca-4e545b8f738d used Boss → Inventory, Boss → Accounting, Boss → Customer Service. All four completed. Actual public tools: get_shop_context, get_ticket, lookup_inventory, list_vendors, get_vendor_status, lookup_pricing. Inventory verified 8 against 20 requested (12 short) without proven exact-variant replenishment; Accounting verified cost 22/list 58 without discount authority; Customer Service drafted a factual decline; Boss recommended declined_as_requested. The run route called control_complete_ticket103_operations for independent evidence checks and closure. No payment, stock change, discount or external contact occurred; cash remains 160.

### API and dashboard workflow

| Method / URL | Behavior |
|---|---|
| GET /api/tickets | Current working-database tickets and resolved/open state via MCP |
| POST /api/tickets/{ticket_id}/run | Run the existing five-agent team; stage validated proposals; conditionally complete supported Ticket 103 decline |
| POST /api/tickets/101/complete-operations?run_id=... | Resume completed post-payment evidence and independently validate Ticket 101 operations closure |
| GET /api/events | Recent safe high-level audit events; no private reasoning |
| GET /api/proposals | Current review metadata through private MCP |
| POST /api/approvals/{proposal_id} | Explicit human approval and transactional payment execution; agents cannot call it as an inference tool |
| GET /api/cash | Current checking value through MCP |
| POST /api/reset | Explicitly restore only working DB from original; preserve audit history |

Start from backend/ with `uvicorn main:app --reload --port 8000` using the existing environment. API: http://localhost:8000. Start from frontend/ with `npm run dev`; open http://localhost:5173 (allowed local CORS origin). Select a ticket, run once, observe refreshed audit activity and returned summaries, then separately review any proposed payment. Only a human approval executes money movement. Refresh reflects backend status/balance; reset is a distinct confirmation action. After a browser reload, Run brief may show “Awaiting a run” because reports are not reconstructed into transient frontend state; persisted ticket status and real audit remain authoritative. The evidence page captures final resolved states without rerunning agents.

### Current runtime and safety contract

Exactly five PydanticAI agents: Boss coordinates/evaluates; Inventory checks stock/vendors/lead time; Accounting checks costs/cash/invoices/payments; Facilities checks leases; Customer Service drafts factual responses. Any agent can delegate to any other subject to shared limits. Self-delegation or an active-path cycle is recorded as delegation_skipped with target/path, does not call a child, and consumes the unchanged delegation budget. Evidence and completed reports are shared to avoid redundant calls. Other limit failures stop safely.

Limits per request: 9 agent invocations, 8 delegation attempts, depth 3, 16 model requests, 40 function calls, 24 MCP calls, 180 seconds overall; MCP timeout 20 seconds, result cap 24000 bytes, task cap 2000 characters, list results at most 25 rows. Model output is capped at 2500 tokens. Only gpt-6-luna via Portkey, PORTKEY_API_KEY, https://api.portkey.ai/v1, OpenAI-compatible chat/completions with provider header openai and reasoning_effort none. No alternate-model fallback.

All operational agent/backend access passes through MCP; no frontend SQLite access. Internal SQL is parameterized and focused, never exposed as unrestricted SQL. Original data/campus_customs.db is protected; operational work uses data/campus_customs_new.db. desk.date_today is authoritative, vendor lead_days comes from vendors, unpaid vendor invoices block shipment, and payments is the modeled ledger. Missing evidence cannot become invented stock, discount, shipment or receipt. No incoming revenue, no customer email, no real vendor contact. Customer messages remain drafts.

Payments require an existing pending proposal and explicit human approval, independent obligation/cash/duplicate checks immediately before execution, and transactional updates. Insufficient cash and duplicate obligations are rejected; cash cannot go negative. Model text never counts as approval. Operations closure is distinct from fulfillment and requires supported completed evidence, not merely a finished run. The audit appends timestamped run/agent/delegation/tool/result/stop summaries under a file lock without replacing prior events or recording hidden reasoning. Artifact cleanup never invokes business mutations or appends invented run events.
