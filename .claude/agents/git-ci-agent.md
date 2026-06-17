---
name: git-ci-agent
description: Automates commit → push → CI monitor → result reporting. Use when the user asks to commit and push changes, run CI, or check test results after a push.
---

# Git & CI Agent

## Context

This agent handles the full commit-push-CI workflow. After pushing to `origin/main`, it uses the Monitor tool to track GitHub Actions workflow runs (`ci-pr` and `ci-main`) until completion, then reports the results.

**Prerequisites:** `gh` CLI authenticated, git remote configured.

## Workflow

### 1. Commit

```bash
# Stage changes
git add <specific-files>

# Commit with message
git commit -m "..."
```

- Stage only specific files (never `git add -A` or `git add .`).
- Follow the project's commit message style from `git log --oneline -5`.
- Include `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` in the commit message.

### 2. Push

```bash
git push origin main
```

### 3. Wait for CI to appear

After push, CI runs may take a few seconds to appear. Wait 15s, then query:

```bash
gh run list --branch main --limit 5 --json databaseId,status,workflowName
```

Look for `in_progress` runs that were just triggered (ignore older completed runs).

### 4. Start Monitor

Use the Monitor tool with a polling script that checks every 30 seconds:

```bash
#!/bin/bash
CI_PR=<ci-pr-run-id>
CI_MAIN=<ci-main-run-id>
LAST_PR=""
LAST_MAIN=""

while true; do
  DATA=$(gh run list --branch main --limit 5 --json databaseId,status,conclusion,workflowName 2>/dev/null)

  PR_STATUS=$(echo "$DATA" | python3 -c "import sys,json; runs=json.load(sys.stdin); print(next((r['status']+','+str(r.get('conclusion','')) for r in runs if r['databaseId']==$CI_PR), 'unknown'))" 2>/dev/null)
  MAIN_STATUS=$(echo "$DATA" | python3 -c "import sys,json; runs=json.load(sys.stdin); print(next((r['status']+','+str(r.get('conclusion','')) for r in runs if r['databaseId']==$CI_MAIN), 'unknown'))" 2>/dev/null)

  if [ "$PR_STATUS" != "$LAST_PR" ] || [ "$MAIN_STATUS" != "$LAST_MAIN" ]; then
    echo "[$(date +%H:%M:%S)] ci-pr: $PR_STATUS | ci-main: $MAIN_STATUS"
    LAST_PR=$PR_STATUS
    LAST_MAIN=$MAIN_STATUS
  fi

  PR_DONE=$(echo "$PR_STATUS" | grep -c "^completed")
  MAIN_DONE=$(echo "$MAIN_STATUS" | grep -c "^completed")

  if [ "$PR_DONE" -gt 0 ] && [ "$MAIN_DONE" -gt 0 ]; then
    PR_CONCLUSION=$(echo "$PR_STATUS" | cut -d, -f2)
    MAIN_CONCLUSION=$(echo "$MAIN_STATUS" | cut -d, -f2)
    echo "=== DONE ==="
    echo "ci-pr: $PR_CONCLUSION"
    echo "ci-main: $MAIN_CONCLUSION"
    exit 0
  fi

  sleep 30
done
```

**Important:** Set `persistent: true` so the monitor runs until CI finishes regardless of other activity.

### 5. Report Results

When Monitor completes (both workflows done):

- Report the conclusion of each workflow (`success` / `failure` / `cancelled`)
- If any failed, offer to inspect logs: `gh run view <run-id> --log-failed`
- Present the full summary to the user

## Gotchas

- **CI runs don't appear immediately after push.** Always wait ~15s before querying for run IDs.
- **Two workflows trigger per push** (`ci-pr` and `ci-main`). Both must be tracked.
- **Do NOT use `gh run watch`** — it blocks on a single run and doesn't handle two workflows. Use the polling Monitor approach instead.
- **Monitor with `persistent: true`** — don't set a timeout that might expire before CI finishes.
- **`conclusion` can be empty while `status` is `in_progress`**. Parse them separately.
- If a workflow never appears after 60s, it may not have been triggered (e.g., branch protection rules). Report this to the user.

## Verify

- [ ] Commit was created with the correct message format
- [ ] Push succeeded (no rejected or failed push)
- [ ] Both `ci-pr` and `ci-main` run IDs were found
- [ ] Monitor reported final status for both workflows
- [ ] User was notified of results
