![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider.svg](images/accent-divider.svg)
# Applications
User facing applications that are applied thru ArgoCD on top of the k3s tech stack

![accent-divider](images/accent-divider.svg)
## PiHole: **Website:** [https://pi-hole.net](https://pi-hole.net)
- Network-wide DNS sinkhole for ads and tracking.
- Blocks ads at the network level (including in-app and smart-TV).
- Web admin interface and API; ideal on Raspberry Pi or any Linux box.
- All `*.seadogger-homelab` hostnames are static `dnsmasq` records defined in
  `core/deployments/pihole/pihole-values.yaml` (`dnsmasq.customDnsEntries`) —
  add a new app's hostname there, not through the Pi-hole UI, so it survives
  a redeploy.
- **30-Minute Pause button** on the portal calls a small backend
  (`deployments/pihole-toggle`, Pro repo) that holds the Pi-hole admin
  password server-side and calls Pi-hole's v6 API
  (`POST /api/dns/blocking`) — the password never reaches the browser.
![PiHole](images/PiHole-Dashboard.png)

![accent-divider](images/accent-divider.svg)
## Home Assistant: **Website:** [https://www.home-assistant.io](https://www.home-assistant.io)
- Home automation hub, deployed via the community
  [pajikos/home-assistant-helm-chart](https://github.com/pajikos/home-assistant-helm-chart)
  (`deployments/home-assistant` + `ansible/tasks/ha_deploy.yml`) — chart
  version pinned explicitly.
- **Container mode, no Supervisor:** Core + HACS only. There is no
  add-on store — anything you'd install as a Supervisor add-on
  (Mosquitto, Zigbee2MQTT, ESPHome) needs to run as its own pod instead.
- **No `hostNetwork`, no node-pinning:** standard pod networking, since
  no USB Zigbee/Z-Wave radio is attached. mDNS-based discovery (HomeKit,
  Chromecast, local device auto-discovery) will not work without
  `hostNetwork: true` — revisit if that's ever needed.
- **Reverse-proxy trust required:** HA rejects requests from a reverse
  proxy it doesn't recognize (`400 Bad Request`, "not set-up for reverse
  proxies"). Since we route via our own Traefik `IngressRoute` rather
  than the chart's own `Ingress`, `ingress.external: true` +
  `configuration.enabled: true` in the values file is what makes HA emit
  the `http.use_x_forwarded_for` / `trusted_proxies` config — without it,
  every request 400s.
- **`configuration.yaml` is only regenerated if missing** — the chart's
  init container copies its templated config to the PVC once and never
  again once the file exists. After changing `configuration.templateConfig`
  values, you must delete `/config/configuration.yaml` from the running
  pod and restart it for the new template to actually apply.
- **HACS install:** `wget -O - https://get.hacs.xyz | bash -` run inside
  the pod (`kubectl exec ... -- bash -c "..."`), then restart the pod.
  Not pre-installed by default.
- **Dashboard editing via code:** see **[[17-Runbooks]]** →
  "Edit a Home Assistant Dashboard via Code" for a reusable script
  (`deployments/home-assistant/ha_dashboard_edit.py`) that
  edits Lovelace dashboards through HA's own WebSocket API
  (`lovelace/config` /
  `lovelace/config/save`) instead of hand-editing the live `.storage`
  file.
- **RTSP cameras:** the two Amcrest IP2M-844E cameras (front door, pool)
  are wired in via the core **ONVIF** integration (manual IP entry —
  WS-Discovery/UDP multicast doesn't reach the pod, so auto-discovery
  finds nothing) rather than a standalone go2rtc app. Replaced the old
  `cameras` app (removed; see git history), which was a 2-3fps
  JPEG-polling stopgap.
- Storage: `ceph-block-data` (RBD), single replica — HA's SQLite recorder
  DB needs a single writer.

![accent-divider](images/accent-divider.svg)
## Mealie: **Website:** [https://mealie.io](https://mealie.io)
- Self-hosted recipe manager and meal planner
  ([mealie-recipes/mealie](https://github.com/mealie-recipes/mealie)).
- Plain hand-written manifests (`deployments/mealie` +
  `ansible/tasks/mealie_deploy.yml`), not a Helm chart — no third-party
  chart for Mealie has real community adoption, so this follows the
  same self-contained-Kustomize pattern used elsewhere in this repo.
- SQLite backend (default, no separate Postgres needed) on
  `ceph-block-data`, `Recreate` deploy strategy (single writer).
- Image pinned (not `:latest`) — bump deliberately, verify after.

### Home Assistant Integration
- HA's built-in `mealie` integration (core since 2024.7) connects directly
  to Mealie's API — no HACS plugin needed.
- **Use the in-cluster Service DNS, not the Pi-hole hostname.** HA/Mealie
  pods resolve DNS through k3s's CoreDNS, which has no record for
  `mealie.seadogger-homelab` (that name only exists in Pi-hole's
  `dnsmasq.customDnsEntries`, used by browsers/LAN clients). Configure the
  integration's host as
  `http://mealie.mealie.svc.cluster.local:9000` instead.
- Exposes one `calendar.mealie_<type>` entity per meal-plan entry type
  (breakfast/lunch/dinner/side/snack/drink/dessert) plus stat sensors
  (`sensor.mealie_recipes`, etc.). Calendars stay empty until a recipe is
  assigned to a date in Mealie's **Meal Plan** view.
- The family dashboard's "Today's Meals" card
  (`custom:calendar-card-pro`, `days_to_show: 1`) reads these calendar
  entities directly — one color-coded row per meal type. See
  [Meal-Planning Workflow](#meal-planning-workflow) below.
- HA polls Mealie on its own interval; to force an immediate refresh after
  a manual test, reload the config entry:
  `POST /api/config/config_entries/entry/{entry_id}/reload`.

### AI Features (Recipe Import, Ingredient Parsing)
Mealie's AI provider is wired to the in-cluster
[AWS Bedrock Access Gateway](#aws-bedrock-access-gateway-websiterepo-httpsgithubcomaws-samplesbedrock-access-gateway),
configured through Mealie's own **Group Settings → AI Providers** API
(`/api/groups/ai-providers/*`) — not env vars (that changed as of
Mealie v1.7+/v3.10+, which moved AI config out of `OPENAI_*` container
env vars and into per-group UI/API settings).

- **Endpoint:** `http://bedrock-access-gateway-service.bedrock-gateway.svc.cluster.local:6880/api/v1`
  (in-cluster Service DNS — same DNS caveat as above applies here too).
- **Model:** `us.anthropic.claude-haiku-4-5-20251001-v1:0` — the only
  model tested that produces clean, schema-conformant JSON through this
  gateway. See "Model compatibility" below for why other models don't
  work as-is.
- **API key:** the gateway's own static key (`bedrock`), not a real
  Anthropic/OpenAI key.

#### Structured-output enforcement (gateway patch)
Mealie's AI client uses the OpenAI Python SDK's structured-output helper
(`client.chat.completions.parse()`), which sends a `response_format:
json_schema` on every request and expects the model to return **only**
raw JSON matching that schema — no markdown, no preamble. As of upstream
commit `274b794e` (2026-06-18), the AWS Bedrock Access Gateway silently
**dropped `response_format` entirely** — it was accepted by the request
schema but never translated into anything Bedrock understands, so every
model just free-texted its own natural style and Mealie's strict
`json.loads()` broke unpredictably (Claude sometimes wrapped output in
` ```json ` fences, sometimes didn't).

This is a confirmed, tracked upstream gap
([aws-samples/bedrock-access-gateway#162](https://github.com/aws-samples/bedrock-access-gateway/issues/162),
[#255](https://github.com/aws-samples/bedrock-access-gateway/issues/255)) —
not a config option we were missing. A complete, tested fix exists as an
**open, unmerged PR** ([#255](https://github.com/aws-samples/bedrock-access-gateway/pull/255),
branch `nijave:nv-response-format`) that maps `response_format.json_schema`
to Bedrock's native `outputConfig.textFormat` — real schema enforcement
at the AWS API level, not a prompt trick.

`core/.github/workflows/upstream-rebuild.yaml` cherry-picks that PR's
single commit on top of a fresh checkout of `aws-samples/main` on every
scheduled rebuild (every 6h), so we still track all other upstream
changes automatically and don't freeze at a stale fork. If the cherry-pick
ever conflicts (upstream changed something the patch touches), the
workflow fails loudly rather than silently building without the fix —
check the Action run and rebase manually if that happens. **Remove the
cherry-pick step once PR #255 actually merges upstream.**

Verified post-patch: 5/5 consecutive real ingredient-parse calls through
Mealie returned clean HTTP 200 JSON with no fences, no reasoning tags,
correct schema shape.

#### Model compatibility (why not gpt-oss or Nova?)
Even with the gateway patch, only Claude is currently usable:

| Model | Result |
|---|---|
| `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Works — clean structured output via `outputConfig.textFormat` |
| `openai.gpt-oss-20b-1:0` / `120b` | Still wraps output in `<think>...</think>` reasoning tags before the JSON, **even with structured output enabled** — confirmed via direct testing post-patch. This is the model's native "harmony format" output; the gateway's reasoning-separation feature (which cleanly splits `reasoning_content` for Claude/DeepSeek) is not implemented for gpt-oss — `reasoning_content` is always `null` for this model family regardless of `reasoning_effort`. This is a separate, gpt-oss-specific gap, not fixed by PR #255. |
| `us.amazon.nova-lite-v1:0` | Not re-tested after the patch; previously ignored the schema's object wrapper (returned a bare list instead of `{"ingredients": [...]}`) |

**Note:** AWS Bedrock does not host OpenAI's proprietary models (GPT-4o,
GPT-5, etc.) in any region — verified directly against the Bedrock
`list-foundation-models` API in 5 regions. Only OpenAI's open-weight
`gpt-oss` line is available on Bedrock; the closed GPT models remain
exclusive to OpenAI's own API / Azure OpenAI.

#### Custom prompts (defense in depth)
Custom prompt overrides also live in `deployments/mealie/prompts/recipes/`
and are mounted into the pod via a Kustomize `configMapGenerator`. These
predate the gateway patch above (added when prompt wording was the only
lever available) and are kept as a second layer of protection — cheap
insurance in case a future model or gateway regression stops enforcing
the schema again:

- ConfigMap `mealie-custom-prompts` mounted at
  `/app/custom-prompts/recipes/` (Mealie expects this exact subdirectory
  — prompt names like `recipes.parse-recipe-ingredients` map to
  `<custom_dir>/recipes/parse-recipe-ingredients.txt`).
- `OPENAI_CUSTOM_PROMPT_DIR=/app/custom-prompts` env var on the Mealie
  deployment tells it to check there first, falling back to Mealie's
  built-in prompts if a file is missing.
- Each of the 4 prompt files (ingredient parsing, image-to-recipe,
  video-to-recipe, URL-scrape) opens and closes with an explicit,
  repeated instruction: *"first character of your response must be `{`,
  no code fences, no `<think>` tags."*
- Kustomize's `configMapGenerator` content-hashes the ConfigMap name, so
  editing a prompt file and re-deploying automatically rolls the Mealie
  pod to pick up the change — no manual restart needed.

#### Meal-Planning Workflow
1. **Add a recipe.** Either **+ Create → Import from URL** (Mealie tries
   its normal scraper first; if the page lacks clean recipe markup, it
   automatically falls back to the AI provider above) or add one by hand.
2. **Assign it to a date.** Mealie → **Meal Plan** → click a date →
   choose an entry type (Breakfast/Lunch/Dinner/etc.) → search/select the
   recipe → Save.
3. **It appears on the dashboard automatically.** HA polls the `mealie`
   integration periodically; the matching `calendar.mealie_<type>` entity
   updates, and the "Today's Meals" card on the family dashboard reflects
   it without any manual step.

#### Forcing the AI Import Path
Mealie's scraper-selection order is hardcoded server-side
(`RecipeScraperPackage` always tries first; the AI scraper only runs if
that returns nothing at all) — there is no request-level way to force AI
for a page the plain scraper can technically read but parses badly (e.g.
duplicated/mislabeled instruction steps from pages that interleave
step-number labels with restated ingredient lists). Today, the only
workaround is manual: fetch the page, extract just the visible recipe
text (no HTML/JSON-LD for the plain scraper to grab), and POST it to
`/api/recipes/create/html-or-json` directly via the API.

Two real, tested, unmerged upstream PRs fix this properly by adding
actual UI controls:
- [#7618](https://github.com/mealie-recipes/mealie/pull/7618) — a
  "Force OpenAI Scraper" checkbox on the Import-from-URL page
- [#7825](https://github.com/mealie-recipes/mealie/pull/7825) — a
  dedicated "Create from Text" page

Both are cherry-picked into a custom image
(`ghcr.io/seadogger-tech/mealie:v3.21.0-ai-import`) built by
`core/.github/workflows/mealie-rebuild.yaml`, following the same
adopted-unmerged-PR pattern established for the Bedrock gateway — see
[ADR-011](13-ADR-Index.md#adr-011-adopting-unmerged-upstream-prs-reusable-pattern).
Unlike the gateway, this pipeline is pinned to a specific upstream
**release tag** (`v3.21.0`), not the active `mealie-next` development
branch — Mealie holds real household data, so unattended tracking of
in-progress upstream commits would be inappropriate here. The pipeline
only rebuilds when the cherry-picked PRs change or `UPSTREAM_TAG` is
bumped manually.

![accent-divider](images/accent-divider.svg)
## OpenWebUI: **Website:** [https://open-webui.com](https://open-webui.com)
- Self-hosted web UI for local/remote LLMs.
- Works offline; supports multiple LLM runners; chat, RAG, and extensions.
- Installable as a PWA for a smooth mobile experience.

<p align="center">
  <img src="images/WebUI-iPhone-UI.png" alt="OpenWebUI on iPhone" width="180">
  &nbsp;&nbsp;&nbsp;
  <img src="images/WebUI-Laptop-UI.png" alt="OpenWebUI on Laptop" width="1024">
</p>

![accent-divider](images/accent-divider.svg)
## AWS Bedrock Access Gateway: **Website/Repo:** [https://github.com/aws-samples/bedrock-access-gateway](https://github.com/aws-samples/bedrock-access-gateway)
- Open-source gateway that exposes **OpenAI-compatible REST APIs** for **Amazon Bedrock**.
- Lets existing OpenAI SDKs/tools (e.g., OpenAI Python/JS, LangChain-OpenAI, AutoGen) work with Bedrock **without code changes**.
- Supports **SSE streaming**, **Chat Completions**, **Embeddings**, **Tool/function calling**, **Multimodal**, **Models API**, **Cross-region inference**, and **Application Inference Profiles**.
- **Easy deployment:** 1-click CloudFormation to **ALB + Lambda** or **ALB + Fargate**; also runs **locally** or in **containers/Kubernetes**.
- Regions & models: follows **Bedrock-supported regions**; use the **Models API** to discover availability.

### Deployment Architecture
- **Automated Upstream Tracking:** GitHub Actions workflow rebuilds image every 6 hours from [aws-samples/bedrock-access-gateway](https://github.com/aws-samples/bedrock-access-gateway)
- **Multi-arch Support:** Built for `linux/amd64` and `linux/arm64` (Raspberry Pi 5 compatible)
- **Image Registry:** `ghcr.io/seadogger-tech/aws-bedrock-gateway:latest`
- **Access:** MetalLB LoadBalancer at `192.168.1.242:6880`
- **Integration:** Confirmed actively connected to OpenWebUI's chat
  interface — verified via OpenWebUI's own stored connection config
  (`openai.api_base_urls` in its `webui.db`), pointed at
  `http://192.168.1.242:6880/api/v1` with the same static `bedrock` key.

### Configuration Requirements
1. **AWS Bedrock Model Access:**
   - Enable models in AWS Bedrock console for the deployment region (us-west-2)
   - Cross-region inference profiles (`us.*` prefix) require separate access grants
   - Example: `us.anthropic.claude-opus-4-1-20250805-v1:0` requires both base model and inference profile access

2. **IAM Permissions:**
   - User must have `AmazonBedrockFullAccess` policy or equivalent
   - Credentials stored as Kubernetes secret in `bedrock-gateway` namespace
   - Environment variables: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`

3. **Gateway Authentication:**
   - **API_KEY:** `bedrock` (used by clients to authenticate to the gateway)
   - Clients must include header: `Authorization: Bearer bedrock`
   - This is separate from AWS credentials (gateway → Bedrock authentication)

4. **Container Configuration:**
   - Container listens on port **8080** (upstream default as of 2025)
   - Service exposes externally on port **6880** via MetalLB

5. **Known Issues & Solutions:**
   - **Model returns AccessDeniedException:** Enable the specific model in AWS Bedrock console for us-west-2
   - **Requests hang without response:** Restart deployment to pull latest gateway image (`kubectl rollout restart deployment/bedrock-access-gateway -n bedrock-gateway`)
   - **Parameter validation errors:** Upstream fixes auto-deployed (e.g., Claude Sonnet 4.5 temperature/top_p conflict fixed in latest)
   - **Pod CrashLoopBackOff "API Key not configured":** Ensure `API_KEY` env var is set (upstream removed default in Feb 2025)
   - **gpt-oss models leak `<think>...</think>` reasoning tags into `content`:** confirmed via direct testing (`reasoning_content` field always `null` for `openai.gpt-oss-20b-1:0`/`120b`, regardless of `reasoning_effort`), even with `response_format` structured output enabled (see below). The gateway's reasoning-separation feature only covers Claude and DeepSeek R1. Breaks any client (like Mealie) expecting strict JSON-only output. Use Claude instead until the gateway adds gpt-oss support.
   - **`response_format`/`json_schema` was silently ignored (fixed as of 2026-07-25):** upstream never implemented OpenAI's structured-output contract — accepted the field, never enforced it, so every model free-texted its own JSON style (Claude sometimes fenced in ` ```json `, breaking strict clients like Mealie). Tracked upstream as [#162](https://github.com/aws-samples/bedrock-access-gateway/issues/162)/[#255](https://github.com/aws-samples/bedrock-access-gateway/issues/255), fixed here by cherry-picking the unmerged [PR #255](https://github.com/aws-samples/bedrock-access-gateway/pull/255) in `upstream-rebuild.yaml` — see [Mealie § Structured-output enforcement](#structured-output-enforcement-gateway-patch) for full details.

### Adopted Unmerged Upstream PRs
`upstream-rebuild.yaml` cherry-picks 6 open, unmerged PRs on top of a
fresh checkout of `aws-samples/main` on every scheduled rebuild — see
[ADR-011](13-ADR-Index.md#adr-011-adopting-unmerged-upstream-prs-reusable-pattern)
for the full rationale and the reusable pattern this establishes.
Verified working end-to-end against the live deployed image
(2026-07-25):

| PR | Fixes | Verified via |
|---|---|---|
| [#255](https://github.com/aws-samples/bedrock-access-gateway/pull/255) | `response_format`/`json_schema` → real Bedrock structured output | Direct `curl` test + 5/5 clean Mealie ingredient-parse calls |
| [#246](https://github.com/aws-samples/bedrock-access-gateway/pull/246) | Drop orphan `tool_use`/`tool_result` pairs (OpenWebUI history-rewrite scenario) | `grep -n _sanitize_tool_pairs /app/api/models/bedrock.py` on the live pod |
| [#247](https://github.com/aws-samples/bedrock-access-gateway/pull/247) | Non-negative tool-call indexes in streaming | Present in cherry-picked commit history |
| [#239](https://github.com/aws-samples/bedrock-access-gateway/pull/239) | Replayed tool blocks without a `tools` array (conversation compaction) | Present in cherry-picked commit history |
| [#198](https://github.com/aws-samples/bedrock-access-gateway/pull/198) | Return `tool_calls` instead of dropping them on `max_tokens` truncation | Present in cherry-picked commit history |
| [#249](https://github.com/aws-samples/bedrock-access-gateway/pull/249) | Claude Opus 4.7 adaptive-thinking request format | `grep -n ADAPTIVE_THINKING_MODELS /app/api/models/bedrock.py` on the live pod |

`#246`/`#247`/`#239`/`#198` protect OpenWebUI's tool/function-calling
path, which isn't enabled today (0 Tools/Functions configured in its
`webui.db` as of this writing) but would hit these exact bugs the
moment it is. `#249` is a live gap regardless — Opus 4.7 is already
selectable in OpenWebUI's model dropdown.

Two of the six conflict with each other in small, known ways (both
`#255` and `#239` add a branch in `_parse_request`; `#198` and `#239`
touch the same log line). Resolved by
`.github/scripts/resolve_bedrock_gateway_conflicts.py`, not inline in
the workflow YAML — see the script's docstring for exactly what each
resolver does and why.

![Bedrock](images/bedrock.png)


![accent-divider](images/accent-divider.svg)
## NextCloud: **Website:** [https://nextcloud.com](https://nextcloud.com)
- Open-source, self-hosted content-collaboration and file-sync platform.
- Files & sharing, Office (collaborative editing), Calendar, Contacts, Talk (chat/video).
- Desktop & mobile clients; extensible via a large app ecosystem.
![NextCloud](images/nextcloud-dashboard.png)

## HDHomeRun Guide Utility

A tiny Python utility that pulls the HDHomeRun XMLTV guide and stores it locally.  
It can be run with:

```bash
# Default (no target, saves to xmltv.xml in current directory)
./fetch_hdhomerun_guide.py \
    --discover-url http://192.168.1.70/discover.json

# Save to a specific location
./fetch_hdhomerun_guide.py \
    --discover-url http://192.168.1.70/discover.json \
    --target /media/data/HomeMedia/files/Live_TV_Guide/xmltv.xml
```

The script lives in `seadogger-homelab-pro/core/useful_scripts/fetch_hdhomerun_guide.py` and is documented in the wiki page **[HDHomeRun Guide Utility](20-HDHomeRun-Guide.md)**.


![accent-divider](images/accent-divider.svg)
## Ember Trail
- Family road-trip planner — custom app (`deployments/ember-trail`, Pro
  repo), a small Python state server behind Caddy, not a third-party project.

![accent-divider](images/accent-divider.svg)
## Signal-CLI
- Headless Signal messenger client
  ([AsamK/signal-cli](https://github.com/AsamK/signal-cli)) exposed as an
  HTTP daemon, used by Hermes agents to send/receive Signal messages.
- Built via `core/deployments/signal-cli/Dockerfile`, rebuilt automatically
  every time upstream cuts a release (`core/.github/workflows/upstream-rebuild-signal-cli.yaml`).
- The daemon's own HTTP server rejects requests carrying a Kubernetes
  Service `Host` header (`421`), so an nginx sidecar rewrites the `Host`
  header before proxying to it.

![accent-divider](images/accent-divider.svg)
## Terminal
- Browser-accessible cluster shell:
  [ttyd](https://github.com/tsl0922/ttyd) serving a terminal with `kubectl`
  pre-installed (copied in from the `bitnami/kubectl` image at pod start),
  bound to a `ServiceAccount` via RBAC (`deployments/terminal/rbac.yaml`)
  rather than requiring a separate login.

![accent-divider](images/accent-divider.svg)
## JellyFin: **Website:** [https://jellyfin.org](https://jellyfin.org)
- Free, open-source, self-hosted media server.
- Lets you organize and stream movies, TV, music, and photos to many devices.
- Runs on Windows, Linux, macOS, Docker, and more.
- Web UI and apps; supports Live TV/DVR and DLNA.
- Hardware-accelerated transcoding via FFmpeg when available.
- 100% free—no tracking and no premium tiers.
![JellyFin](images/jellyfin-dashboard.png)

![accent-divider](images/accent-divider.svg)
## See Also

- **[[18-Setting-Up-n8n-Connections]]** - N8N configuration guide
- **[[20-HDHomeRun-Guide]]** - Jellyfin live TV setup
- **[[06-Storage-Rook-Ceph]]** - Application storage backends
- **[[08-Security-and-Certificates]]** - Application TLS certificates

**Setup Guides:**
- [#34 - Get passwords](https://github.com/seadogger-tech/seadogger-homelab/issues/34)
- [#35 - PiHole whitelist](https://github.com/seadogger-tech/seadogger-homelab/issues/35)
- [#36 - OpenWebUI Bedrock](https://github.com/seadogger-tech/seadogger-homelab/issues/36)
- [#37 - Jellyfin XMLTV](https://github.com/seadogger-tech/seadogger-homelab/issues/37)
- [#38 - Nextcloud setup](https://github.com/seadogger-tech/seadogger-homelab/issues/38)
- [#39 - N8N workflows](https://github.com/seadogger-tech/seadogger-homelab/issues/39)
