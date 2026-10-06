"""Exercise MCP via Codex app-server JSON-RPC, without an LLM turn."""
import asyncio
import json
from pathlib import Path
import hashlib
import sqlite3
from .codex_project import config_overrides
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]

async def main(output_path=ROOT/'output/mcp_smoke_problem5.json'):
    overrides = config_overrides()
    process = await asyncio.create_subprocess_exec(
        'codex', *overrides, '-c', 'sqlite_home='+json.dumps(str(ROOT/'output/.codex-runtime')), '-c', 'log_dir='+json.dumps(str(ROOT/'output/.codex-runtime')), 'app-server', '--stdio', cwd=ROOT,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, limit=16*1024*1024,
    )
    sequence = 0
    async def request(method, params):
        nonlocal sequence
        sequence += 1
        message = {'id': sequence, 'method': method, 'params': params}
        process.stdin.write((json.dumps(message)+'\n').encode())
        await process.stdin.drain()
        while True:
            raw = await asyncio.wait_for(process.stdout.readline(), 50)
            if not raw: raise RuntimeError('Codex app-server exited')
            response = json.loads(raw)
            if response.get('id') == sequence:
                if 'error' in response: raise RuntimeError(response['error'])
                return response['result']
    try:
        await request('initialize', {'clientInfo': {'name':'campus_customs_smoke','version':'1.0'}, 'capabilities':{'experimentalApi':True}})
        process.stdin.write(b'{"method":"initialized"}\n')
        config = await request('config/read', {'cwd':str(ROOT),'includeLayers':True})
        before = {name: hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest()
                  for name in ('campus_customs.db', 'campus_customs_new.db')}
        thread = await request('thread/start', {'cwd':str(ROOT), 'ephemeral':True})
        tid = thread['thread']['id']
        discovery = await request('mcpServerStatus/list', {'threadId':tid, 'detail':'toolsAndAuthOnly'})
        campus = next(item for item in discovery['data'] if item['name']=='campus_customs')
        assert campus['runtimeStatus'] == 'connected'
        assert set(campus['tools']) >= {'lookup_inventory', 'lookup_lease', 'lookup_pricing'}
        print('Discovered all three tools through Codex MCP.', flush=True)
        tests = []
        for prompt, tool, arguments in [
            ('Check the inventory for SKU CC-TEE-WHITE in size S.', 'lookup_inventory', {'sku':'CC-TEE-WHITE','size':'S'}),
            ('Look up lease 1.', 'lookup_lease', {'lease_id':1}),
            ('Look up the pricing for SKU CC-HOOD-NAVY.', 'lookup_pricing', {'sku':'CC-HOOD-NAVY'}),
        ]:
            output = await request('mcpServer/tool/call', {'threadId':tid, 'server':'campus_customs', 'tool':tool, 'arguments':arguments})
            tests.append({'prompt':prompt,'tool':tool,'arguments':arguments,'mcp_output':output})
            print('CALL', json.dumps(tests[-1]), flush=True)
        evidence = {'connection':'Codex app-server -> configured stdio MCP server',
                    'configuration':'.codex/config.toml',
                    'activation':'Project-local config loaded as explicit CLI overrides; native auto-loading awaits project trust.',
                    'discovery':campus,'tests':tests,'sha256_before':before}
        # Only after all MCP calls: independently compare with read-only SQLite.
        queries = [
            ('SELECT * FROM inventory WHERE sku=? AND size=?', ('CC-TEE-WHITE','S')),
            ('SELECT * FROM leases WHERE id=?', (1,)),
            ('SELECT * FROM pricing WHERE sku=?', ('CC-HOOD-NAVY',)),
        ]
        with closing(sqlite3.connect((ROOT/'data/campus_customs_new.db').as_uri()+'?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            for test, (query, arguments) in zip(tests, queries):
                row = dict(db.execute(query, arguments).fetchone())
                output = test['mcp_output']
                assert not output['isError']
                test['matches_working_database'] = output['structuredContent'] == {'found':True, 'record':row}
                assert test['matches_working_database']
        evidence['sha256_after'] = {name:hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest() for name in before}
        assert evidence['sha256_after'] == before
        evidence['validation'] = {'all_outputs_match_working_database':True, 'both_databases_unchanged':True,
                                  'independent_sqlite_checks_performed_after_all_mcp_calls':True, 'problem_6_started':False}
        evidence['test_method'] = 'Vibe coder translated supplied natural-language prompts; Codex app-server forwarded calls over stdio MCP. No LLM turn or direct tool-function calls.'
        output_path.write_text(json.dumps(evidence,indent=2)+'\n')
    finally:
        if process.returncode is None: process.terminate()
        await process.wait()

if __name__ == '__main__':
    asyncio.run(main())
