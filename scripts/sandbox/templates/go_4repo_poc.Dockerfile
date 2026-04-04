# EnterpriseBench 4-repo PoC sandbox
# Repos: moby/moby (v25.0.0) + containerd (v1.7.11) + runc (v1.1.11) + kubernetes (v1.29.0)
# Dependency chain: kubernetes -> containerd -> runc; moby -> containerd -> runc
# Purpose: Kill-or-proceed gate for 4-repo tier (must fit 8GB RAM, build < 3000s)
FROM golang:1.21-bookworm

LABEL eb.template="go_4repo_poc"
LABEL eb.repo.count="4"
LABEL eb.poc="true"

# Install essentials
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates jq && \
    rm -rf /var/lib/apt/lists/*

# Create workspace and marker directory
RUN mkdir -p /workspace/.markers

# Clone runc at v1.1.11 (~5MB shallow)
RUN git clone --depth 1 --branch v1.1.11 https://github.com/opencontainers/runc.git /workspace/runc && \
    cd /workspace/runc && \
    git log --oneline -1 > /workspace/.markers/runc.rev && \
    echo "OK" > /workspace/.markers/runc.status

# Clone containerd at v1.7.11 (~25MB shallow)
RUN git clone --depth 1 --branch v1.7.11 https://github.com/containerd/containerd.git /workspace/containerd && \
    cd /workspace/containerd && \
    git log --oneline -1 > /workspace/.markers/containerd.rev && \
    echo "OK" > /workspace/.markers/containerd.status

# Clone moby at v25.0.0 (~65MB shallow)
RUN git clone --depth 1 --branch v25.0.0 https://github.com/moby/moby.git /workspace/moby && \
    cd /workspace/moby && \
    git log --oneline -1 > /workspace/.markers/moby.rev && \
    echo "OK" > /workspace/.markers/moby.status

# Clone kubernetes at v1.29.0 (~180MB shallow)
RUN git clone --depth 1 --branch v1.29.0 https://github.com/kubernetes/kubernetes.git /workspace/kubernetes && \
    cd /workspace/kubernetes && \
    git log --oneline -1 > /workspace/.markers/kubernetes.rev && \
    echo "OK" > /workspace/.markers/kubernetes.status

# Health-check: verify all repos cloned
COPY health_check.sh /workspace/health_check.sh
RUN chmod +x /workspace/health_check.sh

# Cross-repo test runner
COPY test_runner.sh /workspace/test.sh
RUN chmod +x /workspace/test.sh

WORKDIR /workspace

# Final health check during build
RUN /workspace/health_check.sh runc containerd moby kubernetes
