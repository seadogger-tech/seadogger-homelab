![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider](images/accent-divider.svg)
# CI/CD and GitHub Actions

This repository uses two main GitHub Actions workflows for automation.

![accent-divider](images/accent-divider.svg)
## Publish Wiki
- File: `core/.github/workflows/publish-wiki.yml`
- Purpose: Sync `docs/wiki/**` in the source repo to the GitHub Wiki repository.
- Safety guard: Runs only on the default branch of `seadogger-tech/seadogger-homelab`.
- Manual mode: `workflow_dispatch` input `autogen=true` will run `docs/wiki/tools/build_all.py` before syncing.
- Auth: Requires repo secret `WIKI_TOKEN` (fine-grained PAT with wiki write access) used to clone `seadogger-homelab.wiki.git`.
- Steps overview:
  1. Checkout source (no default creds)
  2. Optionally generate pages with `build_all.py`
  3. Clone wiki repo using PAT
  4. `rsync` markdown, images, and memory_bank into wiki repo
  5. Commit and push if changes exist

![accent-divider](images/accent-divider.svg)
## Upstream Bedrock Gateway Rebuild
- File: `core/.github/workflows/upstream-rebuild.yaml`
- Purpose: Poll `aws-samples/bedrock-access-gateway` for changes, then build and push a fresh multi-arch image.
- Schedule: Every 6 hours (plus manual `workflow_dispatch`).
- Registry: `ghcr.io/seadogger-tech/aws-bedrock-gateway` (tags: `latest`, `sha-<short>`).
- Change detection: Stores last upstream SHA in `.github/upstream_sha`; skips no-op builds.
- Steps overview:
  1. Checkout this repo (branch `master` by default) to read/write `.github/upstream_sha`
  2. Checkout upstream repo (default branch) to compute the new SHA
  3. If changed: setup QEMU/Buildx, login to GHCR, build+push `linux/amd64,linux/arm64`
  4. Commit the new SHA back to this repo for the next run

![accent-divider](images/accent-divider.svg)
## Adapting/Extending
- To use the wiki publisher in another repo, adjust the `if:` guard to your repository and provide a suitable PAT secret.
- To change the image path or cadence of the upstream rebuild, edit the `IMAGE` env and `schedule` cron; ensure `packages: write` permission.

