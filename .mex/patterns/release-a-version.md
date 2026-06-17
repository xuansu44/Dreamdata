---
name: release-a-version
description: How to cut a release using the project's Release Agent — version bump, git tag, CI monitoring, GitHub Release
triggers:
  - "release"
  - "cut a version"
  - "publish"
  - "github release"
edges:
  - target: context/process.md
    condition: when checking release policy or DoD
last_updated: 2026-06-17
---

# Release a Version

## Context

This project has a **Release Agent** that automates the full release workflow. The agent lives in the project (not global) under `.claude/`.

Before releasing:
- Make sure `main` is green on `ci-main.yml`
- Make sure working directory is clean (no uncommitted changes)
- Make sure `gh` (GitHub CLI) is authenticated (`gh auth status`)
- Follow semantic versioning: MAJOR (breaking), MINOR (new features), PATCH (fixes)

## Steps

### Option A: Use the Release Skill (recommended)

In Claude Code:

```
/release 0.2.0 "Adds advanced filtering and field indexing"
```

### Option B: Run the script directly

```bash
./scripts/release.py 0.2.0 "Adds advanced filtering and field indexing"
```

### Option C: Manual (emergency only)

Only if the Release Agent fails:

1. Update version in `pyproject.toml`
2. Commit: `git commit -m "Release v0.2.0"`
3. Tag: `git tag -a v0.2.0 -m "Release v0.2.0"`
4. Push: `git push && git push origin v0.2.0`
5. Wait for CI to pass
6. Build: `uv build`
7. Create GitHub Release manually

## Gotchas

- **Don't skip CI unless emergency** — `--skip-ci` flag exists but should only be used for hotfixes when CI is broken for unrelated reasons
- **Don't release from a dirty working directory** — the script blocks this; stash/commit first
- **Version numbers don't need `v` prefix** — the script normalizes it, but you can provide it or not
- **Chinese docs path** — make sure `ci-main.yml` builds Chinese docs to `docs/build/zh_CN`, not `docs/build/html/zh_CN` (fixed 2026-06-17)
- **GitHub Pages deploys automatically** — after CI passes, the `deploy-pages` job runs

## Verify After Release

- [ ] Check GitHub Actions: `gh run list` — should show green for the release commit
- [ ] Check GitHub Release page: https://github.com/xuansu44/Dreamdata/releases
- [ ] Check GitHub Pages: https://xuansu44/Dreamdata (and Chinese version at `/zh_CN/`)
- [ ] Verify artifacts are attached to the release
- [ ] Verify git tag exists: `git tag -l v0.2.0`

## Debug If Something Breaks

### Release script fails to find `gh`

```bash
gh auth status  # check if authenticated
gh auth login   # re-authenticate if needed
```

### CI fails after push

1. Check the CI logs: `gh run view <run-id>`
2. Fix the issue
3. If it's a docs issue, you may need to adjust Chinese docs paths
4. If you need to re-release, delete the tag first:
   ```bash
   git tag -d v0.2.0
   git push origin --delete v0.2.0
   ```

### GitHub Release didn't get created

1. Check if `dist/` has the built artifacts: `ls -la dist/`
2. Check if `gh release create` failed — re-run manually:
   ```bash
   gh release create v0.2.0 --title "v0.2.0" --notes "..." dist/*
   ```

## Update Scaffold

- [x] Updated `.mex/ROUTER.md` "Current Project State" to mention Release Agent
- [x] Updated `.mex/context/process.md` Release Policy section
- [x] Created this pattern file
- [ ] Add to `patterns/INDEX.md`
