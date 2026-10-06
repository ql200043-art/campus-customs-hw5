import { afterEach, expect, it, vi } from "vitest";
import { api } from "./api";
afterEach(() => vi.unstubAllGlobals());
it("uses the existing backend routes and explicit approval/reset payloads", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue({ ok: true, json: async () => ({}) });
  vi.stubGlobal("fetch", fetcher);
  await api.tickets();
  await api.cash();
  await api.events("run-1");
  await api.proposals();
  await api.run(101);
  await api.approve("proposal-1", "Human", "2026-10-02");
  await api.reset();
  expect(fetcher.mock.calls.map((c) => c[0])).toEqual([
    "http://localhost:8000/api/tickets",
    "http://localhost:8000/api/cash",
    "http://localhost:8000/api/events?limit=200&run_id=run-1",
    "http://localhost:8000/api/proposals",
    "http://localhost:8000/api/tickets/101/run",
    "http://localhost:8000/api/approvals/proposal-1",
    "http://localhost:8000/api/reset",
  ]);
  expect(JSON.parse(fetcher.mock.calls[5][1].body)).toEqual({
    approved: true,
    reviewer: "Human",
    next_due: "2026-10-02",
  });
  expect(JSON.parse(fetcher.mock.calls[6][1].body)).toEqual({
    confirmation: "RESET_WORKING_DATABASE",
  });
});
it("surfaces backend rejections and uncertain network failures safely", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue({
        ok: false,
        json: async () => ({ detail: { reason: "Insufficient cash" } }),
      }),
  );
  await expect(api.approve("id", "Human", null)).rejects.toThrow(
    "Insufficient cash",
  );
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network")));
  await expect(api.run(101)).rejects.toThrow("may have reached the backend");
});
