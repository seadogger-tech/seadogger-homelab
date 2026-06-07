FROM codercom/code-server:latest

# Add openssh-client so the Remote SSH extension can actually make SSH connections.
# The base image has it, but this documents the dependency explicitly.
# Extension installation happens at pod startup via the init container in the
# k8s deployment (installs to /opt/data PVC so it persists across pod restarts).
USER root
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends openssh-client && \
    rm -rf /var/lib/apt/lists/*

USER 1000
