#!/usr/bin/env bash
# Report whether <tag> exists for a GHCR image, without touching git.
#
# Usage: ghcr_tag_exists.sh <owner/image> <tag>
#
# Prints "exists=true" or "exists=false" (also appended to $GITHUB_OUTPUT when
# set). Only a registry 404 on the manifest means "absent". Any other outcome
# - token failure, 401/403, 5xx, network error - exits non-zero so a registry
# problem can never be mistaken for a missing image and trigger a rebuild.
#
# Env: GITHUB_TOKEN + GITHUB_ACTOR (optional; anonymous pull works for public
# packages), GHCR_URL (default https://ghcr.io, overridable for tests).
set -euo pipefail

if [[ $# -ne 2 || -z "$1" || -z "$2" ]]; then
  echo "usage: $0 <owner/image> <tag>" >&2
  exit 2
fi
repo="$1"
tag="$2"
base="${GHCR_URL:-https://ghcr.io}"

curl_opts=(--silent --show-error --max-time 30 --retry 3 --retry-delay 2)
auth=()
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  auth=(--user "${GITHUB_ACTOR:-token}:${GITHUB_TOKEN}")
fi

body="$(mktemp)"
trap 'rm -f "$body"' EXIT

code="$(curl "${curl_opts[@]}" "${auth[@]}" --output "$body" --write-out '%{http_code}' \
  "${base}/token?service=ghcr.io&scope=repository:${repo}:pull")" || {
  echo "::error::GHCR token request failed (network error)" >&2; exit 1; }
if [[ "$code" != "200" ]]; then
  echo "::error::GHCR token request returned HTTP ${code}; cannot tell whether ${repo}:${tag} exists" >&2
  exit 1
fi
token="$(jq -er '.token // empty' "$body")" || {
  echo "::error::GHCR token response had no token" >&2; exit 1; }

code="$(curl "${curl_opts[@]}" --head --output /dev/null --write-out '%{http_code}' \
  -H "Authorization: Bearer ${token}" \
  -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json' \
  "${base}/v2/${repo}/manifests/${tag}")" || {
  echo "::error::GHCR manifest request failed (network error)" >&2; exit 1; }

case "$code" in
  200) result=true ;;
  404) result=false ;;
  *)
    echo "::error::GHCR manifest check for ${repo}:${tag} returned HTTP ${code}; not treating as absent" >&2
    exit 1
    ;;
esac

echo "${repo}:${tag} exists=${result}" >&2
echo "exists=${result}"
[[ -z "${GITHUB_OUTPUT:-}" ]] || echo "exists=${result}" >> "$GITHUB_OUTPUT"
