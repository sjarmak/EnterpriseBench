"""Descriptor-safe filesystem operations for one promotion publication."""

from __future__ import annotations

import os
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Mapping

if __package__:
    from .promotion_types import PromotionContext
else:
    from promotion_types import PromotionContext

_DIRECTORY_FLAGS = (
    os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
)
_FILE_READ_FLAGS = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
_FILE_WRITE_FLAGS = (
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
)
DirectoryIdentity = tuple[int, int]


def ensure_staging_directory(ctx: PromotionContext, *, create: bool) -> Path:
    """Prove the entire staging path is beneath the trusted repository."""

    with open_publication_directory(ctx, location="staging", create=create):
        return ctx.staging_dir


@contextmanager
def open_publication_directory(
    ctx: PromotionContext,
    *,
    location: str,
    create: bool = False,
) -> Iterator[int]:
    """Open a publication directory without following any descendant symlink."""

    path = _publication_path(ctx, location)
    descriptor = _open_directory_chain(ctx.repo_root, path, create=create)
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def write_new_staged_artifacts(
    ctx: PromotionContext,
    artifacts: Mapping[str, bytes],
) -> None:
    """Create a set of artifacts only when every target name is absent."""

    with open_publication_directory(ctx, location="staging", create=True) as directory:
        for name in artifacts:
            _validate_artifact_name(name)
            if _entry_exists(directory, name):
                raise RuntimeError(f"preexisting staged artifact: {name}")
        for name, source in artifacts.items():
            _write_artifact(directory, name, source, replace=False)


def write_staged_artifact(
    ctx: PromotionContext,
    name: str,
    source: bytes,
    *,
    replace: bool,
) -> None:
    """Write one artifact through an already verified directory boundary."""

    _validate_artifact_name(name)
    with open_publication_directory(ctx, location="staging") as directory:
        _write_artifact(directory, name, source, replace=replace)


def read_publication_artifact(
    ctx: PromotionContext,
    name: str,
    *,
    location: str = "staging",
) -> bytes:
    """Read one single-link regular artifact without following a symlink."""

    _validate_artifact_name(name)
    with open_publication_directory(ctx, location=location) as directory:
        descriptor = _open_regular_file(directory, name)
        try:
            return _read_descriptor(descriptor)
        finally:
            os.close(descriptor)


def read_trusted_repository_file(repo_root: Path, relative_path: str) -> bytes:
    """Read an exact repository file without following descendant symlinks."""

    path = Path(relative_path)
    if (
        not relative_path
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.name in {"", ".", ".."}
    ):
        raise RuntimeError("trusted repository file path is invalid")
    parent_path = repo_root.joinpath(*path.parts[:-1])
    parent = (
        os.open(repo_root, _DIRECTORY_FLAGS)
        if parent_path == repo_root
        else _open_directory_chain(repo_root, parent_path, create=False)
    )
    try:
        descriptor = _open_regular_file(parent, path.name)
        try:
            return _read_descriptor(descriptor)
        finally:
            os.close(descriptor)
    except RuntimeError as exc:
        raise RuntimeError("trusted repository file is not safely readable") from exc
    finally:
        os.close(parent)


def read_registry_source(ctx: PromotionContext) -> bytes | None:
    """Read the official registry only as a single-link regular file."""

    name = _registry_name(ctx)
    with _open_official_directory(ctx) as official:
        if not _entry_exists(official, name):
            return None
        descriptor = _open_regular_file(official, name)
        try:
            return _read_descriptor(descriptor)
        finally:
            os.close(descriptor)


def write_registry_source(
    ctx: PromotionContext,
    source: bytes,
) -> None:
    """Write registry bytes through the verified official dirfd."""

    with _open_official_directory(ctx) as official:
        _write_artifact(official, _registry_name(ctx), source, replace=True)


