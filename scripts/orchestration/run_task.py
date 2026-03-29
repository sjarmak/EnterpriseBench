#!/usr/bin/env python3
"""Single-session task runner for EnterpriseBench.

Builds a Docker sandbox from a task.toml, optionally runs an agent inside it,
then scores the result using checkpoint verifiers.

Usage:
    python3 scripts/orchestration/run_task.py benchmarks/.../task.toml --dry-run
    python3 scripts/orchestration/run_task.py benchmarks/.../task.toml --agent "claude -p"
    python3 scripts/orchestration/run_task.py benchmarks/.../task.toml --timeout 900
"""

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Reuse the TOML parser from create_sg_mirrors
sys.path.insert(0, str(REPO_ROOT / "scripts" / "infra"))
from create_sg_mirrors import parse_toml

sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))
from validation import validate_repo_entry

logger = logging.getLogger(__name__)

# Paths to sandbox scripts (relative to repo root)
DOCKERFILE_GENERATOR = REPO_ROOT / "scripts" / "sandbox" / "dockerfile_generator.py"
TEST_RUNNER_SH = REPO_ROOT / "scripts" / "sandbox" / "test_runner.sh"
HEALTH_CHECK_SH = REPO_ROOT / "scripts" / "sandbox" / "health_check.sh"
EB_VERIFY_LIB = REPO_ROOT / "lib" / "eb_verify"


@dataclass(frozen=True)
class TaskRunConfig:
    """Immutable configuration for a single task run."""

    task_toml: Path
    source: str = "mirror"
    agent_command: str = ""
    timeout: int = 1800
    output_dir: Path | None = None
    dry_run: bool = False
    no_build: bool = False
    keep_container: bool = False
    verbose: bool = False
    account: int | None = None


@dataclass
class TaskRunResult:
    """Result of running a single task."""

    task_id: str
    phase: str = ""
    success: bool = False
    error: str = ""
    image_tag: str = ""
    container_id: str = ""
    scores: dict = field(default_factory=dict)
    timing: dict = field(default_factory=dict)
    output_dir: str = ""


def _load_oauth_token(account: int) -> str:
    """Load and validate an OAuth access token for the given account number.

    Reads credentials from ~/.claude-homes/account{N}/.claude/.credentials.json,
    checks the token has not expired, and returns the access token string.

    Raises:
        FileNotFoundError: If the credentials file does not exist.
        ValueError: If the token is expired or the credentials are malformed.
    """
    real_home = Path(os.environ.get("HOME", str(Path.home())))
    creds_path = real_home / ".claude-homes" / f"account{account}" / ".claude" / ".credentials.json"

    if not creds_path.is_file():
        raise FileNotFoundError(
            f"Credentials file not found for account {account}: {creds_path}"
        )

    try:
        creds = json.loads(creds_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(
            f"Failed to read credentials for account {account}: {exc}"
        ) from exc

    oauth = creds.get("claudeAiOauth")
    if not oauth or not isinstance(oauth, dict):
        raise ValueError(
            f"Missing or invalid claudeAiOauth section in {creds_path}"
        )

    access_token = oauth.get("accessToken")
    if not access_token:
        raise ValueError(f"No accessToken found in {creds_path}")

    expires_at_ms = oauth.get("expiresAt", 0)
    now_ms = int(time.time() * 1000)
    if expires_at_ms <= now_ms:
        expired_at = datetime.fromtimestamp(expires_at_ms / 1000, tz=timezone.utc)
        raise ValueError(
            f"OAuth token for account {account} expired at {expired_at.isoformat()}. "
            f"Run: python3 scripts/infra/headless_login.py --account {account}"
        )

    remaining_min = (expires_at_ms - now_ms) // 60000
    logger.info("Account %d: token valid, %d minutes remaining", account, remaining_min)
    return access_token


DEFAULT_OAUTH_AGENT_COMMAND = (
    "claude --dangerously-skip-permissions --max-turns 30 --output-format json -p"
)


def _parse_task(toml_path: Path) -> dict:
    """Parse and validate a task.toml file."""
    if not toml_path.exists():
        raise FileNotFoundError(f"Task file not found: {toml_path}")

    data = parse_toml(toml_path)

    task_info = data.get("task", {})
    if not task_info.get("id"):
        raise ValueError(f"Task file missing [task].id: {toml_path}")

    session_type = task_info.get("session_type", "single")
    if session_type != "single":
        raise ValueError(
            f"run_task.py only handles single-session tasks, "
            f"got session_type={session_type!r}. Use chain_runner.py for chains."
        )

    for repo in data.get("repos", []):
        validate_repo_entry(repo)

    return data


def _generate_dockerfile(task_toml: Path, source: str) -> Path:
    """Generate Dockerfile using the existing dockerfile_generator and return its path."""
    # Import the generator function directly to avoid subprocess overhead
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "sandbox"))
    from dockerfile_generator import generate_for_task

    results = generate_for_task(task_toml, source=source)
    dockerfile_path = results.get("standard")
    if dockerfile_path is None or not dockerfile_path.exists():
        raise RuntimeError("Dockerfile generation failed: no standard Dockerfile produced")

    logger.info("Generated Dockerfile: %s", dockerfile_path)
    return dockerfile_path


