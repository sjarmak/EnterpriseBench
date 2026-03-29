# EnterpriseBench Go multi-repo sandbox template
# Repos: grpc-go (v1.60.0) + etcd (v3.5.10)
# Based on validated P0.2 sandbox (see docs/sandbox_measurements.md)
FROM golang:1.21-bookworm

LABEL eb.template="go_multi_repo"
LABEL eb.repo.count="2"

# Install essentials
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates jq && \
    rm -rf /var/lib/apt/lists/*

# Create workspace and marker directory
RUN mkdir -p /workspace/.markers

# Clone grpc-go at v1.60.0 (~6MB shallow)
RUN git clone --depth 1 --branch v1.60.0 https://github.com/grpc/grpc-go.git /workspace/grpc-go && \
    cd /workspace/grpc-go && \
    git log --oneline -1 > /workspace/.markers/grpc-go.rev && \
    echo "OK" > /workspace/.markers/grpc-go.status

# Clone etcd at v3.5.10 (~43MB shallow)
RUN git clone --depth 1 --branch v3.5.10 https://github.com/etcd-io/etcd.git /workspace/etcd && \
    cd /workspace/etcd && \
    git log --oneline -1 > /workspace/.markers/etcd.rev && \
    echo "OK" > /workspace/.markers/etcd.status

# Health-check: verify all repos cloned
COPY health_check.sh /workspace/health_check.sh
RUN chmod +x /workspace/health_check.sh

# Cross-repo test runner
COPY test_runner.sh /workspace/test.sh
RUN chmod +x /workspace/test.sh

WORKDIR /workspace

# Final health check during build
RUN /workspace/health_check.sh grpc-go etcd
