#!/usr/bin/env python3
"""
sandbox_builder.py — Parses a task.toml, generates a Dockerfile, and optionally
builds + measures the resulting multi-repo sandbox image.

Usage:
    python3 sandbox_builder.py <task.toml> [--build] [--measure]

Flags:
    --build    Actually build the Docker image (requires Docker)
    --measure  Build the image, run it, and report disk/time metrics
"""

import argparse
import os
import subprocess
import sys
import textwrap
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from validation import validate_repo_entry

# Python 3.11+ has tomllib in stdlib; fall back to tomli for older versions
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        # Minimal TOML parser for the subset we need (no external deps)
        tomllib = None


def parse_toml_minimal(path: str) -> dict:
    """Bare-bones TOML parser for task.toml files.
    Handles the subset we actually use: strings, arrays-of-tables, basic tables.
    Falls back to this only if tomllib/tomli are unavailable."""
    import json
    import re

    with open(path) as f:
        content = f.read()

    # Use a crude but functional approach: convert TOML to JSON-ish structure
    result = {}
    current_table = result
    current_table_path = []
    array_table_re = re.compile(r'^\[\[(\S+)\]\]\s*$')
    table_re = re.compile(r'^\[(\S+)\]\s*$')
    kv_re = re.compile(r'^(\w+)\s*=\s*(.+)$')

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # Array of tables: [[repos]]
        m = array_table_re.match(line)
        if m:
            key = m.group(1)
            parts = key.split('.')
            target = result
            for p in parts[:-1]:
                target = target.setdefault(p, {})
            arr = target.setdefault(parts[-1], [])
            new_item = {}
            arr.append(new_item)
            current_table = new_item
            continue

        # Table: [task]
        m = table_re.match(line)
        if m:
            key = m.group(1)
            parts = key.split('.')
            target = result
            for p in parts:
                target = target.setdefault(p, {})
            current_table = target
            continue

        # Key-value
        m = kv_re.match(line)
        if m:
            key = m.group(1)
            val_str = m.group(2).strip()
            # Parse value
            if val_str.startswith('"') or val_str.startswith("'"):
                # String — handle triple-quoted later, for now simple strings
                val = val_str.strip('"').strip("'")
            elif val_str.startswith('['):
                # Array of strings
                val = [s.strip().strip('"').strip("'") for s in val_str.strip('[]').split(',') if s.strip()]
            elif val_str.startswith('"""') or val_str.startswith("'''"):
                val = val_str  # multi-line not fully supported in minimal parser
            elif val_str.replace('_', '').replace('.', '').replace('-', '').isdigit():
                val = int(val_str.replace('_', ''))
            elif val_str in ('true', 'false'):
                val = val_str == 'true'
            else:
                val = val_str.strip('"')
            current_table[key] = val

    return result


def load_task(path: str) -> dict:
    """Load and return a parsed task.toml."""
    if tomllib is not None:
        with open(path, 'rb') as f:
            return tomllib.load(f)
    else:
        return parse_toml_minimal(path)


