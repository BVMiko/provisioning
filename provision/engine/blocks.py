"""Managed regions inside files the engine does not own outright.

Prefer a drop-in directory where the software supports one, and whole-file
ownership where the engine owns the file. Use a block only for plain files with
neither, such as /etc/hosts or a shell rc file.
"""

from __future__ import annotations


class BlockError(Exception):
    pass


def _locate(lines: list[str], begin: str, end: str) -> tuple[int, int] | None:
    starts = [i for i, line in enumerate(lines) if line.strip() == begin]
    ends = [i for i, line in enumerate(lines) if line.strip() == end]

    if not starts and not ends:
        return None
    if len(starts) != 1 or len(ends) != 1:
        raise BlockError(
            f"expected one {begin!r}/{end!r} pair, found {len(starts)} and {len(ends)}"
        )
    if ends[0] < starts[0]:
        raise BlockError(f"{end!r} precedes {begin!r}")
    return starts[0], ends[0]


def splice(existing: str, begin: str, end: str, body: str, position: str) -> str:
    """Insert or replace the marked region, returning the whole file."""
    lines = existing.splitlines()
    marked = [begin, *body.splitlines(), end]
    found = _locate(lines, begin, end)

    if found:
        start, stop = found
        if lines[start : stop + 1] == marked:
            return existing
        lines[start : stop + 1] = marked
    elif position == "prepend":
        lines = marked + lines
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines = lines + marked

    return "\n".join(lines) + "\n"


def remove(existing: str, begin: str, end: str) -> str:
    """Splice the marked region out, leaving the rest of the file alone."""
    lines = existing.splitlines()
    found = _locate(lines, begin, end)
    if not found:
        return existing
    start, stop = found
    del lines[start : stop + 1]
    while start and start <= len(lines) and not lines[start - 1].strip():
        del lines[start - 1]
        start -= 1
    return "\n".join(lines) + "\n" if lines else ""
