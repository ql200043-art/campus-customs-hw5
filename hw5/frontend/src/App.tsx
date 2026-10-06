import { useEffect, useState, useRef } from "react";
import {
  api,
  type Ticket,
  type AgentEvent,
  type Proposal,
  type RunResult,
} from "./api";
const roles = [
  ["Boss", "Coordinates & reviews", "B"],
  ["Inventory", "Stock & replenishment", "I"],
  ["Accounting", "Costs & payment proposals", "A"],
  ["Facilities", "Leases & obligations", "F"],
  ["Customer Service", "Verified customer drafts", "C"],
];
const money = (value: number | string) =>
  Number(value).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
const label = (s: string) => s.replaceAll("_", " ");
export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([]),
    [selected, setSelected] = useState<number | null>(null),
    [cash, setCash] = useState<{ balance: number; date: string } | null>(null),
    [events, setEvents] = useState<AgentEvent[]>([]),
    [proposals, setProposals] = useState<Proposal[]>([]),
    [results, setResults] = useState<Record<number, RunResult>>({}),
    [busy, setBusy] = useState<string | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [modal, setModal] = useState<Proposal | "reset" | null>(null),
    [reviewer, setReviewer] = useState(""),
    [due, setDue] = useState(""),
    [ack, setAck] = useState(false),
    [truncated, setTruncated] = useState(false);
  const dialogRef = useRef<HTMLElement>(null);
  const [runHistory, setRunHistory] = useState<Record<string, AgentEvent[]>>(
    {},
  );
  useEffect(() => {
    if (!modal) return;
    const previous = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    dialog?.querySelector<HTMLElement>("input,button")?.focus();
    function key(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) setModal(null);
      if (e.key !== "Tab") return;
      const items = Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          "button:not(:disabled),input:not(:disabled)",
        ) ?? [],
      );
      const first = items[0],
        last = items.at(-1);
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last?.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first?.focus();
      }
    }
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, [modal, busy]);
  const ticket = tickets.find((t) => t.id === selected),
    result = selected ? results[selected] : undefined;
  async function refresh() {
    const values = await Promise.allSettled([
      api.tickets(),
      api.cash(),
      api.events(),
      api.proposals(),
    ]);
    const [t, c, e, p] = values;
    if (t.status === "fulfilled") {
      setTickets(t.value.tickets);
      setSelected((old) => old ?? t.value.tickets[0]?.id ?? null);
    }
    if (c.status === "fulfilled") setCash(c.value);
    if (e.status === "fulfilled") setEvents(e.value.events);
    if (p.status === "fulfilled") {
      setProposals(p.value.proposals);
      setTruncated(!!p.value.truncated);
    }
    const failed = values.find((v) => v.status === "rejected");
    if (failed?.status === "rejected") throw failed.reason;
  }
  useEffect(() => {
    refresh()
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    if (!busy) return;
    let active = true;
    const timer = setInterval(() => {
      api
        .events()
        .then((v) => {
          if (active) setEvents(v.events);
        })
        .catch(() => {
          if (active)
            setError(
              "Activity refresh failed. The current action may still be running.",
            );
        });
    }, 2500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [busy]);
  async function act(name: string, fn: () => Promise<void>) {
    setBusy(name);
    setError("");
    setNotice("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Action unavailable. Please refresh.",
      );
    } finally {
      setBusy(null);
    }
  }
  const run = () =>
    ticket &&
    act("run", async () => {
      const data = await api.run(ticket.id);
      setResults((old) => ({ ...old, [ticket.id]: data }));
      const history = await api.events(data.run_id);
      setRunHistory((old) => ({ ...old, [data.run_id]: history.events }));
      setNotice(
        "Agent run returned. Ticket status is refreshed from the backend; a recommendation does not itself resolve a ticket.",
      );
    });
  function openModal(value: Proposal | "reset") {
    setModal(value);
    setReviewer("");
    setDue("");
    setAck(false);
  }
  const approve = () =>
    modal &&
    modal !== "reset" &&
    act("approval", async () => {
      const response = await api.approve(
        modal.id,
        reviewer.trim(),
        due || null,
      );
      setModal(null);
      setNotice(
        response.audit_warning ??
          "Payment executed by the backend. Balances and ticket states are being refreshed.",
      );
    });
  const reset = () =>
    act("reset", async () => {
      const response = await api.reset();
      setResults({});
      setRunHistory({});
      setModal(null);
      setNotice(
        response.audit_warning ??
          "Working database restored. Earlier audit events remain available.",
      );
    });
  const runEvents = result
    ? (runHistory[result.run_id] ??
      events.filter((e) => e.run_id === result.run_id))
    : [];
  const shownEvents = result && !busy ? runEvents : events;
  const active = busy === "run" ? events.at(-1)?.active_agent : null;
  const pending = proposals.filter((p) => p.status === "pending");
  return (
    <div className="app">
      <header>
        <div className="brand">
          <span className="logo">CC</span>
          <div>
            Campus Customs<small>SHOP OPERATIONS / AGENT DESK</small>
          </div>
        </div>
        <div className="header-right">
          <span className="local">LOCAL WORKSPACE</span>
          <button
            disabled={!!busy}
            onClick={() => act("refresh", async () => {})}
          >
            ↻ Refresh
          </button>
        </div>
      </header>
      <main>
        <div className="intro">
          <div>
            <div className="eyebrow">THE OPERATIONS DESK</div>
            <h1>A clear view. A human final say.</h1>
            <p>
              Investigate tickets with your team. Review the evidence before
              money moves.
            </p>
          </div>
          <div className="count">
            <strong>{tickets.filter((t) => t.is_open).length}</strong>
            <span>open tickets</span>
          </div>
        </div>
        <div className="roles">
          {roles.map(([name, description, initial], i) => (
            <div
              key={name}
              className={`role role-${i} ${active === name ? "active" : ""}`}
            >
              <span>{initial}</span>
              <div>
                <b>{name}</b>
                <small>{description}</small>
              </div>
              {active === name && <em>latest activity</em>}
            </div>
          ))}
        </div>
        {error && (
          <div role="alert" className="message error">
            {error} Previously loaded values may be stale.
          </div>
        )}
        {notice && (
          <div role="status" className="message success">
            {notice}
          </div>
        )}
        {loading && (
          <div role="status" className="message">
            Loading the working database…
          </div>
        )}
        <div className="desk-grid">
          <aside className="queue panel">
            <div className="section-head">
              <h2>Ticket queue</h2>
              <span>{tickets.length} total</span>
            </div>
            {tickets.map((t) => (
              <button
                disabled={!!busy}
                className={`ticket ${selected === t.id ? "selected" : ""}`}
                key={t.id}
                onClick={() => setSelected(t.id)}
              >
                <div>
                  <span className="ticket-id">#{t.id}</span>
                  <span className={`badge ${t.is_resolved ? "resolved" : ""}`}>
                    {busy === "run" && selected === t.id
                      ? "Running"
                      : t.is_resolved
                        ? "Resolved"
                        : label(t.status)}
                  </span>
                </div>
                <h3>{t.subject}</h3>
                <p>{t.requester}</p>
                <small>
                  {label(t.type)} <span>→</span>
                </small>
              </button>
            ))}
            {!loading && !tickets.length && (
              <p className="empty">
                No ticket data loaded. Check the backend and refresh.
              </p>
            )}
            <div className="queue-note">
              One ticket at a time.
              <br />
              Status comes from the working database.
            </div>
          </aside>
          <section className="workspace">
            <div className="panel ticket-detail">
              <div className="section-head">
                <span className="eyebrow">
                  SELECTED TICKET {ticket && `/ ${ticket.id}`}
                </span>
                <span className="badge">
                  {ticket ? label(ticket.status) : "Waiting for data"}
                </span>
              </div>
              <h2>{ticket?.subject ?? "Your workspace is ready"}</h2>
              <p>
                {ticket?.notes ??
                  "Select a ticket when the backend is connected."}
              </p>
              {ticket && (
                <div className="facts">
                  <span>
                    Requester <b>{ticket.requester}</b>
                  </span>
                  {ticket.sku && (
                    <span>
                      SKU <b>{ticket.sku}</b>
                    </span>
                  )}
                  {ticket.size && (
                    <span>
                      Size <b>{ticket.size}</b>
                    </span>
                  )}
                  {ticket.qty != null && (
                    <span>
                      Requested <b>{ticket.qty}</b>
                    </span>
                  )}
                </div>
              )}
              <div className="run-row">
                <button
                  className="primary"
                  disabled={!ticket?.is_open || !!busy}
                  onClick={run}
                >
                  {busy === "run"
                    ? "Team is investigating…"
                    : "Run agent team →"}
                </button>
                <small>
                  Recommendations and drafts only.
                  <br />
                  Payments require your separate approval.
                </small>
              </div>
            </div>
            <div className="panel">
              <div className="section-head">
                <h2>Run brief</h2>
                <span>{result ? label(result.status) : "Awaiting a run"}</span>
              </div>
              {result ? (
                <>
                  <p>
                    {result.report?.summary ??
                      result.stop_reason ??
                      "The backend returned no report."}
                  </p>
                  {result.report?.recommended_actions?.map((a, i) => (
                    <p key={i} className="recommendation">
                      → {a}
                    </p>
                  ))}
                  {!!result.report?.missing_information?.length && (
                    <p className="message">
                      Missing information:{" "}
                      {result.report.missing_information.join("; ")}
                    </p>
                  )}
                  {result.report?.customer_draft && (
                    <details>
                      <summary>Customer message · draft only</summary>
                      <p className="draft">{result.report.customer_draft}</p>
                    </details>
                  )}
                  {result.proposal_rejections.map((r, i) => (
                    <p key={i} className="message error">
                      Proposal not staged: {r}
                    </p>
                  ))}
                  {(result.stop_reason || result.report?.stop_reason) && (
                    <small>
                      Stop: {result.stop_reason || result.report?.stop_reason}
                    </small>
                  )}
                  <h3>Agent contributions</h3>
                  {runEvents
                    .filter((e) => e.action === "agent_complete")
                    .map((e, i) => (
                      <p key={i}>
                        <b>{e.active_agent}</b> — {e.result_summary}
                      </p>
                    ))}
                  {!runEvents.some((e) => e.action === "agent_complete") && (
                    <p className="empty">
                      No per-agent completion summaries in the most recent audit
                      window.
                    </p>
                  )}
                  <small>Run {result.run_id}</small>
                </>
              ) : (
                <p className="empty">
                  Run a selected ticket to see the backend’s recommendation and
                  each agent’s recorded contribution. No model runs start
                  automatically.
                </p>
              )}
            </div>
            <div className="panel timeline">
              <div className="section-head">
                <h2>Agent activity</h2>
                <span className={busy ? "pulse" : ""}>
                  {busy
                    ? "Refreshing every 2.5s"
                    : result
                      ? "Selected run"
                      : "Recent desk activity"}
                </span>
              </div>
              <p className="caption">
                {busy
                  ? "Desk-wide audit events while the request is in flight; other or earlier runs may appear."
                  : result
                    ? "Events matched to the returned run ID, up to 200 events from this run."
                    : "Real audit history across requests, including earlier validation activity."}
              </p>
              {shownEvents.length ? (
                <ol>
                  {[...shownEvents].reverse().map((e, i) => (
                    <li key={`${e.run_id}-${e.timestamp}-${i}`}>
                      <div
                        className={`dot role-${Math.max(
                          0,
                          roles.findIndex((r) => r[0] === e.active_agent),
                        )}`}
                      />
                      <div>
                        <div className="event-title">
                          <b>{e.active_agent}</b>
                          <time>
                            {new Date(e.timestamp).toLocaleTimeString()}
                          </time>
                        </div>
                        <p>
                          {label(e.action)}
                          {e.delegation_target && ` → ${e.delegation_target}`}
                        </p>
                        {e.mcp_tool && <code>{e.mcp_tool}</code>}
                        {e.result_summary && <small>{e.result_summary}</small>}
                        {e.stop_reason && <small>Stop: {e.stop_reason}</small>}
                      </div>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="empty">No recorded events in this view.</p>
              )}
            </div>
          </section>
          <aside className="right-rail">
            <div className="balance">
              <div className="eyebrow">CHECKING ACCOUNT</div>
              <strong>{cash ? money(cash.balance) : "—"}</strong>
              <p>Current backend balance</p>
              <small>
                {cash
                  ? `Account record date · ${cash.date}`
                  : "Waiting for backend data"}
              </small>
              <hr />
              <small>
                Cash only goes out. Payments never execute from an agent
                recommendation.
              </small>
            </div>
            <div className="panel approvals">
              <div className="section-head">
                <h2>Human review</h2>
                <span className="badge">{pending.length} pending</span>
              </div>
              <p className="caption">
                Your approval is the boundary between a proposal and a payment.
              </p>
              {pending.map((p) => (
                <article className="proposal" key={p.id}>
                  <span className="eyebrow">
                    TICKET {p.ticket_id} · {p.proposal.kind}
                  </span>
                  <h3>{p.proposal.payee}</h3>
                  <strong>{money(p.proposal.amount)}</strong>
                  <p>
                    {p.proposal.account} · Reference {p.proposal.ref_id}
                  </p>
                  <small>
                    Due {p.proposal.due_date}
                    <br />
                    Shop date at proposal: {p.proposal.shop_date}
                  </small>
                  <button disabled={!!busy} onClick={() => openModal(p)}>
                    Review payment →
                  </button>
                </article>
              ))}
              {!pending.length && (
                <div className="empty review-empty">
                  <span>✓</span>No pending proposals returned.
                  <small>
                    Prepared proposals will appear here for your review.
                  </small>
                </div>
              )}
              {truncated && (
                <p className="message">
                  The backend proposal list is truncated to 200 records.
                </p>
              )}
            </div>
            <div className="reset-box">
              <h3>Fresh demo</h3>
              <p>
                Restore only the working database. The original and audit
                history stay preserved.
              </p>
              <button
                className="danger"
                disabled={!!busy}
                onClick={() => openModal("reset")}
              >
                Reset working database…
              </button>
            </div>
          </aside>
        </div>
        <footer>
          Campus Customs / Local operations desk{" "}
          <span>Customer communications remain drafts · No vendor contact</span>
        </footer>
      </main>
      {modal && (
        <div className="overlay">
          <section
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="dialog-title"
            className="dialog"
          >
            <h2 id="dialog-title">
              {modal === "reset"
                ? "Reset the working database?"
                : "Approve this payment?"}
            </h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (modal === "reset") void reset();
                else void approve();
              }}
            >
              {modal === "reset" ? (
                <p>
                  This restores the original shop values in the working copy and
                  invalidates pending proposals. Earlier audit events are
                  retained.
                </p>
              ) : (
                <>
                  <p>
                    <b>{modal.proposal.payee}</b> ·{" "}
                    {money(modal.proposal.amount)} from {modal.proposal.account}
                  </p>
                  <p>
                    The backend rechecks the obligation, duplicate-payment risk
                    and available cash before executing.
                  </p>
                  <label>
                    Your name
                    <input
                      autoFocus
                      required
                      value={reviewer}
                      onChange={(e) => setReviewer(e.target.value)}
                      maxLength={120}
                    />
                  </label>
                  {modal.proposal.kind === "rent" && (
                    <label>
                      Confirmed next rent due date
                      <input
                        type="date"
                        required
                        value={due}
                        onChange={(e) => setDue(e.target.value)}
                      />
                      <small>
                        Enter the verified next due date. The system does not
                        infer lease terms.
                      </small>
                    </label>
                  )}
                </>
              )}
              <label className="check">
                <input
                  type="checkbox"
                  required
                  checked={ack}
                  onChange={(e) => setAck(e.target.checked)}
                />
                {modal === "reset"
                  ? "I want to reset the working copy."
                  : "I am the human reviewer and explicitly approve this payment."}
              </label>
              {error && (
                <p role="alert" className="message error">
                  {error}
                </p>
              )}
              <div className="dialog-actions">
                <button
                  type="button"
                  disabled={!!busy}
                  onClick={() => setModal(null)}
                >
                  Cancel
                </button>
                <button
                  className={modal === "reset" ? "danger" : "primary"}
                  disabled={
                    !!busy || !ack || (modal !== "reset" && !reviewer.trim())
                  }
                >
                  {busy
                    ? "Working…"
                    : modal === "reset"
                      ? "Confirm reset"
                      : "Approve & execute payment"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}
