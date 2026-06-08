FROM docker.io/nousresearch/hermes-agent:latest

# All tool versions pinned — bump deliberately when upgrading
ARG KUBECTL_VERSION=v1.33.4
ARG YQ_VERSION=v4.53.3
ARG HELM_VERSION=v4.2.0
ARG STERN_VERSION=v1.34.0
ARG KUSTOMIZE_VERSION=v5.8.1
ARG GH_VERSION=2.93.0
ARG TRIVY_VERSION=0.71.0
ARG GRYPE_VERSION=0.114.0
ARG SYFT_VERSION=1.45.1
ARG SWIFTLINT_VERSION=0.63.3
ARG SWIFTFORMAT_VERSION=0.61.1
ARG SWIFT_VERSION=swift-6.3.2-RELEASE

USER root

# ── System packages ───────────────────────────────────────────────────────────
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    # Network / DNS
    dnsutils netcat-openbsd iputils-ping traceroute \
    # JSON / YAML
    jq \
    # Shell / filesystem (ripgrep already in upstream base)
    tree fd-find bat tmux \
    # Python dev (python3 + uv already in upstream base; ipython installed via pip below)
    python3-pip python3-venv \
    # JavaScript (yarn installed via npm below — not in Debian Trixie apt repos)

    # Java
    openjdk-21-jdk gradle maven \
    # C / C++
    gcc g++ clang cmake make gdb \
    # Swift toolchain deps
    binutils gnupg2 libc6-dev libcurl4-openssl-dev \
    libedit2 libgcc-13-dev libpython3-dev libsqlite3-0 \
    libstdc++-13-dev libxml2-dev libz3-dev pkg-config \
    tzdata unzip zlib1g-dev \
    # Ruby — needed for fastlane (not in upstream base image)
    ruby ruby-dev \
    # SSH server — VS Code Remote SSH from the dev (code-server) pod connects
    # here so the integrated terminal runs inside the full dev environment.
    # No passwords — auth is exclusively via keypair written to the PVC.
    openssh-server \
    # General
    curl wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── kubectl ───────────────────────────────────────────────────────────────────
RUN curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/arm64/kubectl" \
    -o /usr/local/bin/kubectl && chmod 755 /usr/local/bin/kubectl

# ── gh CLI ────────────────────────────────────────────────────────────────────
RUN curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_arm64.tar.gz" \
    | tar -xz -C /tmp && \
    cp /tmp/gh_${GH_VERSION}_linux_arm64/bin/gh /usr/local/bin/gh && \
    chmod 755 /usr/local/bin/gh && rm -rf /tmp/gh_*

# ── yq ────────────────────────────────────────────────────────────────────────
RUN curl -fsSL "https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/yq_linux_arm64" \
    -o /usr/local/bin/yq && chmod 755 /usr/local/bin/yq

# ── helm ──────────────────────────────────────────────────────────────────────
RUN curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-arm64.tar.gz" \
    | tar -xz -C /tmp && \
    cp /tmp/linux-arm64/helm /usr/local/bin/helm && \
    chmod 755 /usr/local/bin/helm && rm -rf /tmp/linux-arm64

# ── stern ─────────────────────────────────────────────────────────────────────
RUN curl -fsSL "https://github.com/stern/stern/releases/download/${STERN_VERSION}/stern_${STERN_VERSION#v}_linux_arm64.tar.gz" \
    | tar -xz -C /tmp && \
    cp /tmp/stern /usr/local/bin/stern && chmod 755 /usr/local/bin/stern && rm -f /tmp/stern

# ── kustomize ─────────────────────────────────────────────────────────────────
RUN curl -fsSL "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2F${KUSTOMIZE_VERSION}/kustomize_${KUSTOMIZE_VERSION}_linux_arm64.tar.gz" \
    | tar -xz -C /usr/local/bin && chmod 755 /usr/local/bin/kustomize

# ── trivy ─────────────────────────────────────────────────────────────────────
RUN curl -fsSL "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-ARM64.tar.gz" \
    | tar -xz -C /tmp && \
    cp /tmp/trivy /usr/local/bin/trivy && chmod 755 /usr/local/bin/trivy && rm -f /tmp/trivy

# ── grype ─────────────────────────────────────────────────────────────────────
RUN curl -fsSL "https://github.com/anchore/grype/releases/download/v${GRYPE_VERSION}/grype_${GRYPE_VERSION}_linux_arm64.tar.gz" \
    | tar -xz -C /tmp && \
    cp /tmp/grype /usr/local/bin/grype && chmod 755 /usr/local/bin/grype && rm -f /tmp/grype

# ── syft ──────────────────────────────────────────────────────────────────────
RUN curl -fsSL "https://github.com/anchore/syft/releases/download/v${SYFT_VERSION}/syft_${SYFT_VERSION}_linux_arm64.tar.gz" \
    | tar -xz -C /tmp && \
    cp /tmp/syft /usr/local/bin/syft && chmod 755 /usr/local/bin/syft && rm -f /tmp/syft