def _docker_build(dockerfile_path: Path, image_tag: str) -> None:
    """Build a Docker image from the generated Dockerfile."""
    context_dir = str(dockerfile_path.parent)
    cmd = [
        "docker", "build",
        "-f", str(dockerfile_path),
        "-t", image_tag,
        context_dir,
    ]
    logger.info("Building Docker image: %s", image_tag)
    logger.debug("Command: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Docker build failed (exit {result.returncode}):\n{result.stderr[-2000:]}"
        )
    logger.info("Docker image built: %s", image_tag)


def _docker_create_container(
    image_tag: str,
    container_name: str,
) -> str:
    """Create (but do not start) a container, returning the container ID."""
    cmd = [
        "docker", "create",
        "--name", container_name,
        image_tag,
        "sleep", "infinity",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"docker create failed: {result.stderr.strip()}")

    container_id = result.stdout.strip()
    logger.info("Created container: %s (%s)", container_name, container_id[:12])
    return container_id


def _docker_start(container_id: str) -> None:
    """Start an existing container."""
    result = subprocess.run(
        ["docker", "start", container_id],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"docker start failed: {result.stderr.strip()}")


def _docker_exec(
    container_id: str,
    cmd: list[str],
    timeout: int = 120,
    workdir: str = "/workspace",
) -> subprocess.CompletedProcess:
    """Run a command inside the container."""
    full_cmd = ["docker", "exec", "-w", workdir, container_id] + cmd
    return subprocess.run(
        full_cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _docker_cp(src: str, dest: str) -> None:
    """Copy files into or out of a container."""
    result = subprocess.run(
        ["docker", "cp", src, dest],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"docker cp failed: {result.stderr.strip()}")


def _docker_stop_rm(container_id: str) -> None:
    """Stop and remove a container."""
    subprocess.run(
        ["docker", "stop", "-t", "5", container_id],
        capture_output=True, text=True, timeout=30,
    )
    subprocess.run(
        ["docker", "rm", "-f", container_id],
        capture_output=True, text=True, timeout=30,
    )


def _setup_container(
    container_id: str,
    task_dir: Path,
    task_data: dict,
) -> None:
    """Copy task files into the running container.

    - instruction.md -> /workspace/instruction.md
    - checks/*.sh -> /workspace/.verifiers/
    - test_runner.sh -> /workspace/test.sh
    - eb_verify library -> /workspace/.eb_verify/ (if needed by check scripts)
    """
    # Copy instruction.md with output format appendix
    instruction = task_dir / "instruction.md"
    if instruction.exists():
        import tempfile
        instruction_text = instruction.read_text()
        output_appendix = (
            "\n\n---\n\n## Output Requirements\n\n"
            "Write your findings as a JSON file to `/workspace/agent_output/answer.json`.\n"
            "Create the directory first: `mkdir -p /workspace/agent_output`\n\n"
            "Include all relevant fields for this task type. Example structure:\n"
            "```json\n"
            "{\n"
            '  "source_files": [{"path": "relative/path/to/file"}],\n'
            '  "error_chain": ["Step 1", "Step 2"],\n'
            '  "trigger_conditions": ["Condition 1"],\n'
            '  "code_paths": [{"path": "relative/path"}],\n'
            '  "ownership": "subsystem description",\n'
            '  "severity": {"level": "high", "rationale": "..."}\n'
            "}\n```\n"
            "Include only the fields relevant to this task. "
            "Your answer is evaluated against a closed-world oracle — completeness matters.\n"
        )
        combined = instruction_text + output_appendix
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(combined)
            tmp_path = f.name
        try:
            _docker_cp(tmp_path, f"{container_id}:/workspace/instruction.md")
        finally:
            os.unlink(tmp_path)
        logger.info("Copied instruction.md with output appendix into container")
    else:
        logger.warning("No instruction.md found in %s", task_dir)

    # Create .verifiers directory and copy check scripts
    _docker_exec(container_id, ["mkdir", "-p", "/workspace/.verifiers"])

    checks_dir = task_dir / "checks"
    if checks_dir.is_dir():
        for check_script in sorted(checks_dir.glob("*.sh")):
            # Strip the "check_" prefix and ".sh" suffix to get checkpoint name,
            # then rename to just <name>.sh for test_runner.sh compatibility
            name = check_script.stem
            if name.startswith("check_"):
                name = name[len("check_"):]
            dest = f"{container_id}:/workspace/.verifiers/{name}.sh"
            _docker_cp(str(check_script), dest)
            _docker_exec(container_id, ["chmod", "+x", f"/workspace/.verifiers/{name}.sh"])
        logger.info("Copied %d check scripts into .verifiers/", len(list(checks_dir.glob("*.sh"))))
    else:
        logger.warning("No checks/ directory found in %s", task_dir)

    # Copy test_runner.sh as /workspace/test.sh
    if TEST_RUNNER_SH.exists():
        _docker_cp(str(TEST_RUNNER_SH), f"{container_id}:/workspace/test.sh")
        _docker_exec(container_id, ["chmod", "+x", "/workspace/test.sh"])
        logger.info("Copied test_runner.sh as /workspace/test.sh")

    # Copy eb_verify library for check scripts that import it
    if EB_VERIFY_LIB.is_dir():
        _docker_cp(str(EB_VERIFY_LIB), f"{container_id}:/workspace/.eb_verify")
        logger.info("Copied eb_verify library into container")

    # Copy ground_truth.json into a task metadata directory for verifiers
    gt_file = task_dir / "ground_truth.json"
    _docker_exec(container_id, ["mkdir", "-p", "/workspace/.task"])
    if gt_file.exists():
        _docker_cp(str(gt_file), f"{container_id}:/workspace/.task/ground_truth.json")
        logger.info("Copied ground_truth.json into container")


def _install_claude_cli(container_id: str) -> bool:
    """Install Claude Code CLI and create non-root agent user. Returns True on success."""
    logger.info("Installing Claude Code CLI...")
    # Ensure Node.js is available (node:20 and python:3.11 images have it,
    # others may need it installed first)
    check_node = _docker_exec(container_id, ["which", "node"])
    if check_node.returncode != 0:
        logger.info("Node.js not found, installing via apt...")
        _docker_exec(container_id, [
            "bash", "-c",
            "apt-get update -qq && apt-get install -y -qq nodejs npm >/dev/null 2>&1"
        ])
    result = _docker_exec(container_id, [
        "bash", "-c",
        "npm install -g @anthropic-ai/claude-code@latest 2>&1 | tail -3"
    ])
    if result.returncode != 0:
        logger.error("Failed to install Claude Code CLI: %s", result.stderr)
        return False
    # Create non-root user for agent execution (Claude Code refuses
    # --dangerously-skip-permissions as root)
    _docker_exec(container_id, [
        "bash", "-c",
        "useradd -m -s /bin/bash agent 2>/dev/null; "
        "chown -R agent:agent /workspace"
    ])
    # Verify
    ver = _docker_exec(container_id, ["claude", "--version"])
    if ver.returncode == 0:
        logger.info("Claude Code CLI installed: %s", ver.stdout.strip())
        return True
    logger.error("Claude Code CLI not found after install")
    return False


def _run_health_check(container_id: str, repos: list[dict]) -> bool:
    """Run health_check.sh inside the container. Returns True if healthy."""
    repo_paths = [r["path"] for r in repos if r.get("path")]

    # Check that repo directories exist and have .git
    all_healthy = True
    for repo_path in repo_paths:
        result = _docker_exec(
            container_id,
            ["test", "-d", f"/workspace/{repo_path}/.git"],
        )
        if result.returncode != 0:
            logger.error("Health check failed: /workspace/%s/.git not found", repo_path)
            all_healthy = False
        else:
            logger.info("Health check OK: /workspace/%s/", repo_path)

    return all_healthy


def _run_agent(
    container_id: str,
    agent_command: str,
    timeout: int,
    output_dir: Path,
    env_extra: dict[str, str] | None = None,
) -> tuple[int, float]:
    """Execute the agent command inside the container.

    Returns (exit_code, duration_seconds).
    """
    _SAFE_AGENT_CMD_RE = re.compile(r'^[\w./@: -]+$')
    if not _SAFE_AGENT_CMD_RE.match(agent_command):
        raise ValueError(
            f"agent_command contains unsafe characters: {agent_command!r}"
        )

    logger.info("Running agent: %s (timeout=%ds)", agent_command, timeout)

    # Write env vars to a temp file so they are not visible in `ps aux`
    env_items = dict(env_extra or {})
    env_items["HOME"] = "/home/agent"

    tmp_env_file = None
    start = time.monotonic()
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".env", delete=False
        ) as fh:
            for key, value in env_items.items():
                fh.write(f"{key}={value}\n")
            tmp_env_file = fh.name

        full_cmd = (
            ["docker", "exec",
             "--env-file", tmp_env_file,
             "-u", "agent",
             "-w", "/workspace", container_id]
            + ["bash", "-c",
               "mkdir -p /workspace/agent_output && "
               f"{agent_command} < /workspace/instruction.md"]
        )
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = time.monotonic() - start
        exit_code = result.returncode

        # Save agent logs
        (output_dir / "agent_stdout.log").write_text(result.stdout)
        (output_dir / "agent_stderr.log").write_text(result.stderr)
        logger.info("Agent finished in %.1fs (exit %d)", duration, exit_code)

    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        exit_code = 124
        (output_dir / "agent_stdout.log").write_text("")
        (output_dir / "agent_stderr.log").write_text(f"TIMEOUT after {timeout}s\n")
        logger.error("Agent timed out after %ds", timeout)

    finally:
        if tmp_env_file is not None:
            try:
                os.unlink(tmp_env_file)
            except OSError:
                pass

    return exit_code, duration


