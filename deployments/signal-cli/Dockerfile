# signal-cli daemon image - AsamK upstream binary, wrapped for k8s.
#
# Same thing as `brew install signal-cli && signal-cli --account +1xxx
# daemon --http 127.0.0.1:8080` on macOS, but in a container.
#
# Multi-arch: eclipse-temurin handles amd64+arm64 via TARGETARCH; the
# signal-cli JVM tarball is architecture-independent.
#
# Bump VERSION when you want a newer signal-cli release. Track:
# https://github.com/AsamK/signal-cli/releases
FROM eclipse-temurin:25-jre

ARG VERSION=0.14.4.1
ARG SHA256_TARBALL=

ENV SIGNAL_CLI_VERSION=${VERSION}
# NOTE: do NOT set SIGNAL_CLI_CONFIG. The Gradle-generated wrapper script
# in signal-cli interprets that env var as "--config <value>", and signal-cli
# treats --config's argument as a config FILE path (not a directory) - so
# the daemon crashes at startup with
#   "Failed to load config from /data: /data (Is a directory)"
# Pass the data directory via --data-dir in CMD instead.

# Install signal-cli from upstream release.
# Supply-chain note: if SHA256_TARBALL is provided at build time, the
# tarball is verified before extraction. Empty -> skip (default).
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    curl -fsSL -o /tmp/signal-cli.tar.gz \
      "https://github.com/AsamK/signal-cli/releases/download/v${VERSION}/signal-cli-${VERSION}.tar.gz" && \
    if [ -n "${SHA256_TARBALL}" ]; then \
        echo "${SHA256_TARBALL}  /tmp/signal-cli.tar.gz" | sha256sum -c -; \
    fi && \
    tar -xzf /tmp/signal-cli.tar.gz -C /opt && \
    ln -sf "/opt/signal-cli-${VERSION}/bin/signal-cli" /usr/local/bin/signal-cli && \
    rm -f /tmp/signal-cli.tar.gz && \
    apt-get purge -y curl && apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Data directory: signal-cli stores account state, session keys, attachments
# here. Mounted as a PVC in k8s so it survives pod restarts.
RUN mkdir -p /data && chmod 700 /data
VOLUME ["/data"]

EXPOSE 8080

# Default: HTTP JSON-RPC daemon, bound to 0.0.0.0 so the k8s Service can
# reach it. Multi-account mode (no --account flag) so a single pod can
# serve every hermes-<user> agent. Each agent passes its own SIGNAL_ACCOUNT
# in the JSON-RPC request body.
#
# Override at the Deployment level by setting `args:` if needed (e.g. for
# single-account mode: `args: ["--data-dir","/data","--account","+1XXX","daemon","--http","0.0.0.0:8080"]`).
ENTRYPOINT ["signal-cli"]
CMD ["--data-dir", "/data", "daemon", "--http", "0.0.0.0:8080"]
