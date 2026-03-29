"""Shared task directory discovery for EnterpriseBench scripts."""

from pathlib import Path

BENCHMARKS_DIR = Path(__file__).resolve().parent.parent.parent / "benchmarks"


def find_task_dirs(
    benchmarks_dir: Path | None = None,
    exclude_archived: bool = True,
    exclude_mined: bool = True,
) -> list[Path]:
    """Find all task directories containing task.toml under benchmarks/.

    Args:
        benchmarks_dir: Root benchmarks directory. Defaults to the repo's benchmarks/.
        exclude_archived: Skip directories whose name starts with '_' (e.g. _archived).
        exclude_mined: Skip the 'mined' directory.

    Returns:
        Sorted list of Path objects pointing to task directories.
    """
    root = benchmarks_dir or BENCHMARKS_DIR
    skip_names: set[str] = set()
    if exclude_archived:
        skip_names.add("_archived")
    if exclude_mined:
        skip_names.add("mined")

    tasks: list[Path] = []
    for suite_dir in sorted(root.iterdir()):
        if not suite_dir.is_dir():
            continue
        if suite_dir.name in skip_names or suite_dir.name.startswith("_"):
            continue
        if suite_dir.name.endswith(".toml"):
            continue
        for task_dir in sorted(suite_dir.iterdir()):
            if not task_dir.is_dir():
                continue
            if task_dir.name.startswith("_"):
                continue
            toml_path = task_dir / "task.toml"
            if toml_path.exists():
                tasks.append(task_dir)
    return tasks