def generate_dockerfile(task: dict, task_dir: str) -> str:
    """Generate a Dockerfile string that clones all repos at pinned revisions."""
    repos = task.get('repos', [])
    task_meta = task.get('task', {})
    task_id = task_meta.get('id', 'unknown')

    # Detect primary language for base image selection
    languages = task.get('metadata', {}).get('languages', [])
    if 'go' in languages:
        base_image = 'golang:1.21-bookworm'
    elif 'python' in languages:
        base_image = 'python:3.11-bookworm'
    elif 'java' in languages:
        base_image = 'eclipse-temurin:21-jdk-jammy'
    elif 'typescript' in languages or 'javascript' in languages:
        base_image = 'node:20-bookworm'
    else:
        base_image = 'ubuntu:22.04'

    lines = [
        f"# Auto-generated Dockerfile for EnterpriseBench task: {task_id}",
        f"# Repos: {', '.join(r['path'] for r in repos)}",
        f"FROM {base_image}",
        "",
        f'LABEL eb.task.id="{task_id}"',
        f'LABEL eb.repo.count="{len(repos)}"',
        "",
        "# Install essentials",
        "RUN apt-get update && apt-get install -y --no-install-recommends \\",
        "    git curl ca-certificates jq && \\",
        "    rm -rf /var/lib/apt/lists/*",
        "",
        "# Create workspace and marker directory",
        "RUN mkdir -p /workspace/.markers",
        "",
    ]

    health_markers = []
    for repo in repos:
        url = repo['url']
        # Ensure .git suffix for clone
        clone_url = url if url.endswith('.git') else f"{url}.git"
        rev = repo['rev']
        path = repo['path']

        lines.append(f"# Clone {path} at {rev}")
        lines.append(
            f"RUN git clone --depth 1 --branch {rev} {clone_url} /workspace/{path} && \\"
        )
        lines.append(
            f"    cd /workspace/{path} && \\"
        )
        lines.append(
            f"    git log --oneline -1 > /workspace/.markers/{path}.rev && \\"
        )
        lines.append(
            f'    echo "OK" > /workspace/.markers/{path}.status'
        )
        lines.append("")
        health_markers.append(path)

    marker_list = ' '.join(health_markers)

    lines.extend([
        "# Health-check: verify all repos cloned",
        "COPY health_check.sh /workspace/health_check.sh",
        "RUN chmod +x /workspace/health_check.sh",
        "",
        "# Cross-repo test runner",
        "COPY test_runner.sh /workspace/test.sh",
        "RUN chmod +x /workspace/test.sh",
        "",
        "WORKDIR /workspace",
        "",
        f"# Final health check during build — fail the build if any repo missing",
        f"RUN /workspace/health_check.sh {marker_list}",
        "",
    ])

    return "\n".join(lines)


def generate_health_check() -> str:
    """Generate health_check.sh content."""
    return textwrap.dedent("""\
        #!/usr/bin/env bash
        # health_check.sh — Validates all repos cloned correctly.
        # Usage: health_check.sh <repo1> <repo2> ...
        # Reads marker files from /workspace/.markers/
        set -euo pipefail

        MARKER_DIR="/workspace/.markers"
        FAILED=0

        if [ $# -eq 0 ]; then
            # Auto-detect from marker directory
            for status_file in "$MARKER_DIR"/*.status; do
                [ -f "$status_file" ] || continue
                repo=$(basename "$status_file" .status)
                set -- "$@" "$repo"
            done
        fi

        for repo in "$@"; do
            status_file="$MARKER_DIR/${repo}.status"
            rev_file="$MARKER_DIR/${repo}.rev"

            if [ ! -f "$status_file" ]; then
                echo "FAIL: $repo — no status marker found"
                FAILED=1
                continue
            fi

            status=$(cat "$status_file")
            if [ "$status" != "OK" ]; then
                echo "FAIL: $repo — status is '$status', expected 'OK'"
                FAILED=1
                continue
            fi

            if [ ! -f "$rev_file" ]; then
                echo "WARN: $repo — no revision marker"
            else
                echo "OK: $repo — $(cat "$rev_file")"
            fi

            # Verify the repo directory actually has files
            if [ ! -d "/workspace/$repo/.git" ]; then
                echo "FAIL: $repo — directory exists but no .git"
                FAILED=1
                continue
            fi
        done

        if [ "$FAILED" -ne 0 ]; then
            echo ""
            echo "SANDBOX HEALTH CHECK FAILED — aborting"
            exit 1
        fi

        echo ""
        echo "All repos healthy."
    """)


def generate_test_runner() -> str:
    """Read test_runner.sh from the canonical source file."""
    runner_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_runner.sh')
    with open(runner_path) as f:
        return f.read()


