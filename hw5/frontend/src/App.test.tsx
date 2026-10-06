import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { api } from "./api";
vi.mock("./api", () => ({
  api: {
    tickets: vi.fn(),
    cash: vi.fn(),
    events: vi.fn(),
    proposals: vi.fn(),
    run: vi.fn(),
    approve: vi.fn(),
    reset: vi.fn(),
  },
}));
// Synthetic fixtures belong only to isolated UI tests, never the production dashboard.
const fixtureTickets = [101, 102, 103].map((id) => ({
  id,
  subject: `Fixture ticket ${id}`,
  requester: "Test requester",
  notes: "Test note",
  type: "test",
  status: "open",
  is_open: true,
  is_resolved: false,
  sku: null,
  size: null,
  qty: null,
}));
const proposal = {
  id: "test-proposal",
  ticket_id: 102,
  status: "pending",
  proposal: {
    kind: "rent",
    ref_id: 1,
    account: "checking",
    amount: "10",
    payee: "Test landlord",
    due_date: "2026-09-02",
    shop_date: "2026-08-31",
  },
};
beforeEach(() => {
  vi.mocked(api.tickets).mockResolvedValue({ tickets: fixtureTickets });
  vi.mocked(api.cash).mockResolvedValue({ balance: 100, date: "2026-08-31" });
  vi.mocked(api.events).mockResolvedValue({ events: [] });
  vi.mocked(api.proposals).mockResolvedValue({ proposals: [] });
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
describe("operations desk", () => {
  it("loads tickets and cash, selects a ticket, runs only on human click and displays actual summary/events", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("100.00");
    expect(api.run).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /#103/ }));
    vi.mocked(api.run).mockResolvedValue({
      ticket_id: 103,
      run_id: "test-run",
      status: "recommendation",
      report: {
        summary: "Verified fixture recommendation",
        status: "recommendation",
        recommended_actions: [],
        missing_information: [],
      },
      proposal_rejections: [],
    });
    vi.mocked(api.events).mockResolvedValue({
      events: [
        {
          timestamp: "2026-10-04T12:00:00Z",
          run_id: "test-run",
          active_agent: "Inventory",
          action: "agent_complete",
          mcp_tool: "lookup_inventory",
          result_summary: "Fixture stock checked",
        },
      ],
    });
    await user.click(screen.getByRole("button", { name: /Run agent team/ }));
    await screen.findByText("Verified fixture recommendation");
    expect(api.run).toHaveBeenCalledWith(103);
    expect(screen.getByText("lookup_inventory")).toBeTruthy();
    expect(screen.getAllByText(/Fixture stock checked/).length).toBeGreaterThan(
      0,
    );
    expect(screen.queryByText("Resolved")).toBeNull();
  });
  it("requires explicit human review and refreshes backend balance after execution", async () => {
    vi.mocked(api.proposals).mockResolvedValue({ proposals: [proposal] });
    vi.mocked(api.approve).mockResolvedValue({ status: "executed" });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Test landlord");
    expect(api.approve).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /Review payment/ }));
    expect(
      (
        screen.getByRole("button", {
          name: "Approve & execute payment",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    await user.type(screen.getByLabelText("Your name"), "Human Reviewer");
    await user.type(
      screen.getByLabelText(/Confirmed next rent due date/),
      "2026-10-02",
    );
    await user.click(screen.getByRole("checkbox"));
    vi.mocked(api.cash).mockResolvedValue({ balance: 90, date: "2026-08-31" });
    vi.mocked(api.proposals).mockResolvedValue({ proposals: [] });
    await user.click(
      screen.getByRole("button", { name: "Approve & execute payment" }),
    );
    await screen.findByText("90.00");
    expect(api.approve).toHaveBeenCalledWith(
      "test-proposal",
      "Human Reviewer",
      "2026-10-02",
    );
  });
  it("does not reset until confirmation and refreshes after reset", async () => {
    vi.mocked(api.reset).mockResolvedValue({ status: "reset" });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("100.00");
    await user.click(
      screen.getByRole("button", { name: /Reset working database/ }),
    );
    expect(api.reset).not.toHaveBeenCalled();
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Confirm reset" }));
    await waitFor(() => expect(api.reset).toHaveBeenCalledTimes(1));
    await screen.findByText(/Working database restored/);
  });
  it("shows useful load failures without made-up ticket or balance data", async () => {
    vi.mocked(api.tickets).mockRejectedValue(new Error("Backend unavailable"));
    vi.mocked(api.cash).mockRejectedValue(new Error("Backend unavailable"));
    render(<App />);
    await screen.findByRole("alert");
    expect(screen.queryByText("100.00")).toBeNull();
    expect(api.run).not.toHaveBeenCalled();
  });
});
