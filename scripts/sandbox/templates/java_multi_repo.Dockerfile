# EnterpriseBench Java multi-repo sandbox template
# Repos: protobuf-java (v25.1) + grpc-java (v1.60.0)
# Dependency chain: grpc-java -> protobuf-java
FROM eclipse-temurin:21-jdk-jammy

LABEL eb.template="java_multi_repo"
LABEL eb.repo.count="2"

# Install essentials
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates jq && \
    rm -rf /var/lib/apt/lists/*

# Create workspace and marker directory
RUN mkdir -p /workspace/.markers

# Clone protobuf at v25.1 (~30MB shallow)
RUN git clone --depth 1 --branch v25.1 https://github.com/protocolbuffers/protobuf.git /workspace/protobuf && \
    cd /workspace/protobuf && \
    git log --oneline -1 > /workspace/.markers/protobuf.rev && \
    echo "OK" > /workspace/.markers/protobuf.status

# Clone grpc-java at v1.60.0 (~25MB shallow)
RUN git clone --depth 1 --branch v1.60.0 https://github.com/grpc/grpc-java.git /workspace/grpc-java && \
    cd /workspace/grpc-java && \
    git log --oneline -1 > /workspace/.markers/grpc-java.rev && \
    echo "OK" > /workspace/.markers/grpc-java.status

# Health-check: verify all repos cloned
COPY health_check.sh /workspace/health_check.sh
RUN chmod +x /workspace/health_check.sh

# Cross-repo test runner
COPY test_runner.sh /workspace/test.sh
RUN chmod +x /workspace/test.sh

WORKDIR /workspace

# Final health check during build
RUN /workspace/health_check.sh protobuf grpc-java