def write_forensics_artifacts(
    ctx: PromotionContext,
    stem: str,
    artifacts: Mapping[str, bytes],
) -> Path:
    """Create one collision-resistant forensic directory through held dirfds."""

    expected = ctx.final_dir.parent / "_failures"
    if ctx.forensics_dir != expected:
        raise RuntimeError("forensics path does not match the official publication")
    parent = _open_directory_chain(ctx.repo_root, expected, create=True)
    try:
        directory_name = _create_unique_directory(parent, stem)
        directory = os.open(directory_name, _DIRECTORY_FLAGS, dir_fd=parent)
        try:
            for name, source in artifacts.items():
                _validate_artifact_name(name)
                _write_artifact(directory, name, source, replace=False)
            os.fsync(directory)
        finally:
            os.close(directory)
        os.fsync(parent)
        return expected / directory_name
    finally:
        os.close(parent)


def remove_staged_artifact(ctx: PromotionContext, name: str) -> None:
    """Remove an entry by name without following it."""

    _validate_artifact_name(name)
    with open_publication_directory(ctx, location="staging") as directory:
        try:
            os.unlink(name, dir_fd=directory)
        except FileNotFoundError:
            return


def validate_publication_inventory(
    ctx: PromotionContext,
    expected: frozenset[str],
    *,
    location: str = "staging",
) -> None:
    """Require an exact inventory of single-link regular files."""

    with open_publication_directory(ctx, location=location) as directory:
        _validate_inventory_descriptor(directory, expected)


def freeze_staged_publication(
    ctx: PromotionContext,
    expected: frozenset[str],
) -> DirectoryIdentity:
    """Freeze artifacts and directory entries before the same-parent rename."""

    validate_publication_inventory(ctx, expected)
    with open_publication_directory(ctx, location="staging") as directory:
        for name in expected:
            descriptor = _open_regular_file(directory, name)
            try:
                os.fchmod(descriptor, 0o444)
            finally:
                os.close(descriptor)
        os.fchmod(directory, 0o555)
        os.fsync(directory)
        return _directory_identity(directory)


def validate_frozen_publication(
    ctx: PromotionContext,
    expected: frozenset[str],
    *,
    location: str,
) -> None:
    """Require the frozen directory and every artifact to retain exact modes."""

    with open_publication_directory(ctx, location=location) as directory:
        _validate_inventory_descriptor(directory, expected)
        if stat.S_IMODE(os.fstat(directory).st_mode) != 0o555:
            raise RuntimeError("publication directory is not frozen")
        for name in expected:
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if stat.S_IMODE(info.st_mode) != 0o444:
                raise RuntimeError(f"publication artifact is not frozen: {name}")


def validate_publication_identity(
    ctx: PromotionContext,
    expected: DirectoryIdentity,
    *,
    location: str,
) -> None:
    """Require the named publication path to resolve to one frozen inode."""

    with open_publication_directory(ctx, location=location) as directory:
        if _directory_identity(directory) != expected:
            raise RuntimeError("publication directory inode changed")


def lock_final_publication_directory(ctx: PromotionContext) -> None:
    """Prevent creation or removal of entries in the renamed publication."""

    with open_publication_directory(ctx, location="final") as directory:
        os.fchmod(directory, 0o555)
        os.fsync(directory)