def build_image(dockerfile_content: str, context_dir: str, tag: str) -> tuple[bool, float]:
    """Build the Docker image. Returns (success, build_time_seconds)."""
    dockerfile_path = os.path.join(context_dir, 'Dockerfile')
    with open(dockerfile_path, 'w') as f:
        f.write(dockerfile_content)

    # Write supporting scripts to context
    with open(os.path.join(context_dir, 'health_check.sh'), 'w') as f:
        f.write(generate_health_check())
    with open(os.path.join(context_dir, 'test_runner.sh'), 'w') as f:
        f.write(generate_test_runner())

    start = time.time()
    result = subprocess.run(
        ['docker', 'build', '-t', tag, '.'],
        cwd=context_dir,
        capture_output=True,
        text=True,
        timeout=600,  # 10 min timeout
    )
    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"Build FAILED ({elapsed:.1f}s):")
        print(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
        return False, elapsed

    print(f"Build succeeded in {elapsed:.1f}s")
    return True, elapsed


def measure_image(tag: str) -> dict:
    """Measure disk footprint of a built image."""
    metrics = {}

    # Image size
    result = subprocess.run(
        ['docker', 'image', 'inspect', tag, '--format', '{{.Size}}'],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        size_bytes = int(result.stdout.strip())
        metrics['image_size_mb'] = round(size_bytes / (1024 * 1024), 1)

    # Per-repo disk usage inside the container
    result = subprocess.run(
        ['docker', 'run', '--rm', tag, 'du', '-sh', '/workspace/*/'],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        metrics['repo_sizes'] = {}
        for line in result.stdout.strip().splitlines():
            parts = line.split('\t')
            if len(parts) == 2:
                size, path = parts
                repo_name = path.rstrip('/').split('/')[-1]
                if repo_name and repo_name != '*':
                    metrics['repo_sizes'][repo_name] = size

    # Total /workspace size
    result = subprocess.run(
        ['docker', 'run', '--rm', tag, 'du', '-sh', '/workspace/'],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        metrics['workspace_total'] = result.stdout.strip().split('\t')[0]

    return metrics


def main():
    parser = argparse.ArgumentParser(description='EnterpriseBench sandbox builder')
    parser.add_argument('task_toml', help='Path to task.toml file')
    parser.add_argument('--build', action='store_true', help='Build the Docker image')
    parser.add_argument('--measure', action='store_true', help='Build and measure disk/time')
    parser.add_argument('--output-dir', default=None, help='Output directory for generated files')
    args = parser.parse_args()

    # Load task
    task = load_task(args.task_toml)
    task_meta = task.get('task', {})
    task_id = task_meta.get('id', 'unknown')
    repos = task.get('repos', [])

    # Normalize URLs before validation (TOML may omit https:// prefix)
    for r in repos:
        if not r.get('url', '').startswith('http'):
            r['url'] = f"https://{r['url']}"
        validate_repo_entry(r)

    print(f"Task: {task_id}")
    print(f"Repos: {len(repos)}")
    for r in repos:
        print(f"  - {r['path']} ({r['url']}@{r['rev']})")
    print()

    # Determine output directory
    task_dir = args.output_dir or os.path.dirname(os.path.abspath(args.task_toml))
    os.makedirs(task_dir, exist_ok=True)

    # Generate Dockerfile
    dockerfile = generate_dockerfile(task, task_dir)
    dockerfile_path = os.path.join(task_dir, 'Dockerfile')
    with open(dockerfile_path, 'w') as f:
        f.write(dockerfile)
    print(f"Wrote: {dockerfile_path}")

    # Write helper scripts
    hc_path = os.path.join(task_dir, 'health_check.sh')
    with open(hc_path, 'w') as f:
        f.write(generate_health_check())
    os.chmod(hc_path, 0o755)
    print(f"Wrote: {hc_path}")

    tr_path = os.path.join(task_dir, 'test_runner.sh')
    with open(tr_path, 'w') as f:
        f.write(generate_test_runner())
    os.chmod(tr_path, 0o755)
    print(f"Wrote: {tr_path}")

    # Build if requested
    if args.build or args.measure:
        tag = f"eb-sandbox-{task_id}"
        success, build_time = build_image(dockerfile, task_dir, tag)

        if success and args.measure:
            print("\n=== Measurements ===")
            metrics = measure_image(tag)
            metrics['build_time_seconds'] = round(build_time, 1)
            metrics['task_id'] = task_id
            metrics['repo_count'] = len(repos)

            print(f"Image size:      {metrics.get('image_size_mb', '?')} MB")
            print(f"Workspace total: {metrics.get('workspace_total', '?')}")
            print(f"Build time:      {build_time:.1f}s")
            if 'repo_sizes' in metrics:
                print("Per-repo sizes:")
                for name, size in metrics['repo_sizes'].items():
                    print(f"  {name}: {size}")

            # Write metrics to JSON
            import json
            metrics_path = os.path.join(task_dir, 'sandbox_metrics.json')
            with open(metrics_path, 'w') as f:
                json.dump(metrics, f, indent=2)
            print(f"\nMetrics written to: {metrics_path}")

        if not success:
            sys.exit(1)
    else:
        print("\nDockerfile generated. Use --build to build, --measure to build + measure.")


if __name__ == '__main__':
    main()
