"""Problem 7 API/control tests; all destructive work uses disposable shop copies."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from fastmcp import Client
from backend.api_mcp import MCPGateway
from backend.audit import AuditTrail
from backend.main import create_app
from backend.settings import ROOT,TOOL_NAMES
from mcp_server import database,control,operations
from mcp_server.server import create_server


class InProcessGateway(MCPGateway):
    """Real MCP Client transports, but hosted in-process against disposable paths."""
    def __init__(self):
        super().__init__();self.public=create_server();self.private=create_server(self.capability)
    def shop_client(self):return Client(self.public)
    def control_client(self):return Client(self.private)


class APITests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack()
        self.temp=self.stack.enter_context(tempfile.TemporaryDirectory(dir=ROOT/'output'))
        self.folder=Path(self.temp);data=self.folder/'data';data.mkdir()
        self.original=data/'campus_customs.db';self.working=data/'campus_customs_new.db'
        shutil.copyfile(ROOT/'data/campus_customs.db',self.original)
        shutil.copyfile(self.original,self.working)
        self.baseline=self.original.read_bytes()
        self.stack.enter_context(patch.object(database,'DATABASE_PATH',self.working))
        self.stack.enter_context(patch.object(control,'STATE_PATH',self.folder/'review.db'))
        self.audit=AuditTrail(self.folder/'audit.json')
        self.audit.append(run_id='fixture',active_agent='Inventory',action='mcp_result',mcp_tool='lookup_inventory',result_summary='fixture audit event')
        self.gateway=InProcessGateway()
        self.app=create_app(gateway=self.gateway,audit=self.audit)
        self.client=self.stack.enter_context(TestClient(self.app))

    def tearDown(self):
        self.assertEqual(self.original.read_bytes(),self.baseline)
        self.stack.close()

    def sql(self,query,args=()):
        with closing(sqlite3.connect(self.working)) as db:
            with db:
                return db.execute(query,args).fetchall()

    def queue(self,kind='invoice',ref_id=501,ticket_id=101):
        candidate=operations.prepare_payment(kind,ref_id,'checking')
        state=control.get_review_state()
        result=control.stage_proposal(candidate,ticket_id,'fixture-run',state['generation'])
        return result['proposal_id']

    def approve(self,proposal_id,**extra):
        return self.client.post('/api/approvals/'+proposal_id,json={'approved':True,'reviewer':'Human reviewer',**extra})

    def test_startup_no_reset_and_routes_return_database_and_audit(self):
        self.assertEqual(self.working.read_bytes(),self.baseline)
        routes={(method,route.path) for route in self.app.routes for method in getattr(route,'methods',())}
        for method,path in [('GET','/api/tickets'),('POST','/api/tickets/{ticket_id}/run'),('GET','/api/events'),('GET','/api/proposals'),('POST','/api/approvals/{proposal_id}'),('GET','/api/cash'),('POST','/api/reset')]:
            self.assertIn((method,path),routes)
        tickets=self.client.get('/api/tickets').json()['tickets']
        self.assertEqual([t['id'] for t in tickets],[101,102,103])
        self.assertTrue(all(t['is_open'] and not t['is_resolved'] for t in tickets))
        self.assertEqual(tickets[0]['invoice_id'],501)
        cash=self.client.get('/api/cash').json()
        self.assertEqual(cash['balance'],self.sql("SELECT balance FROM cash_accounts WHERE name='checking'")[0][0])
        event=self.client.get('/api/events?limit=1').json()['events'][0]
        self.assertEqual(event['run_id'],'fixture')
        self.assertEqual(event['mcp_tool'],'lookup_inventory')
        self.assertEqual(self.client.get('/api/events?limit=201').status_code,422)
        self.assertEqual(self.client.post('/api/tickets/999/run').status_code,404)
        self.assertEqual(self.working.read_bytes(),self.baseline)

    def test_missing_configuration_and_cors(self):
        with patch.dict('os.environ',{'PORTKEY_API_KEY':''}):
            self.assertEqual(self.client.post('/api/tickets/101/run').status_code,503)
        response=self.client.options('/api/cash',headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'GET'})
        self.assertEqual(response.headers['access-control-allow-origin'],'http://localhost:5173')
        response=self.client.post('/api/reset',headers={'Origin':'https://untrusted.example'},json={'confirmation':'RESET_WORKING_DATABASE'})
        self.assertEqual(response.status_code,403)

    def test_run_route_reuses_team_interface_and_stages_only_pending(self):
        outer=self
        class MockTeam:
            async def run(self,task,role):
                outer.assertIn('ticket 101 only',task)
                outer.assertEqual(role.value,'Boss')
                candidate=operations.prepare_payment('invoice',501,'checking')
                return {'run_id':'mock-inference-only','report':{'status':'needs_human_approval','summary':'Mock result; no inference','stop_reason':'fixture'},
                        'payment_proposals':[candidate],'approved':True}
            async def close(self):pass
        self.app.state.team_factory=MockTeam
        result=self.client.post('/api/tickets/101/run')
        self.assertEqual(result.status_code,200,result.text)
        body=result.json();self.assertEqual(len(body['pending_proposals']),1)
        self.assertEqual(body['pending_proposals'][0]['status'],'pending')
        self.assertEqual(self.sql('SELECT count(*) FROM payments')[0][0],0)
        self.assertEqual(self.working.read_bytes(),self.baseline)
        self.assertEqual(self.client.get('/api/proposals').json()['proposals'][0]['status'],'pending')

    def test_no_explicit_approval_no_execution(self):
        proposal=self.queue()
        self.assertEqual(self.client.post('/api/approvals/'+proposal).status_code,422)
        self.assertEqual(self.client.post('/api/approvals/'+proposal,json={'approved':False,'reviewer':'Human'}).status_code,400)
        self.assertEqual(self.client.post('/api/approvals/'+proposal,json={'approved':'true','reviewer':'Human'}).status_code,422)
        self.assertEqual(self.client.post('/api/approvals/'+proposal,json={'approved':True,'reviewer':' '}).status_code,422)
        self.assertEqual(self.approve('unknown-proposal').status_code,404)
        self.assertEqual(self.working.read_bytes(),self.baseline)

    def test_invoice_payment_atomic_updates_and_no_customer_resolution(self):
        proposal=self.queue();result=self.approve(proposal)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['status'],'executed')
        self.assertEqual(self.sql('SELECT balance FROM cash_accounts')[0][0],2560)
        self.assertEqual(self.sql('SELECT status FROM invoices WHERE id=501')[0][0],'paid')
        self.assertEqual(self.sql('SELECT status FROM tickets WHERE id=101')[0][0],'open')
        self.assertEqual(self.sql('SELECT kind,ref_id,amount,paid_at,approved_by FROM payments'),[('invoice',501,840.0,'2026-08-31','Human reviewer')])
        self.assertEqual(self.client.get('/api/proposals').json()['proposals'][0]['status'],'executed')
        self.assertEqual(self.approve(proposal).status_code,409)
        self.assertEqual(self.sql('SELECT count(*) FROM payments')[0][0],1)

    def test_rent_payment_requires_next_due_and_resolves_only_rent(self):
        proposal=self.queue('rent',1,102)
        self.assertEqual(self.approve(proposal).status_code,400)
        self.assertEqual(self.approve(proposal,next_due='2026-09-01').status_code,400)
        self.assertEqual(self.approve(proposal,next_due='bad-date').status_code,400)
        self.assertEqual(self.working.read_bytes(),self.baseline)
        result=self.approve(proposal,next_due='2026-10-02')
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.sql('SELECT balance FROM cash_accounts')[0][0],1000)
        self.assertEqual(self.sql('SELECT next_due FROM leases WHERE id=1')[0][0],'2026-10-02')
        self.assertEqual(self.sql('SELECT id,status FROM tickets ORDER BY id'),[(101,'open'),(102,'closed'),(103,'open')])
        ticket=self.client.get('/api/tickets').json()['tickets'][1]
        self.assertTrue(ticket['is_resolved'])

    def test_insufficient_funds_and_negative_money_rejected_at_execution(self):
        proposal=self.queue()
        self.sql('UPDATE cash_accounts SET balance=10')
        result=self.approve(proposal)
        self.assertEqual(result.status_code,409,result.text)
        self.assertIn('Insufficient',result.text)
        self.assertEqual(self.sql('SELECT balance FROM cash_accounts')[0][0],10)
        self.assertEqual(self.sql('SELECT count(*) FROM payments')[0][0],0)
        self.sql('UPDATE cash_accounts SET balance=-1')
        self.assertEqual(self.approve(proposal).status_code,409)
        self.assertEqual(self.sql('SELECT count(*) FROM payments')[0][0],0)

    def test_duplicate_existing_payment_refused_and_stale_invoice_refused(self):
        proposal=self.queue()
        self.sql("INSERT INTO payments VALUES(1,'invoice',501,840,'checking','2026-08-31','fixture')")
        self.assertEqual(self.approve(proposal).status_code,409)
        self.assertEqual(self.sql('SELECT balance FROM cash_accounts')[0][0],3400)
        self.sql('DELETE FROM payments')
        self.sql('UPDATE invoices SET amount=841 WHERE id=501')
        self.assertEqual(self.approve(proposal).status_code,409)
        self.assertEqual(self.sql('SELECT count(*) FROM payments')[0][0],0)

    def test_partial_write_rolls_back_cash_payment_and_receipt(self):
        proposal=self.queue()
        self.sql("CREATE TRIGGER fail_invoice BEFORE UPDATE ON invoices BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
        # SQLite errors surface as MCP errors; the API fails closed.
        with TestClient(self.app,raise_server_exceptions=False) as client:
            response=client.post('/api/approvals/'+proposal,json={'approved':True,'reviewer':'Human'})
        self.assertEqual(response.status_code,503)
        self.assertEqual(self.sql('SELECT balance FROM cash_accounts')[0][0],3400)
        self.assertEqual(self.sql('SELECT count(*) FROM payments')[0][0],0)
        self.assertEqual(self.sql('SELECT status FROM invoices')[0][0],'open')
        self.assertEqual(self.client.get('/api/proposals').json()['proposals'][0]['status'],'pending')

    def test_concurrent_duplicate_attempt_only_one_succeeds(self):
        proposal=self.queue()
        def execute():
            try:return control.execute_proposal(proposal,'Human',True)['ok']
            except control.Rejected:return False
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:execute(),range(2)))
        self.assertEqual(sorted(results),[False,True])
        self.assertEqual(self.sql('SELECT count(*) FROM payments')[0][0],1)
        self.assertEqual(self.sql('SELECT balance FROM cash_accounts')[0][0],2560)

    def test_reset_exact_copy_invalidates_pending_and_preserves_audit(self):
        pending=self.queue('rent',1,102);invoice=self.queue()
        self.assertEqual(self.approve(invoice).status_code,200)
        before=json.loads(self.audit.path.read_text())
        self.assertEqual(self.client.post('/api/reset',json={}).status_code,422)
        response=self.client.post('/api/reset',json={'confirmation':'RESET_WORKING_DATABASE'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.working.read_bytes(),self.baseline)
        self.assertEqual(json.loads(self.audit.path.read_text())[:len(before)],before)
        self.assertEqual(self.approve(pending,next_due='2026-10-02').status_code,409)
        self.assertEqual(self.approve(invoice).status_code,409)
        self.assertEqual(self.sql('SELECT count(*) FROM payments')[0][0],0)
        self.assertEqual(self.sql('PRAGMA integrity_check')[0][0],'ok')

    def test_fabricated_or_wrong_ticket_proposal_rejected(self):
        state=control.get_review_state();candidate=operations.prepare_payment('invoice',501,'checking')
        altered=json.loads(json.dumps(candidate));altered['proposal']['amount']='1'
        with self.assertRaises(control.Rejected):control.stage_proposal(altered,101,'fixture',state['generation'])
        with self.assertRaises(control.Rejected):control.stage_proposal(candidate,103,'fixture',state['generation'])
        with self.assertRaises(control.Rejected):control.stage_proposal(candidate,101,'fixture','old-generation')

    def test_private_tools_not_discoverable_or_callable_by_agents(self):
        async def check():
            async with self.gateway.shop_client() as client:
                self.assertEqual({t.name for t in await client.list_tools()},set(TOOL_NAMES))
                with self.assertRaises(Exception):await client.call_tool('control_reset',{'confirmation':'RESET_WORKING_DATABASE'})
            async with self.gateway.control_client() as client:
                with self.assertRaises(Exception):await client.call_tool('control_get_state',{'capability':'agent cannot know this'})
        asyncio.run(check())


if __name__=='__main__':unittest.main()
