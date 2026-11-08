# AGENTS.md — ContextQ-RAG

Operating rules for AI agents working in this repository. To change a rule, edit only this file.

This file does not copy rules from the reference documents; it only points to them. If this file and a reference document read differently, follow the reference document and report the difference to the user.

---

## 0. Absolute rules

1. Follow `CONTRIBUTING.md` > `0. 필수 사항` > `절대 원칙`.
2. The repository documents are the source of truth. Use conversations or earlier sessions as grounds only when their content is reflected in a repository document.
3. Do not fill in values you could not confirm in a document (dates, Issue numbers, metrics, policy values). Leave them blank and ask the user.
4. Do not create or edit Issues, PRs, or comments on GitHub until the user approves. Do not run `git push`.

---

## 1. Before starting work

1. Confirm the Issue number and branch before working. If either is unknown, ask first.
   Follow `CONTRIBUTING.md` > `1.2 브랜치 네이밍` for branch naming.
2. Read the reference documents for the task from the table in §4 before writing any code.
3. If the task affects the RAG pipeline, API contract, or DB schema, read the relevant section of `claude/sdd.md` first.

---

## 2. Document rules

- If the task requires a contract change (REST API response schema, ERD, `configs/` file structure, RAG chain I/O interface), stop implementing and propose the document change first.
- Confirm whether something is implemented by reading code and configuration files directly — not PR descriptions or commit messages.
- Give document locations as `document > section > phrase`, never as line numbers.

---

## 3. Scope and prohibitions

- Do not expand work beyond the scope of the current request. If a change outside the scope seems necessary, state the target and reason, and proceed only after the user approves.
- Before each commit, show the changed file list and commit message, and get approval.
  Follow `CONTRIBUTING.md` > `2. 커밋 규칙` for the commit format.
- Never write secrets (API keys, passwords, tokens) to files, commits, Issues, or PRs. Use empty strings or placeholders for example values.
- Do not merge `configs/` changes without Before/After evaluation metrics.

---

## 4. Reference documents

| Work | Read first |
| --- | --- |
| All work | `CONTRIBUTING.md` |
| Branches, commits, Issues, PRs | `CONTRIBUTING.md` §1–§4 |
| Feature scope, requirements, design defense | `claude/sdd.md` |
| RAG chain and context composition | `claude/rag-pipeline.md` |
| API endpoints, request/response schemas | `claude/interfaces.md` |
| Data collection, parsing, chunking, embedding | `claude/data-sources.md` |
| RAG evaluation metrics and experiment protocol | `claude/evaluation.md`, `claude/protocol.md` |
| Test plan and coverage criteria | `claude/test-plan.md` |
| Environment variables and infrastructure | `.env.example`, `infra/docker-compose.yml` |

---

## 5. Language and comments

- Reply to the user in Korean.
- Write Issue, PR, and commit subjects and bodies in Korean.
  Keep `<type>(<scope>)`, code identifiers, and file paths as-is.
- Write code comments to explain *Why*. The code explains *What*.

---

## 6. TBD

The following sections will be filled in as the project progresses.

- **Run commands** — `uv run pytest`, `./gradlew build`, `npm run lint`, etc.
  Add after `ai-server/`, `backend/`, `frontend/` directories are created.
- **Directory structure** — role of each module and location of key files.
  Add after initial implementation is complete.
- **Session stage prompts** — step-by-step prompts for each work cycle.
  Add after recurring patterns are established.

---

end.