# ── Swift toolchain ───────────────────────────────────────────────────────────
RUN curl -fsSL "https://download.swift.org/swift-6.3.2-release/debian12-aarch64/${SWIFT_VERSION}/${SWIFT_VERSION}-debian12-aarch64.tar.gz" \
    | tar -xz -C /opt && \
    ln -s /opt/${SWIFT_VERSION}-debian12-aarch64/usr/bin/swift /usr/local/bin/swift && \
    ln -s /opt/${SWIFT_VERSION}-debian12-aarch64/usr/bin/swiftc /usr/local/bin/swiftc

# ── SwiftLint ─────────────────────────────────────────────────────────────────
RUN curl -fsSL "https://github.com/realm/SwiftLint/releases/download/${SWIFTLINT_VERSION}/swiftlint_linux_arm64.zip" \
    -o /tmp/swiftlint.zip && \
    unzip -q /tmp/swiftlint.zip -d /tmp/swiftlint && \
    cp /tmp/swiftlint/swiftlint /usr/local/bin/swiftlint && \
    chmod 755 /usr/local/bin/swiftlint && rm -rf /tmp/swiftlint /tmp/swiftlint.zip

# ── SwiftFormat ───────────────────────────────────────────────────────────────
RUN curl -fsSL "https://github.com/nicklockwood/SwiftFormat/releases/download/${SWIFTFORMAT_VERSION}/swiftformat_linux_aarch64.zip" \
    -o /tmp/swiftformat.zip && \
    unzip -q /tmp/swiftformat.zip -d /tmp/swiftformat && \
    cp /tmp/swiftformat/swiftformat_linux_aarch64 /usr/local/bin/swiftformat && \
    chmod 755 /usr/local/bin/swiftformat && rm -rf /tmp/swiftformat /tmp/swiftformat.zip

# ── fd / bat symlinks (Debian renames these binaries) ────────────────────────
RUN ln -sf /usr/bin/fdfind /usr/local/bin/fd && \
    ln -sf /usr/bin/batcat /usr/local/bin/bat

# ── pnpm + yarn + TypeScript + ESLint + Prettier ─────────────────────────────
RUN npm install -g pnpm yarn typescript eslint prettier

# ── Python dev packages ───────────────────────────────────────────────────────
# uv/uvx already in upstream hermes-agent base image
RUN pip3 install --break-system-packages django fastapi uvicorn pytest black ruff ipython

# ── fastlane ─────────────────────────────────────────────────────────────────
RUN gem install fastlane --no-document

# ── sshd config ──────────────────────────────────────────────────────────────
# Generate static host keys at build time — pod restarts don't rotate them,
# so VS Code Remote SSH doesn't prompt "host key changed" on every restart.
# Host keys authenticate the server transport layer only; they are not secrets.
# User auth is exclusively via keypair written to the PVC by ansible.
RUN ssh-keygen -A && \
    mkdir -p /var/run/sshd && \
    sed -i 's|#PasswordAuthentication yes|PasswordAuthentication no|' /etc/ssh/sshd_config && \
    sed -i 's|#PermitRootLogin prohibit-password|PermitRootLogin no|'  /etc/ssh/sshd_config && \
    echo "PubkeyAuthentication yes"                                    >> /etc/ssh/sshd_config && \
    echo "AuthorizedKeysFile /opt/data/home/.ssh/authorized_keys"     >> /etc/ssh/sshd_config && \
    echo "UsePAM no"                                                   >> /etc/ssh/sshd_config && \
    echo "X11Forwarding no"                                            >> /etc/ssh/sshd_config && \
    echo "PrintMotd no"                                                >> /etc/ssh/sshd_config && \
    echo "AcceptEnv LANG LC_*"                                         >> /etc/ssh/sshd_config && \
    echo "StrictModes no"                                              >> /etc/ssh/sshd_config && \
    echo "SetEnv PATH=/opt/hermes/bin:/opt/hermes/.venv/bin:/usr/local/bin:/usr/bin:/bin HOME=/opt/data" >> /etc/ssh/sshd_config && \
    usermod -s /bin/bash hermes

# ── s6-overlay sshd service ───────────────────────────────────────────────────
# The upstream image uses s6-overlay as PID 1 (/init). We register sshd as a
# longrun service in the s6-rc dependency tree so it starts alongside the
# hermes gateway — no entrypoint override needed.
COPY --chmod=0755 s6-sshd/run /etc/s6-overlay/s6-rc.d/sshd/run
COPY s6-sshd/type /etc/s6-overlay/s6-rc.d/sshd/type
COPY s6-sshd/dependencies.d/base /etc/s6-overlay/s6-rc.d/sshd/dependencies.d/base
COPY s6-sshd/bundle-sshd /etc/s6-overlay/s6-rc.d/user/contents.d/sshd

# Upstream image drops to hermes user via s6-setuidgid in its run scripts;
# sshd must start as root (needs to bind :22 and manage PAM/keys), which is
# handled by the s6 service run script (not setuidgid).
# No USER instruction needed — upstream ENTRYPOINT handles privilege drop.
