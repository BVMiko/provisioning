"""Render tasks into a desired state, diff it against the machine, apply it."""

from __future__ import annotations

import difflib
import grp
import os
import pwd
import subprocess
from dataclasses import dataclass
from pathlib import Path

import jinja2

from . import blocks, facts, manifest
from .config import BlockSpec, FileSpec, Task


@dataclass
class Change:
    path: Path
    before: str | None
    after: str | None
    mode: int | None = None
    owner: str | None = None
    group: str | None = None
    task: str = ""
    note: str = ""

    @property
    def action(self) -> str:
        if self.after is None:
            return "delete"
        if self.before is None:
            return "create"
        return "update"

    def diff(self) -> str:
        lines = difflib.unified_diff(
            (self.before or "").splitlines(keepends=True),
            (self.after or "").splitlines(keepends=True),
            fromfile=f"a{self.path}",
            tofile=f"b{self.path}",
        )
        return "".join(lines)


class Renderer:
    def __init__(self, context: dict):
        self.context = context

    def render(self, task: Task, spec: FileSpec | BlockSpec, extra: dict) -> str:
        if spec.content is not None:
            source = spec.content
        else:
            source = (task.directory / spec.src).read_text()
        if not spec.is_template():
            return source
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(task.directory),
            undefined=jinja2.StrictUndefined,
            keep_trailing_newline=True,
        )
        return env.from_string(source).render(**self.context, **extra)


def _targets(spec: FileSpec | BlockSpec, dst: str) -> list[tuple[Path, dict, str | None]]:
    """(path, template extras, owner) for each place this spec applies."""
    if spec.scope == "system":
        return [(Path(dst), {}, None)]
    return [
        (Path(entry.pw_dir) / dst, {"user": entry.pw_name, "home": entry.pw_dir}, entry.pw_name)
        for entry in facts.users()
    ]


def _real(root: Path, dst: Path) -> Path:
    return root / dst.relative_to("/") if dst.is_absolute() else root / dst


def _read(path: Path) -> str | None:
    try:
        return path.read_text()
    except FileNotFoundError:
        return None
    except UnicodeDecodeError:
        raise SystemExit(f"{path} is not text; the engine only manages text files")


def stage(tasks: list[Task], root: Path, variables: dict) -> tuple[list[Change], set[manifest.Entry]]:
    renderer = Renderer({**facts.context(), **variables})
    changes: list[Change] = []
    owned: set[manifest.Entry] = set()
    # Several tasks may touch different blocks of one file; each builds on the last.
    pending: dict[Path, str] = {}

    for task in tasks:
        for spec in task.files:
            for dst, extra, owner in _targets(spec, spec.dst):
                real = _real(root, dst)
                body = renderer.render(task, spec, extra)
                before = pending.get(real, _read(real))
                owned.add(manifest.Entry("file", str(dst)))
                pending[real] = body
                if before != body:
                    changes.append(
                        Change(
                            path=dst,
                            before=before,
                            after=body,
                            mode=int(spec.mode, 8),
                            owner=spec.owner or owner,
                            group=spec.group,
                            task=task.name,
                        )
                    )

        for spec in task.blocks:
            for dst, extra, owner in _targets(spec, spec.path):
                real = _real(root, dst)
                body = renderer.render(task, spec, extra)
                before = pending.get(real, _read(real))
                if before is None and not spec.create:
                    raise SystemExit(
                        f"{task.name}: {dst} does not exist; set create = true to make it"
                    )
                after = blocks.splice(
                    before or "", spec.begin(), spec.end(), body, spec.position
                )
                owned.add(manifest.Entry("block", str(dst), spec.marker, spec.comment))
                pending[real] = after
                if before != after:
                    changes.append(
                        Change(
                            path=dst,
                            before=before,
                            after=after,
                            owner=owner,
                            task=task.name,
                            note=f"block {spec.marker}",
                        )
                    )

    return changes, owned


def reclaim(orphans: list[manifest.Entry], root: Path) -> list[Change]:
    """Undo entries the engine owned last run and no longer declares."""
    changes = []
    for entry in orphans:
        dst = Path(entry.path)
        real = _real(root, dst)
        before = _read(real)
        if before is None:
            continue
        if entry.kind == "file":
            after = None
        else:
            after = blocks.remove(
                before, f"{entry.comment} BEGIN {entry.marker}", f"{entry.comment} END {entry.marker}"
            )
            if after == before:
                continue
        changes.append(Change(path=dst, before=before, after=after, note="no longer managed"))
    return changes


def commit(changes: list[Change], root: Path) -> None:
    for change in changes:
        real = _real(root, change.path)
        if change.after is None:
            real.unlink(missing_ok=True)
            continue
        real.parent.mkdir(parents=True, exist_ok=True)
        tmp = real.with_name(real.name + ".provision-tmp")
        tmp.write_text(change.after)
        if change.mode is not None:
            os.chmod(tmp, change.mode)
        elif change.before is None:
            os.chmod(tmp, 0o644)
        else:
            os.chmod(tmp, os.stat(real).st_mode & 0o7777)
        if change.owner or change.group:
            uid = pwd.getpwnam(change.owner).pw_uid if change.owner else -1
            gid = grp.getgrnam(change.group).gr_gid if change.group else -1
            os.chown(tmp, uid, gid)
        tmp.replace(real)


def run_script(task: Task, root: Path, changed: list[Path], variables: dict) -> None:
    script = task.script_path()
    if not script:
        return
    env = {
        **os.environ,
        "TASK": task.name,
        "PROVISION_ROOT": str(root),
        "PROVISION_ROLES": " ".join(sorted(facts.roles())),
        "PROVISION_CHANGED": "\n".join(str(p) for p in changed),
        **{f"PROVISION_VAR_{k.upper()}": str(v) for k, v in variables.items()},
    }
    subprocess.run(["bash", str(script)], env=env, check=True)
