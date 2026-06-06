# signal-cli daemon image - AsamK upstream binary, wrapped for k8s.
#
# Same thing as `brew install signal-cli && signal-cli --account +1xxx
# daemon --http 127.0.0.1:8080` on macOS, but in a container.
#
# Multi-arch: eclipse-temurin handles amd64+arm64 via TARGETARCH; the
# signal-cli JVM tarball is architecture-independent EXCEPT for the
# libsignal_jni native lib, which ships only x86_64 in upstream. For
# arm64 we patch in the matching pre-built lib from exquo/signal-libs-build
# (the canonical community ARM64 builds the AsamK wiki points at).
#
# Bump VERSION when you want a newer signal-cli release. Track:
#   https://github.com/AsamK/signal-cli/releases
# When you bump VERSION, also update LIBSIGNAL_VERSION to match the
# libsignal-client jar shipped with that signal-cli release. Look in
# the unpacked tarball: lib/libsignal-client-X.Y.Z.jar
FROM eclipse-temurin:25-jre

ARG VERSION=0.14.4.1
# Must match the libsignal-client-X.Y.Z.jar version that ships with the
# above signal-cli release. Check exquo releases for available builds:
#   https://github.com/exquo/signal-libs-build/releases
ARG LIBSIGNAL_VERSION=0.94.1
ARG SHA256_TARBALL=

ENV SIGNAL_CLI_VERSION=${VERSION}
# NOTE: do NOT set SIGNAL_CLI_CONFIG. The Gradle-generated wrapper script
# in signal-cli interprets that env var as "--config <value>", and signal-cli
# treats --config's argument as a config FILE path (not a directory) - so
# the daemon crashes at startup with
#   "Failed to load config from /data: /data (Is a directory)"
# Pass the data directory via --data-dir in CMD instead.

# Install signal-cli + patch in arm64-native libsignal_jni.
# Supply-chain note: if SHA256_TARBALL is provided at build time, the
# tarball is verified before extraction. Empty -> skip (default).
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates zip && \
    # 1. signal-cli main tarball
    curl -fsSL -o /tmp/signal-cli.tar.gz \
      "https://github.com/AsamK/signal-cli/releases/download/v${VERSION}/signal-cli-${VERSION}.tar.gz" && \
    if [ -n "${SHA256_TARBALL}" ]; then \
        echo "${SHA256_TARBALL}  /tmp/signal-cli.tar.gz" | sha256sum -c -; \
    fi && \
    tar -xzf /tmp/signal-cli.tar.gz -C /opt && \
    ln -sf "/opt/signal-cli-${VERSION}/bin/signal-cli" /usr/local/bin/signal-cli && \
    rm -f /tmp/signal-cli.tar.gz && \
    # 2. Patch libsignal_jni.so for current arch. Upstream ships x86_64 only.
    arch="$(uname -m)" && \
    case "$arch" in \
        x86_64)  exquo_arch="x86_64-unknown-linux-gnu" ;; \
        aarch64) exquo_arch="aarch64-unknown-linux-gnu" ;; \
        *) echo "Unsupported arch: $arch" >&2; exit 1 ;; \
    esac && \
    curl -fsSL -o /tmp/libsignal_jni.tar.gz \
        "https://github.com/exquo/signal-libs-build/releases/download/libsignal_v${LIBSIGNAL_VERSION}/libsignal_jni.so-v${LIBSIGNAL_VERSION}-${exquo_arch}.tar.gz" && \
    tar -xzf /tmp/libsignal_jni.tar.gz -C /tmp && \
    # Replace the .so inside the libsignal-client jar that signal-cli loads at runtime
    JAR="/opt/signal-cli-${VERSION}/lib/libsignal-client-${LIBSIGNAL_VERSION}.jar" && \
    test -f "$JAR" || { echo "libsignal-client jar not found at $JAR"; exit 1; } && \
    cd /tmp && zip -j "$JAR" libsignal_jni.so && cd / && \
    rm -f /tmp/libsignal_jni.tar.gz /tmp/libsignal_jni.so && \
    apt-get purge -y curl zip && apt-get autoremove -y && \
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
