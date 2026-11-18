# Prebuilt runner image so every run uses the same Ansible. Nothing is installed at run time.
# Published as ghcr.io/seadogger-tech/ansible-runner by .github/workflows/ansible-runner-image.yml.
# Pinned to the owner's controller: ansible-core 2.21.4 on Python 3.14.
# Manual build (ARM64):
#   docker buildx build --platform linux/arm64 -t ghcr.io/seadogger-tech/ansible-runner:2.21.4 --push .
# Then put the resulting image digest (ghcr.io/seadogger-tech/ansible-runner@sha256:...) in the Job. Never use a tag.
FROM python:3.14-slim-bookworm
ARG ANSIBLE_CORE_VERSION=2.21.4
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends openssh-client git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir "ansible-core==${ANSIBLE_CORE_VERSION}" -r /tmp/requirements.txt
