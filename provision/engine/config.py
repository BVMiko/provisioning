"""Task definitions, loaded from tasks/*/task.toml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import tomllib

from . import facts


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class FileSpec:
    dst: str
    src: str | None = None
    content: str | None = None
    mode: str = "0644"
    owner: str | None = None
    group: str | None = None
    scope: str = "system"
    template: bool | None = None

    def is_template(self) -> bool:
        if self.template is not None:
            return self.template
        return bool(self.src and self.src.endswith(".j2"))


@dataclass(frozen=True)
class BlockSpec:
    path: str
    marker: str
    src: str | None = None
    content: str | None = None
    comment: str = "#"
    position: str = "append"
    scope: str = "system"
    create: bool = False
    template: bool | None = None

    def is_template(self) -> bool:
        if self.template is not None:
            return self.template
        return bool(self.src and self.src.endswith(".j2"))

    def begin(self) -> str:
        return f"{self.comment} BEGIN {self.marker}"

    def end(self) -> str:
        return f"{self.comment} END {self.marker}"


@dataclass(frozen=True)
class When:
    roles: tuple[str, ...] = ()
    installed: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    hostnames: tuple[str, ...] = ()

    def met(self) -> tuple[bool, str]:
        if self.roles and not (set(self.roles) & facts.roles()):
            return False, f"needs role {' or '.join(self.roles)}"
        for package in self.installed:
            if not facts.installed(package):
                return False, f"{package} not installed"
        for command in self.commands:
            if not facts.has_command(command):
                return False, f"{command} not on PATH"
        if self.hostnames:
            import socket

            if socket.gethostname() not in self.hostnames:
                return False, "hostname does not match"
        return True, ""


@dataclass(frozen=True)
class Task:
    name: str
    directory: Path
    description: str = ""
    requires: tuple[str, ...] = ()
    when: When = field(default_factory=When)
    files: tuple[FileSpec, ...] = ()
    blocks: tuple[BlockSpec, ...] = ()
    script: str | None = None

    def script_path(self) -> Path | None:
        return self.directory / self.script if self.script else None


def _spec(cls, raw: dict, where: str):
    known = {f.name for f in cls.__dataclass_fields__.values()}
    unknown = set(raw) - known
    if unknown:
        raise ConfigError(f"{where}: unknown keys {sorted(unknown)}")
    return cls(**raw)


def load_task(directory: Path) -> Task:
    manifest = directory / "task.toml"
    try:
        raw = tomllib.loads(manifest.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{manifest}: {exc}") from exc

    where = str(manifest)
    files = tuple(_spec(FileSpec, f, where) for f in raw.pop("files", []))
    blocks = tuple(_spec(BlockSpec, b, where) for b in raw.pop("blocks", []))
    when = _spec(When, raw.pop("when", {}), where)

    for spec in files + blocks:
        target = spec.dst if isinstance(spec, FileSpec) else spec.path
        if bool(spec.src) == bool(spec.content):
            raise ConfigError(f"{where}: set exactly one of src or content")
        if spec.scope not in ("system", "user"):
            raise ConfigError(f"{where}: scope must be system or user")
        if spec.src and not (directory / spec.src).is_file():
            raise ConfigError(f"{where}: missing source {spec.src}")
        if spec.scope == "system" and not target.startswith("/"):
            raise ConfigError(f"{where}: system paths must be absolute: {target}")
        if spec.scope == "user" and target.startswith("/"):
            raise ConfigError(f"{where}: user paths are relative to home: {target}")

    for block in blocks:
        if block.position not in ("append", "prepend"):
            raise ConfigError(f"{where}: position must be append or prepend")

    raw.pop("name", None)
    return _spec(
        Task,
        {
            "name": directory.name,
            "directory": directory,
            "files": files,
            "blocks": blocks,
            "when": when,
            **{k: tuple(v) if k == "requires" else v for k, v in raw.items()},
        },
        where,
    )


def load_vars(path: Path) -> dict:
    """Repository-wide values, merged into the template context."""
    try:
        raw = tomllib.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    for key, value in raw.items():
        if not isinstance(value, (str, int, float, bool)):
            raise ConfigError(f"{path}: {key} must be a scalar")
    return raw


def load_tasks(root: Path) -> dict[str, Task]:
    tasks = {}
    for manifest in sorted(root.glob("*/task.toml")):
        task = load_task(manifest.parent)
        tasks[task.name] = task
    if not tasks:
        raise ConfigError(f"no tasks found under {root}")
    return tasks
