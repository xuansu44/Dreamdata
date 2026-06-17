---
name: git-ci-workflow
description: Commit, push, and monitor CI via Monitor tool. Use when the user asks to commit changes, push, check CI status, or run tests after a push.
triggers:
  - "commit and push"
  - "push and CI"
  - "monitor CI"
  - "check CI"
  - "git push"
  - "run CI"
edges:
  - target: context/process.md
    condition: when reviewing CI pipeline expectations
  - target: ../agents/git-ci-agent.md
    condition: when loading the agent definition for the full workflow
last_updated: 2026-06-17 (Monitor approach validated)
---

# Git CI Workflow

## Context

After pushing to `origin/main`, two GitHub Actions workflows are triggered: `ci-pr` and `ci-main`. This pattern covers how to commit, push, and monitor both to completion.

## Steps

1. **Stage and commit** — stage only specific files, write commit message following project style
2. **Push** — `git push origin main`
3. **Wait and find CI runs** — sleep 15s, then query `gh run list` for `in_progress` runs
4. **Start Monitor** — use Monitor tool with a 30s polling script that tracks both `ci-pr` and `ci-main` until both are `completed`
5. **Report** — present final conclusions to the user; offer to inspect failures with `gh run view <run-id> --log-failed`

## Gotchas

- **Monitor with `persistent: true`** — CI can take minutes; don't use a timeout.
- **Two workflows per push** — `ci-pr` and `ci-main`. Track both.
- **Wait ~15s after push** before querying for run IDs — they don't appear instantly.

## Verify

- [ ] Commit created with correct message format
- [ ] Push succeeded
- [ ] Both workflow run IDs found
- [ ] Monitor completed and reported final status
