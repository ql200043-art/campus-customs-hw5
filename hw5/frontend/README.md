# Campus Customs operations desk

From `backend/` in one terminal:

```sh
source ../mcp_server/.venv/bin/activate
uvicorn main:app --reload --port 8000
```

From `frontend/` in another terminal:

```sh
npm ci
npm run dev
```

Open http://localhost:5173. The frontend calls http://localhost:8000; the existing backend permits this local origin. Port 5173 is strict to avoid an accidental CORS mismatch. Agent runs require the existing backend Portkey environment configuration; ordinary dashboard reads do not call a model.

`npm run build` validates TypeScript and produces `dist/`. `npm test` checks UI workflows and the API contract using clearly isolated synthetic fixtures; it never executes shop operations or model calls. Run the existing Python tests from Homework 5 to validate real backend behavior with disposable copies.

Select a ticket and click Run agent team. A recommendation does not mark a ticket resolved: status always comes from the backend. Desk-wide audit events refresh while an action is pending; the completed run view requests events filtered by its returned run ID. The latest audit window is capped at 200 events. Reloading the page preserves backend records but clears this browser's ephemeral run briefs.

Human review requires a reviewer name, explicit acknowledgement, and a confirmed next due date for rent. The backend alone executes and revalidates payments. Reset requires its own confirmation, restores the working copy, and preserves the original and audit history. Never expose this unauthenticated local demo API on a public network.
