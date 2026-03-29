# EnterpriseBench Python multi-repo sandbox template
# Repos: urllib3 (2.1.0) + requests (v2.31.0) + boto3 (1.34.0)
# Dependency chain: boto3 -> requests -> urllib3
FROM python:3.11-bookworm

LABEL eb.template="python_multi_repo"
LABEL eb.repo.count="3"

# Install essentials
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates jq && \
    rm -rf /var/lib/apt/lists/*

# Create workspace and marker directory
RUN mkdir -p /workspace/.markers

# Clone urllib3 at 2.1.0 (~8MB shallow)
RUN git clone --depth 1 --branch 2.1.0 https://github.com/urllib3/urllib3.git /workspace/urllib3 && \
    cd /workspace/urllib3 && \
    git log --oneline -1 > /workspace/.markers/urllib3.rev && \
    echo "OK" > /workspace/.markers/urllib3.status

# Clone requests at v2.31.0 (~4MB shallow)
RUN git clone --depth 1 --branch v2.31.0 https://github.com/psf/requests.git /workspace/requests && \
    cd /workspace/requests && \
    git log --oneline -1 > /workspace/.markers/requests.rev && \
    echo "OK" > /workspace/.markers/requests.status

# Clone boto3 at 1.34.0 (~30MB shallow)
RUN git clone --depth 1 --branch 1.34.0 https://github.com/boto/boto3.git /workspace/boto3 && \
    cd /workspace/boto3 && \
    git log --oneline -1 > /workspace/.markers/boto3.rev && \
    echo "OK" > /workspace/.markers/boto3.status

# Health-check: verify all repos cloned
COPY health_check.sh /workspace/health_check.sh
RUN chmod +x /workspace/health_check.sh

# Cross-repo test runner
COPY test_runner.sh /workspace/test.sh
RUN chmod +x /workspace/test.sh

WORKDIR /workspace

# Final health check during build
RUN /workspace/health_check.sh urllib3 requests boto3