def thaw_publication(ctx: PromotionContext, *, location: str) -> None:
    """Restore owner write access so a failed publication can be rolled back."""

    try:
        with open_publication_directory(ctx, location=location) as directory:
            os.fchmod(directory, 0o700)
            for name in os.listdir(directory):
                try:
                    info = os.stat(name, dir_fd=directory, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                if stat.S_ISREG(info.st_mode):
                    descriptor = _open_regular_file(
                        directory,
                        name,
                        require_single_link=False,
                    )
                    try:
                        os.fchmod(descriptor, 0o600)
                    finally:
                        os.close(descriptor)
    except RuntimeError:
        return


def rename_staging_to_final(
    ctx: PromotionContext,
    expected_identity: DirectoryIdentity,
    rename: Callable[..., None] = os.rename,
) -> None:
    """Rename through verified parent descriptors on the same filesystem."""

    with _open_official_directory(ctx) as official:
        staging_name = _staging_name(ctx)
        _require_entry_identity(
            official,
            staging_name,
            expected_identity,
            "staging publication",
        )
        if _entry_exists(official, ctx.run_id):
            raise RuntimeError(
                "atomic_publish: final dir already exists "
                f"(refusing to overwrite): {ctx.final_dir}"
            )
        rename(
            staging_name,
            ctx.run_id,
            src_dir_fd=official,
            dst_dir_fd=official,
        )
        published = _entry_identity(official, ctx.run_id)
        if published != expected_identity:
            _quarantine_entry(
                official,
                ctx.run_id,
                published,
                f".{ctx.run_id}.rejected",
            )
            raise RuntimeError("renamed publication does not match frozen staging")


def final_publication_exists(ctx: PromotionContext) -> bool:
    """Check the final run name beneath a descriptor-verified official root."""

    with _open_official_directory(ctx) as official:
        return _entry_exists(official, ctx.run_id)


def staging_publication_exists(ctx: PromotionContext) -> bool:
    """Check the staging run name without following any ancestor symlink."""

    _publication_path(ctx, "staging")
    with _open_official_directory(ctx) as official:
        return _entry_exists(official, _staging_name(ctx))


def quarantine_staging_publication(ctx: PromotionContext) -> None:
    """Quarantine the exact staging inode without recursively deleting a race."""

    _publication_path(ctx, "staging")
    with _open_official_directory(ctx) as parent:
        staging_name = _staging_name(ctx)
        try:
            descriptor = os.open(staging_name, _DIRECTORY_FLAGS, dir_fd=parent)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise RuntimeError("staging publication is not a real directory") from exc
        try:
            identity = _directory_identity(descriptor)
            _quarantine_entry(
                parent,
                staging_name,
                identity,
                f".{ctx.run_id}.discarded",
            )
        finally:
            os.close(descriptor)


def rename_final_to_staging(
    ctx: PromotionContext,
    rename: Callable[..., None] = os.rename,
) -> Path:
    """Move a failed final publication back through verified descriptors."""

    with _open_official_directory(ctx) as official:
        identity = _entry_identity(official, ctx.run_id)
        staging_name = _staging_name(ctx)
        destination = (
            _unique_entry_name(official, f".{ctx.run_id}.failed")
            if _entry_exists(official, staging_name)
            else staging_name
        )
        rename(
            ctx.run_id,
            destination,
            src_dir_fd=official,
            dst_dir_fd=official,
        )
        _require_entry_identity(
            official,
            destination,
            identity,
            "rolled-back publication",
        )
        return ctx.final_dir.parent / destination


def _publication_path(ctx: PromotionContext, location: str) -> Path:
    expected_staging = ctx.final_dir.parent / _staging_name(ctx)
    if ctx.staging_dir != expected_staging:
        raise RuntimeError("staging path does not match the named publication")
    if location == "staging":
        return expected_staging
    if location == "final":
        return ctx.final_dir
    raise ValueError(f"unknown publication location: {location}")


def _staging_name(ctx: PromotionContext) -> str:
    return f".{ctx.run_id}.staging"


def _registry_name(ctx: PromotionContext) -> str:
    expected = ctx.final_dir.parent / "_registry.json"
    if ctx.registry_path != expected:
        raise RuntimeError("registry path does not match the official publication")
    return expected.name


@contextmanager
def _open_official_directory(ctx: PromotionContext) -> Iterator[int]:
    descriptor = _open_directory_chain(
        ctx.repo_root,
        ctx.final_dir.parent,
        create=False,
    )
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def _open_directory_chain(root: Path, target: Path, *, create: bool) -> int:
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(
            "publication path is outside the trusted repository"
        ) from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise RuntimeError("publication path is outside the trusted repository")
    try:
        current = os.open(root, _DIRECTORY_FLAGS)
    except OSError as exc:
        raise RuntimeError("trusted repository root is not a real directory") from exc
    try:
        for part in relative.parts:
            try:
                child = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
            except FileNotFoundError:
                if not create:
                    raise RuntimeError("publication directory is missing") from None
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current)
                    child = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
                except OSError as exc:
                    raise RuntimeError(
                        "cannot create publication directory safely"
                    ) from exc
            except OSError as exc:
                raise RuntimeError(
                    "staging path contains a symlink or non-directory"
                ) from exc
            os.close(current)
            current = child
        return current
    except BaseException:
        os.close(current)
        raise


