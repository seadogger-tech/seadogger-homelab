FROM codercom/code-server:latest

# Pre-install the VS Code Remote SSH extension so it's available on first launch.
# The extension is what lets the integrated terminal run inside the hermes pod
# (full dev tooling) rather than the code-server container (minimal base image).
# Extensions are installed to /opt/data/home/.local/share/code-server/extensions
# at runtime (on the PVC) — this bakes it into the image so there's no
# download on first launch.
RUN code-server --install-extension ms-vscode-remote.remote-ssh --force

# SSH client config is written into the image as a default; the user can
# override by editing /opt/data/home/.ssh/config (which takes precedence
# because that path is on the PVC and code-server sets HOME=/opt/data/home).
# The hermes service is reachable at hermes.<namespace>.svc.cluster.local:22
# from within the same namespace. The namespace placeholder is patched at
# runtime by the init container in the dev pod deployment.
COPY ssh_config /etc/ssh/ssh_config.d/hermes.conf

USER 1000
