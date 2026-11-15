# 20. Issue Write

## Purpose

Write an Issue body from the settled scope and register it after the user approves.

## When to use

- After Step C of stage 10 settles the scope and decisions, once per Issue

## Inputs

- One Issue settled in stage 10 (title, scope, commit units, decisions)
- `.github/ISSUE_TEMPLATE/`: feature template (`feat`), bug template (`fix`), task template
  (`chore` / `docs` / `test` / `refactor` / `perf`)
- `CONTRIBUTING.md` §1.3 Issue rules (scope table, title format)

## Steps

1. **If the Issue already exists on GitHub** (created manually before this step):
   - Ask the user to paste the body.
   - Compare it against the scope settled in stage 10.
   - Report discrepancies: title mismatch, missing fields, placeholders not replaced.
   - Propose corrections. Wait for user approval before proceeding.

2. **Choose the template** that matches the work type:

   | Type | Template | Use when |
   | --- | --- | --- |
   | `feat` | 기능 구현 | Adding a new capability (endpoint, pipeline, feature) |
   | `fix` | 버그 수정 | Correcting incorrect behavior; `hotfix` if production-critical |
   | `docs` / `chore` / `test` / `refactor` / `perf` | 일반 작업 | Docs, CI, deps, config, eval, refactor, performance |

3. **Choose the scope** from `CONTRIBUTING.md` §1.3 scope table only. Do not invent scopes.

4. **Write the body** from the settled scope:
   - Write only settled items. Do not write implementation choices that are still open.
   - File paths, function names, table names, and commands must be in `` `backticks` ``.
   - For `fix` template: fill Given / When / Then for 재현 조건. Stack traces go in `` ``` `` fences.
   - For `perf` or `eval` Issues, or any Issue that changes `configs/` or RAG query-rewriting logic:
     add a 측정 기준 section with Before/After metric targets and measurement method (`CONTRIBUTING.md` §9.5).
     ```
     | 지표 | Before | After (목표) | 측정 방법 |
     | precision@3 | 0.62 | ≥ 0.75 | qa_eval_v1.jsonl, top-3 |
     | faithfulness | 0.71 | ≥ 0.80 | RAGAS, gpt-4o-mini 채점, qa_eval_v1.jsonl |
     ```
   - Leave values not given in the inputs blank (due date, Issue numbers). List them as questions
     outside the body.

5. **Verify** before showing the body — no placeholder text must remain:
   - 🎯 작업 목적 / 🐞 버그 설명: not "여기에 작성"
   - ✅ 구현 내용 / 작업 내용: specific items, not placeholder text
   - 🔁 재현 조건 (fix only): all three of Given / When / Then filled
   - 🧭 우선순위: exactly one checkbox checked
   - 📏 예상 작업 규모: exactly one checkbox checked
   - 📅 완료 기한: a concrete `yyyy-mm-dd (요일)` date, or blank with a question listed outside
   - Leave all 이슈 확인 체크박스 unchecked — the user checks them after posting, not the AI
   - Remove all HTML comment blocks before output

6. Outside the body, give one line each on:
   - Why you chose this template
   - Reasoning for priority and size
   - Blank values and their questions

7. Output the body and wait for the user to review, fill blank values, and say to register it.
   The user registers it manually — there is no MCP or automated registration.

## Output format

- Issue 제목 (`type(scope): 한 줄 요약`)
- Issue 본문 (template format; all HTML comment blocks removed)
- 본문 밖: template choice reason, priority and size reasoning, blank values and questions

## Do not

- Copy template example sentences as facts into the body.
- Fill empty values by guessing (Issue number, due date, assignee).
- Register or edit the Issue without user approval.
- Use scopes not in `CONTRIBUTING.md` §1.3 scope table.
- Omit the 측정 기준 section for a `perf` Issue or any Issue that changes `configs/`.
- Reference `.env` values, secrets, or `.mcp.json` paths anywhere in the body.

## Human gate

- The user reviews the body, fills blank values, and says to register it.
- After registration, the user sets the milestone, assignee, and labels manually.
