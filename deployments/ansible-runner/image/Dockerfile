# Prebuilt runner image so every run uses the same Ansible. Nothing is installed at run time.
# Build (ARM64) with the Ansible version the owner's controller uses, e.g.:
#   docker buildx build --platform linux/arm64 \
#     --build-arg ANSIBLE_CORE_VERSION=<output of `ansible --version` on the Mac> -t <registry>/ansible-runner:<ver> --push .
# Then put the resulting image digest (repo@sha256:...) in the Job. Never use a tag.
FROM python:3.12-slim-bookworm
ARG ANSIBLE_CORE_VERSION
RUN test -n "$ANSIBLE_CORE_VERSION" || (echo 'ANSIBLE_CORE_VERSION is required' >&2; exit 1)
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends openssh-client git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir "ansible-core==${ANSIBLE_CORE_VERSION}" -r /tmp/requirements.txt
