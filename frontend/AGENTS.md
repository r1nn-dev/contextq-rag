# AGENTS.md — frontend

Working rules for AI agents in `frontend/`. The root `AGENTS.md` also applies; this file wins on conflict for work in this directory.

`frontend/` is AI-delegated. Implementation follows `docs/ai/prompts/30-implement-frontend.md`.

---

## §1 Absolute Rules

1. **SSE uses `fetch` + `ReadableStream` only.** Do not use `EventSource` — it cannot send the `Authorization` header (`docs/adr/ADR-003-sse-fetch-stream.md`). ESLint rejects `EventSource`.
2. **Keep the Access Token in memory only.** Do not write tokens to `localStorage`, `sessionStorage`, or IndexedDB (`docs/planning/policy.md` > §1.2 > "메모리에만 보관"). ESLint rejects `localStorage` and `sessionStorage`.
3. **Read the version list from the meta API only.** Do not hardcode framework or version strings (`docs/planning/policy.md` > §3 소스·버전 정책 > "버전 문자열을 하드코딩하지 않는다(UI-01)").
4. **Assume the same origin.** The backend allows no CORS (`docs/planning/policy.md` > §11 > "CORS 미허용"). Call relative `/api/...` paths prefixed by `import.meta.env.VITE_API_BASE_URL`. Do not hardcode a host or port. In development, the Vite proxy forwards `/api` to the backend.
5. **Do not change API contracts here.** If a screen needs a new field or endpoint, stop and propose a change to `docs/specs/api-spec.md` first.

---

## §2 Code Rules

- No `any`. Use `unknown` and narrow with a type guard.
- Types that mirror API responses live in `src/types/` and follow `docs/specs/api-spec.md`. SSE event types follow the SSE contract schema (`contracts/sse-events.schema.json`, added with the SSE contract issue).
- API calls live in `src/api/`. Components do not call `fetch` directly.
- Do not install a new package without stating the reason and getting user approval.
- `VITE_` variables are bundled into the browser. Never put secrets in them.

---

## §3 Before Each Commit

```bash
cd frontend
npm run lint        # ESLint, warnings fail
npm test            # Vitest unit tests (src/**/*.test.ts)
npm run build       # type check + Vite build
```

Commit `package.json` and `package-lock.json` together (`CONTRIBUTING.md` > §0.1).

---

## §4 Reference Documents

| Work | Read first |
| --- | --- |
| Endpoints, request and response fields | `docs/specs/api-spec.md` |
| SSE event order and fields | `docs/specs/api-spec.md` > 부록 B, `contracts/sse-events.schema.json` |
| Token, guest, and quota behavior | `docs/planning/policy.md` > §1 |
| Screen layout | `docs/ui/app.html`, `docs/ui/README.md` |
| Review standard | `docs/ai/review-checklist.md` > §G |