def _run_scoring(container_id: str) -> dict:
    """Run /workspace/test.sh and capture the JSON results."""
    logger.info("Running checkpoint verifiers...")

    result = _docker_exec(
        container_id,
        ["bash", "-c",
         "export WORKSPACE=/workspace TASK_DIR=/workspace/.task "
         "PYTHONPATH=/workspace/.eb_verify:${PYTHONPATH:-}; "
         "bash /workspace/test.sh"],
        timeout=300,
    )

    # test.sh outputs JSON to stdout, diagnostics to stderr
    if result.stderr:
        logger.info("Verifier diagnostics:\n%s", result.stderr.rstrip())

    # Parse the JSON output
    stdout = result.stdout.strip()
    if not stdout:
        return {
            "task_score": 0.0,
            "all_passed": False,
            "error": f"test.sh produced no output (exit {result.returncode})",
        }

    try:
        scores = json.loads(stdout)
    except json.JSONDecodeError as e:
        return {
            "task_score": 0.0,
            "all_passed": False,
            "error": f"test.sh output was not valid JSON: {e}",
            "raw_output": stdout[:2000],
        }

    return scores


def _save_results(
    result: TaskRunResult,
    task_data: dict,
    output_dir: Path,
    config: TaskRunConfig,
) -> Path:
    """Save run results, metadata, and scores to the output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    results_path = output_dir / "results.json"
    payload = {
        "task_id": result.task_id,
        "success": result.success,
        "phase": result.phase,
        "error": result.error,
        "image_tag": result.image_tag,
        "scores": result.scores,
        "timing": result.timing,
        "config": {
            "source": config.source,
            "agent_command": config.agent_command,
            "timeout": config.timeout,
            "dry_run": config.dry_run,
        },
        "task_metadata": {
            "suite": task_data.get("task", {}).get("suite", ""),
            "task_type": task_data.get("task", {}).get("task_type", ""),
            "difficulty": task_data.get("task", {}).get("difficulty", ""),
            "languages": task_data.get("metadata", {}).get("languages", []),
        },
    }

    results_path.write_text(json.dumps(payload, indent=2) + "\n")
    logger.info("Results saved to: %s", results_path)
    return results_path


def run_task(config: TaskRunConfig) -> TaskRunResult:
    """Execute the full single-session task lifecycle.

    Phases:
        1. Parse task.toml
        2. Generate and build Dockerfile
        3. Create container and set up workspace
        4. Run agent (unless --dry-run)
        5. Score with checkpoint verifiers
        6. Save results and clean up
    """
    timings: dict[str, float] = {}
    result = TaskRunResult(task_id="unknown")

    try:
        # --- Phase 1: Parse ---
        t0 = time.monotonic()
        task_data = _parse_task(config.task_toml)
        task_info = task_data["task"]
        task_id = task_info["id"]
        task_dir = config.task_toml.parent.resolve()
        repos = task_data.get("repos", [])

        result.task_id = task_id
        image_tag = f"eb-{task_id}"
        container_name = f"eb-run-{task_id}-{int(time.time())}"
        result.image_tag = image_tag
        timings["parse"] = time.monotonic() - t0

        # Resolve output directory
        if config.output_dir is not None:
            output_dir = config.output_dir
        else:
            output_dir = REPO_ROOT / "results" / "runs" / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        result.output_dir = str(output_dir)

        logger.info("Task: %s (suite=%s, type=%s)", task_id,
                     task_info.get("suite"), task_info.get("task_type"))

        # --- Phase 2: Build ---
        if not config.no_build:
            t0 = time.monotonic()
            dockerfile_path = _generate_dockerfile(config.task_toml, config.source)
            _docker_build(dockerfile_path, image_tag)
            timings["build"] = time.monotonic() - t0
        else:
            logger.info("Skipping Docker build (--no-build)")

        # --- Phase 3: Setup ---
        t0 = time.monotonic()
        container_id = _docker_create_container(image_tag, container_name)
        result.container_id = container_id
        _docker_start(container_id)
        _setup_container(container_id, task_dir, task_data)

        healthy = _run_health_check(container_id, repos)
        timings["setup"] = time.monotonic() - t0

        if not healthy:
            logger.warning("Health check reported issues (continuing anyway)")

        # --- Dry run stops here ---
        if config.dry_run:
            result.phase = "dry_run_complete"
            result.success = True
            result.timing = timings
            logger.info("Dry run complete. Container: %s, Image: %s", container_name, image_tag)
            return result

        # --- Phase 4: Agent ---
        # Resolve OAuth token if --account was specified
        env_extra: dict[str, str] = {}
        agent_command = config.agent_command
        if config.account is not None:
            oauth_token = _load_oauth_token(config.account)
            env_extra["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token
            # Use default OAuth agent command if none was explicitly provided
            if not agent_command:
                agent_command = DEFAULT_OAUTH_AGENT_COMMAND
            # Install Claude Code CLI inside the container
            if not _install_claude_cli(container_id):
                result.phase = "setup_failed"
                result.error = "Failed to install Claude Code CLI"
                return result

        if agent_command:
            t0 = time.monotonic()
            agent_exit, agent_duration = _run_agent(
                container_id, agent_command, config.timeout, output_dir,
                env_extra=env_extra,
            )
            timings["agent"] = agent_duration
        else:
            logger.info("No agent command specified, skipping agent phase")

        # --- Phase 5: Score ---
        t0 = time.monotonic()
        scores = _run_scoring(container_id)
        timings["scoring"] = time.monotonic() - t0
        result.scores = scores

        # --- Save ---
        result.phase = "complete"
        result.success = True
        result.timing = timings
        _save_results(result, task_data, output_dir, config)

        return result

    except Exception as e:
        result.error = type(e).__name__
        result.phase = "error"
        result.timing = timings
        logger.error("Task run failed: %s", e, exc_info=True)
        return result

    finally:
        # --- Phase 6: Cleanup ---
        if result.container_id and not config.keep_container:
            if not config.dry_run or not config.keep_container:
                logger.info("Cleaning up container: %s", result.container_id)
                _docker_stop_rm(result.container_id)
        elif result.container_id:
            logger.info("Keeping container for debugging: %s", result.container_id)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a single-session EnterpriseBench task in a Docker sandbox",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # Dry run: build container and validate setup
  python3 scripts/orchestration/run_task.py benchmarks/.../task.toml --dry-run

  # Run with an agent
  python3 scripts/orchestration/run_task.py benchmarks/.../task.toml --agent "claude -p"

  # Use upstream repos instead of mirrors
  python3 scripts/orchestration/run_task.py benchmarks/.../task.toml --source upstream --dry-run
""",
    )
    parser.add_argument(
        "task_toml",
        type=Path,
        help="Path to the task.toml file",
    )
    parser.add_argument(
        "--source",
        choices=["mirror", "upstream"],
        default="mirror",
        help="Clone source: 'mirror' (default) or 'upstream'",
    )
    parser.add_argument(
        "--agent",
        dest="agent_command",
        default="",
        help="Agent command to run (e.g. 'claude -p')",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Max seconds for agent execution (default: 1800)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to save results (default: results/runs/<task-id>/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build container and validate setup, but do not run agent",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Skip Docker build (reuse existing image)",
    )
    parser.add_argument(
        "--keep-container",
        action="store_true",
        help="Keep container after run for debugging",
    )
    parser.add_argument(
        "--account",
        type=int,
        default=None,
        help=(
            "OAuth account number N (loads token from "
            "~/.claude-homes/accountN/.claude/.credentials.json). "
            "When set, CLAUDE_CODE_OAUTH_TOKEN is passed into the container."
        ),
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = TaskRunConfig(
        task_toml=args.task_toml.resolve(),
        source=args.source,
        agent_command=args.agent_command,
        timeout=args.timeout,
        output_dir=args.output_dir.resolve() if args.output_dir else None,
        dry_run=args.dry_run,
        no_build=args.no_build,
        keep_container=args.keep_container,
        verbose=args.verbose,
        account=args.account,
    )

    result = run_task(config)

    # Print summary
    print()
    print("=" * 60)
    print(f"Task:      {result.task_id}")
    print(f"Phase:     {result.phase}")
    print(f"Success:   {result.success}")
    if result.error:
        print(f"Error:     {result.error}")
    if result.image_tag:
        print(f"Image:     {result.image_tag}")
    if result.output_dir:
        print(f"Output:    {result.output_dir}")
    if result.timing:
        print(f"Timing:    { {k: f'{v:.1f}s' for k, v in result.timing.items()} }")
    if result.scores:
        score = result.scores.get("task_score", "N/A")
        passed = result.scores.get("checkpoints_passed", "?")
        total = result.scores.get("checkpoints_total", "?")
        print(f"Score:     {score} ({passed}/{total} checkpoints)")
    print("=" * 60)

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
