# Prebuilt runner image so every run uses the same Ansible. Nothing is installed at run time.
# Published as ghcr.io/seadogger-tech/ansible-runner by .github/workflows/build-ansible-runner.yaml
# (tags ansible-core-2.21.4 and sha-<commit>; the Job uses the reported digest, never a tag).
# Pinned to the owner's controller: ansible-core 2.21.4 on Python 3.14.
# Base image is pinned by digest (python:3.14-slim-bookworm, multi-arch index, resolved 2026-11-18).
FROM python:3.14-slim-bookworm@sha256:3fe1a0b6c2d6b2ebb572906cdabeca75aeb558c0c17db5ffefbcf8094871c32b
ARG ANSIBLE_CORE_VERSION=2.21.4
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends openssh-client git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt collections.yml /tmp/
RUN pip install --no-cache-dir "ansible-core==${ANSIBLE_CORE_VERSION}" -r /tmp/requirements.txt
# Collections go in the system path so they resolve for any user/HOME the Job runs as.
# Core also vendors an old community.kubernetes under ansible/ansible_collections; it is a
# different collection name, so it does not shadow kubernetes.core 6.5.0 installed here.
RUN ansible-galaxy collection install -p /usr/share/ansible/collections -r /tmp/collections.yml \
 && ansible-galaxy collection list -p /usr/share/ansible/collections
