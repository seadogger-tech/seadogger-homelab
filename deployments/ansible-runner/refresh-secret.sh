#!/bin/sh
# Run on the owner's controller (the Mac) after ANY change to ansible/config.yml, hosts.ini or the keys.
# Rebuilds Secret ansible-runner-private from the live local files so the runner never uses stale config.
# Usage: [PRO_CONFIG=/path/runner-pro-config.yml PRO_HOSTS=/path/pro-hosts.ini] refresh-secret.sh /path/to/dedicated_key /path/to/known_hosts [/path/to/pro_deploy_key]
set -eu
KEY=${1:?dedicated ssh key}
KNOWN=${2:?known_hosts (nodes and github.com)}
PRO=${3:-}
CORE_ANSIBLE=${CORE_ANSIBLE:-ansible}
set -- "--from-file=config.yml=$CORE_ANSIBLE/config.yml" "--from-file=hosts.ini=$CORE_ANSIBLE/hosts.ini" \
  "--from-file=id_ed25519=$KEY" "--from-file=known_hosts=$KNOWN"
if [ -n "$PRO" ]; then
  set -- "$@" "--from-file=pro_deploy_key=$PRO"
fi
# Pro runs need Pro's own inventory and a runner copy of Pro's config.yml
# (destructive and stage-2 flags false; see docs/wiki/28-Ansible-Runner.md).
if [ -n "${PRO_CONFIG:-}" ]; then
  set -- "$@" "--from-file=pro_config.yml=$PRO_CONFIG" "--from-file=pro_hosts.ini=${PRO_HOSTS:?PRO_HOSTS with PRO_CONFIG}"
fi
kubectl get ns ansible-runner >/dev/null 2>&1 || kubectl create ns ansible-runner
kubectl -n ansible-runner create secret generic ansible-runner-private "$@" --dry-run=client -o yaml | kubectl apply -f -
echo "config.yml sha256: $(shasum -a 256 "$CORE_ANSIBLE/config.yml" | cut -d' ' -f1)"
[ -n "${PRO_CONFIG:-}" ] && echo "pro_config.yml sha256: $(shasum -a 256 "$PRO_CONFIG" | cut -d' ' -f1)"