def _write_artifact(
    directory: int,
    name: str,
    source: bytes,
    *,
    replace: bool,
) -> None:
    if replace and _entry_exists(directory, name):
        descriptor = _open_regular_file(directory, name)
        os.close(descriptor)
    elif not replace and _entry_exists(directory, name):
        raise RuntimeError(f"preexisting staged artifact: {name}")
    temporary = f".{name}.{secrets.token_hex(12)}"
    descriptor = os.open(temporary, _FILE_WRITE_FLAGS, 0o600, dir_fd=directory)
    try:
        view = memoryview(source)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        if replace:
            os.rename(
                temporary,
                name,
                src_dir_fd=directory,
                dst_dir_fd=directory,
            )
        else:
            os.link(
                temporary,
                name,
                src_dir_fd=directory,
                dst_dir_fd=directory,
                follow_symlinks=False,
            )
            os.unlink(temporary, dir_fd=directory)
        os.fsync(directory)
    except BaseException:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        raise


def _open_regular_file(
    directory: int,
    name: str,
    *,
    require_single_link: bool = True,
) -> int:
    try:
        descriptor = os.open(name, _FILE_READ_FLAGS, dir_fd=directory)
    except OSError as exc:
        raise RuntimeError(
            f"publication artifact is not a single-link regular artifact: {name}"
        ) from exc
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or (require_single_link and info.st_nlink != 1):
        os.close(descriptor)
        raise RuntimeError(
            f"publication artifact is not a single-link regular file: {name}"
        )
    return descriptor


def _read_descriptor(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    while chunk := os.read(descriptor, 1024 * 1024):
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_inventory_descriptor(
    directory: int,
    expected: frozenset[str],
) -> None:
    actual = set(os.listdir(directory))
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        raise RuntimeError(f"missing staged artifact(s): {', '.join(missing)}")
    if unexpected:
        raise RuntimeError(f"unexpected staged artifact(s): {', '.join(unexpected)}")
    for name in expected:
        info = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError("staged publication contains a non-regular artifact")
        if info.st_nlink != 1:
            raise RuntimeError(
                "staged publication requires each file to be a "
                "single-link regular artifact"
            )


def _directory_identity(descriptor: int) -> DirectoryIdentity:
    info = os.fstat(descriptor)
    if not stat.S_ISDIR(info.st_mode):
        raise RuntimeError("publication descriptor is not a directory")
    return info.st_dev, info.st_ino


def _entry_identity(directory: int, name: str) -> DirectoryIdentity:
    info = os.stat(name, dir_fd=directory, follow_symlinks=False)
    if not stat.S_ISDIR(info.st_mode):
        raise RuntimeError("publication entry is not a directory")
    return info.st_dev, info.st_ino


def _require_entry_identity(
    directory: int,
    name: str,
    expected: DirectoryIdentity,
    label: str,
) -> None:
    if _entry_identity(directory, name) != expected:
        raise RuntimeError(f"{label} inode changed")


def _quarantine_entry(
    directory: int,
    source: str,
    expected: DirectoryIdentity,
    prefix: str,
) -> None:
    destination = _unique_entry_name(directory, prefix)
    os.replace(
        source,
        destination,
        src_dir_fd=directory,
        dst_dir_fd=directory,
    )
    _require_entry_identity(
        directory,
        destination,
        expected,
        "quarantined publication",
    )


def _unique_entry_name(directory: int, prefix: str) -> str:
    for _attempt in range(32):
        name = f"{prefix}.{secrets.token_hex(12)}"
        if not _entry_exists(directory, name):
            return name
    raise RuntimeError("cannot allocate a unique publication quarantine name")


def _create_unique_directory(parent: int, stem: str) -> str:
    _validate_artifact_name(stem)
    for _attempt in range(32):
        name = f"{stem}.{secrets.token_hex(12)}"
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent)
        except FileExistsError:
            continue
        return name
    raise RuntimeError("cannot allocate a unique forensics directory")


def _entry_exists(directory: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _validate_artifact_name(name: str) -> None:
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("publication artifact name must be a single path component")
