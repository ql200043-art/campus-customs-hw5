export type Ticket = {
  id: number;
  subject: string;
  requester: string;
  notes: string;
  type: string;
  status: string;
  is_open: boolean;
  is_resolved: boolean;
  sku: string | null;
  size: string | null;
  qty: number | null;
};
export type AgentEvent = {
  timestamp: string;
  run_id: string;
  active_agent: string;
  action: string;
  delegation_target?: string;
  mcp_tool?: string;
  result_summary?: string;
  stop_reason?: string;
};
export type Proposal = {
  id: string;
  ticket_id: number;
  status: string;
  proposal: {
    kind: string;
    ref_id: number;
    account: string;
    amount: string;
    payee: string;
    due_date: string;
    shop_date: string;
  };
};
export type Report = {
  summary: string;
  status: string;
  recommended_actions: string[];
  missing_information: string[];
  customer_draft?: string | null;
  stop_reason?: string;
};
export type RunResult = {
  ticket_id: number;
  run_id: string;
  status: string;
  report: Report | null;
  stop_reason?: string;
  proposal_rejections: string[];
};
export const API = "http://localhost:8000";
export async function request<T>(path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(
      API + path,
      body === undefined
        ? {}
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          },
    );
  } catch {
    throw new Error(
      body === undefined
        ? "Cannot reach the backend. Start it on localhost:8000, then refresh."
        : "Connection lost. The action may have reached the backend. Refresh and check its status before retrying.",
    );
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : (detail?.reason ??
            (Array.isArray(detail)
              ? "Please check the required approval fields."
              : "The backend could not complete this action. Refresh and check the current state.")),
    );
  }
  return data as T;
}
export const api = {
  tickets: () => request<{ tickets: Ticket[] }>("/api/tickets"),
  cash: () => request<{ balance: number; date: string }>("/api/cash"),
  events: (run?: string) =>
    request<{ events: AgentEvent[] }>(
      "/api/events?limit=200" +
        (run ? "&run_id=" + encodeURIComponent(run) : ""),
    ),
  proposals: () =>
    request<{ proposals: Proposal[]; truncated?: boolean }>("/api/proposals"),
  run: (id: number) => request<RunResult>(`/api/tickets/${id}/run`, {}),
  approve: (id: string, reviewer: string, next_due: string | null) =>
    request<{ status: string; audit_warning?: string }>(
      `/api/approvals/${encodeURIComponent(id)}`,
      { approved: true, reviewer, next_due },
    ),
  reset: () =>
    request<{ status: string; audit_warning?: string }>("/api/reset", {
      confirmation: "RESET_WORKING_DATABASE",
    }),
};
