#!/bin/sh
# Run on the owner's controller (the Mac) after ANY change to ansible/config.yml, hosts.ini or the keys.
# Rebuilds Secret ansible-runner-private from the live local files so the runner never uses stale config.
# Usage: refresh-secret.sh /path/to/dedicated_key /path/to/known_hosts [/path/to/pro_deploy_key]
set -eu
KEY=${1:?dedicated ssh key}
KNOWN=${2:?known_hosts (nodes and github.com)}
PRO=${3:-}
CORE_ANSIBLE=${CORE_ANSIBLE:-ansible}
args="--from-file=config.yml=$CORE_ANSIBLE/config.yml --from-file=hosts.ini=$CORE_ANSIBLE/hosts.ini --from-file=id_ed25519=$KEY --from-file=known_hosts=$KNOWN"
[ -n "$PRO" ] && args="$args --from-file=pro_deploy_key=$PRO"
kubectl get ns ansible-runner >/dev/null 2>&1 || kubectl create ns ansible-runner
# shellcheck disable=SC2086
kubectl -n ansible-runner create secret generic ansible-runner-private $args --dry-run=client -o yaml | kubectl apply -f -
echo "config.yml sha256: $(shasum -a 256 "$CORE_ANSIBLE/config.yml" | cut -d' ' -f1)"
