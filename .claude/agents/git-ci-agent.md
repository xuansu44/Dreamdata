---
name: git-ci-agent
description: Automates commit → push → CI monitor → result reporting. Use when the user asks to commit and push changes, run CI, or check test results after a push.
---

# Git & CI Agent

## Context

This agent handles the full commit-push-CI workflow. After pushing to `origin/main`, it uses the Monitor tool to dynamically discover and track *all* triggered GitHub Actions workflow runs until completion, then reports the results.

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

### 3. Wait for CI to appear and discover runs

After push, CI runs may take a few seconds to appear. Wait 15s, then query:

```bash
gh run list --branch main --limit 10 --json databaseId,status,workflowName,createdAt,headSha
```

Find runs that:
- Were created *after* the push (compare `createdAt` timestamps)
- Match the current branch's `headSha`
- Are `in_progress` or `queued`

Collect all matching `databaseId` and `workflowName` pairs — track *all* of them, regardless of their names.

### 4. Start Monitor

Use the Monitor tool with a polling script that checks every 30 seconds:

```bash
#!/bin/bash
# JSON array of {id, name} pairs, e.g.: '[{"id":123,"name":"ci-pr"},{"id":456,"name":"ci-main"}]'
TRACKED_RUNS='<json-array-of-runs>'
LAST_OUTPUT=""

while true; do
  DATA=$(gh run list --branch main --limit 15 --json databaseId,status,conclusion,workflowName 2>/dev/null)

  # Parse current state
  CURRENT=$(echo "$DATA" | python3 -c "
import sys, json
tracked = $TRACKED_RUNS
runs = json.load(sys.stdin)
state = {}
for t in tracked:
    run = next((r for r in runs if r['databaseId'] == t['id']), None)
    if run:
        state[t['name']] = {
            'status': run['status'],
            'conclusion': run.get('conclusion', '')
        }
    else:
        state[t['name']] = {'status': 'unknown', 'conclusion': ''}
print(json.dumps(state))
" 2>/dev/null)

  # Generate output line
  OUTPUT_LINE=$(echo "$CURRENT" | python3 -c "
import sys, json
state = json.load(sys.stdin)
parts = []
for name, s in state.items():
    status = s['status']
    conc = s['conclusion']
    if status == 'completed' and conc:
        parts.append(f'{name}: {status}/{conc}')
    else:
        parts.append(f'{name}: {status}')
print(' | '.join(parts))
" 2>/dev/null)

  # Print if changed
  if [ "$OUTPUT_LINE" != "$LAST_OUTPUT" ]; then
    echo "[$(date +%H:%M:%S)] $OUTPUT_LINE"
    LAST_OUTPUT="$OUTPUT_LINE"
  fi

  # Check if all done
  ALL_DONE=$(echo "$CURRENT" | python3 -c "
import sys, json
state = json.load(sys.stdin)
all_completed = all(s['status'] == 'completed' for s in state.values())
print('1' if all_completed else '0')
" 2>/dev/null)

  if [ "$ALL_DONE" = "1" ]; then
    echo "=== DONE ==="
    echo "$CURRENT"
    exit 0
  fi

  sleep 30
done
```

**Important:** Set `persistent: true` so the monitor runs until CI finishes regardless of other activity.

### 5. Report Results

When Monitor completes (all workflows done):

1. **Parse the final JSON state**
2. **Report the conclusion of each workflow** (`success` / `failure` / `cancelled`) by name
3. **For any failed workflow, automatically fetch and analyze logs:**
   - First, get the failed jobs: `gh run view <run-id> --json jobs`
   - For each failed job, get the logs: `gh run view <run-id> --log-failed`
   - Extract the relevant failure details (test failures, error messages, coverage shortfalls, etc.)
4. **Present the full summary to the user**, including:
   - Overall status (success/failure) per workflow
   - Detailed failure reasons for any failed runs
   - Key excerpts from the logs
   - Next-step suggestions (fix the issue, adjust coverage threshold, etc.)

## Gotchas

- **CI runs don't appear immediately after push.** Always wait ~15s before querying for run IDs.
- **Track *all* workflows that trigger**, not just specific names.
- **Do NOT use `gh run watch`** — it blocks on a single run and doesn't handle multiple workflows. Use the polling Monitor approach instead.
- **Monitor with `persistent: true`** — don't set a timeout that might expire before CI finishes.
- **`conclusion` can be empty while `status` is `in_progress`**. Parse them separately.
- If no workflows appear after 60s, it may not have been triggered (e.g., branch protection rules). Report this to the user.

## Verify

- [ ] Commit was created with the correct message format
- [ ] Push succeeded (no rejected or failed push)
- [ ] All triggered workflows were discovered (no hardcoded names)
- [ ] Monitor reported final status for all workflows
- [ ] User was notified of results
