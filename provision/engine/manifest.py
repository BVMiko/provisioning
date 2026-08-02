"""Record of what the engine owns, so removals propagate to machines."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

VERSION = 1


@dataclass(frozen=True, order=True)
class Entry:
    kind: str  # "file" or "block"
    path: str
    marker: str = ""
    comment: str = "#"

    def key(self) -> tuple[str, str, str]:
        return self.kind, self.path, self.marker


def load(path: Path) -> set[Entry]:
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        return set()
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is corrupt: {exc}")
    return {Entry(**entry) for entry in raw.get("entries", [])}


def save(path: Path, entries: set[Entry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": VERSION,
        "entries": [asdict(entry) for entry in sorted(entries)],
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(path)


def orphans(previous: set[Entry], current: set[Entry]) -> list[Entry]:
    """Entries the engine owned last run and no longer declares."""
    keys = {entry.key() for entry in current}
    return sorted(entry for entry in previous if entry.key() not in keys)
