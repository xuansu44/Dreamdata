---
name: planning-release
description: How to plan a dreamdata release — review current state, design user stories, present to PM, record the plan.
---

# Release Planning Pattern

## When to Use This

When starting a new phase or release (v0.3.0, v0.4.0, etc.).

## Steps

### Step 1: Review Current State

First establish the baseline:

```bash
git status
git log -5 --oneline
python scripts/run_local_tests.py --quick
```

Capture:
- Current version and what's shipped
- Coverage stats
- CI status (green/red)
- Tech debt report
- Unmet user needs

### Step 2: Design User Stories

Write stories in this format:

```
As a [persona], I want [goal] so that [business value].
```

Personas:
- Data Scientist (primary user)
- Data Engineer
- ML Engineer
- Operator/SRE

Guidelines:
- 3–5 stories per release
- No implementation details in stories
- Focus on user value, not features

### Step 3: Present to PM

Present in this order:
1. **Current State** (1 slide)
2. **User Stories** (1 per story, no implementation)
3. **Wait for PM approval** before proceeding
4. **Feature Breakdown** (map features to stories)
5. **Test Strategy** (per-layer plan)
6. **Non-negotiables + Out of Scope**

### Step 4: Record Approved Plan

Update `.mex/ROUTER.md`:

```markdown
## vX.Y.Z Planning (Phase N: [description])

**Scope:** [what's in this release]
**Status:** PM Approved ([date])

### User Stories (PM Approved)
1. **Story 1:** As a..., I want... so that...
...

### Features (FX–FY) (PM Approved)
- **FX:** [feature description]
  - [endpoint/UI component]
...

### Non-Negotiables (PM Approved)
| Rule | Reason |
|------|--------|
| ... | ... |

### Test Strategy (PM Approved)
- L1: ...
- ...

### Out of Scope (Deferred to vX.Y.Z+) (PM Approved)
- ...
```

Also:
- Bump `last_updated` in ROUTER.md
- Update any context files if needed

## Example

See ROUTER.md v0.3.0 planning for a complete example.
