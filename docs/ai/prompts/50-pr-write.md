# 50. PR Writing

## Purpose

Write a PR body from the actual changes and verification results only, and register it as a
Draft after the user approves.

## When to use

After stage 40 shows no `미통과` items and the branch has been pushed to the remote.

## Inputs

- `git diff develop...HEAD`, `git log --oneline develop..HEAD`
- `.github/pull_request_template.md`
- `CONTRIBUTING.md` — PR writing conventions and commit message rules
- The stage 40 result (판정 table, 실행한 명령 table, LLMOps 체크)

## Steps

1. Follow the PR template and `CONTRIBUTING.md` PR writing conventions.
2. List only changes visible in the current diff. Do not describe planned work as done.
   Convert commit messages into past-tense result statements (e.g., "Added X", not "Add X").
3. In the test section, check only what appears in the stage 40 `실행한 명령` table.
   Show the commands and results inside a `<details>` block.
4. In the checklist, check only the items that passed in stage 40.
5. **LLMOps**: if the stage 40 LLMOps check flagged any item, add an entry to the
   `💬 체크` section stating the eval results (Before/After metrics) are attached
   (`CONTRIBUTING.md` §9.5).
6. If a related ADR is applicable, name the file (e.g., `docs/adr/ADR-003-sse-fetch-stream.md`)
   in the `💬 체크` section.
7. Output the PR title and body, then wait for approval.
   Register on GitHub only after the user confirms.

Registration command (run after approval):
```bash
gh pr create \
  --draft \
  --title "<PR title>" \
  --body "$(cat <<'EOF'
<PR body>
EOF
)" \
  --base develop
```

## Output format

- PR 제목
- PR 본문 (template format, guidance comments removed)
- Outside the body: base branch, Draft status, label suggestions, empty values and questions

## Do not

- Describe planned work as done.
- Check test items not in the stage 40 `실행한 명령` table.
- Register without explicit approval from the user.
- Include CI check results in the PR body — CI failures are notified separately.
- Include secrets or environment variable values in the body.
- Assign reviewers — this is a solo project; no reviewer assignment is needed.

## Human gate

- The user reviews the body, fills in any empty values, and says to register.
- After registration: check that the PR is in Draft status and the Issue is linked (`Closes #N`).
- Switch the PR to Ready for review when all checks pass and the work is ready to merge.
- Merge strategy: Squash and merge to `develop`.
