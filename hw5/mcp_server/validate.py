"""Offline registration/query checks; never starts or connects a server."""
import asyncio
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

from .database import DATABASE_PATH
from .server import mcp


async def main():
    paths = [DATABASE_PATH.with_name("campus_customs.db"), DATABASE_PATH]
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    for source in Path(__file__).parent.glob("*.py"):
        compile(source.read_text(), str(source), "exec")
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert set(tools) >= {"lookup_inventory", "lookup_lease", "lookup_pricing"}
    with closing(sqlite3.connect(DATABASE_PATH.as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        cases = []
        for ticket_id, name, table, columns in [
            (101, "lookup_inventory", "inventory", ("sku", "size")),
            (102, "lookup_lease", "leases", ("id",)),
            (103, "lookup_pricing", "pricing", ("sku",)),
        ]:
            ticket = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
            arguments = {"lease_id": ticket["lease_id"]} if table == "leases" else {k: ticket[k] for k in columns}
            where = " AND ".join(f"{column}=?" for column in columns)
            row = conn.execute(f"SELECT * FROM {table} WHERE {where}", tuple(arguments.values())).fetchone()
            assert row is not None
            result = tools[name].fn(**arguments)
            assert result == {"found": True, "record": dict(row)}
            assert tools[name].annotations.readOnlyHint is True
            cases.append({"ticket": ticket_id, "tool": name, "result": result})
        # Deliberately invalid lookup inputs are test probes, never operational facts.
        for name, arguments in [
            ("lookup_inventory", {"sku": "' OR 1=1 --", "size": "S"}),
            ("lookup_lease", {"lease_id": -1}),
            ("lookup_pricing", {"sku": "' OR 1=1 --"}),
        ]:
            result = tools[name].fn(**arguments)
            assert result["found"] is False and result["record"] is None
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    assert before == after, "Database bytes changed"
    print(json.dumps({"checks": "PASS: compilation, imports, original three registrations preserved, real rows, not-found inputs, unchanged hashes",
                      "lookups": cases, "sha256": after, "transport_started": False}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
