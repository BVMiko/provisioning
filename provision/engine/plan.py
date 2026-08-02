"""Task selection and ordering."""

from __future__ import annotations

from .config import ConfigError, Task


def order(tasks: dict[str, Task]) -> list[Task]:
    """Dependency order, alphabetical among independent tasks."""
    for task in tasks.values():
        for dependency in task.requires:
            if dependency not in tasks:
                raise ConfigError(f"{task.name} requires unknown task {dependency}")

    ordered: list[Task] = []
    state: dict[str, int] = {}

    def visit(name: str, trail: tuple[str, ...]) -> None:
        if state.get(name) == 2:
            return
        if state.get(name) == 1:
            cycle = " -> ".join(trail[trail.index(name):] + (name,))
            raise ConfigError(f"dependency cycle: {cycle}")
        state[name] = 1
        for dependency in sorted(tasks[name].requires):
            visit(dependency, trail + (name,))
        state[name] = 2
        ordered.append(tasks[name])

    for name in sorted(tasks):
        visit(name, ())
    return ordered


def select(tasks: dict[str, Task], only: list[str] | None) -> tuple[list[Task], list[tuple[str, str]]]:
    """Return tasks to run, plus (name, reason) pairs for those skipped."""
    chosen = order(tasks)

    if only:
        wanted = {t.name for t in chosen if any(f in t.name for f in only)}
        if not wanted:
            raise ConfigError(f"no task matches {only}")
        # Pull in dependencies of anything explicitly requested.
        changed = True
        while changed:
            changed = False
            for task in chosen:
                if task.name in wanted:
                    for dependency in task.requires:
                        if dependency not in wanted:
                            wanted.add(dependency)
                            changed = True
        chosen = [t for t in chosen if t.name in wanted]

    runnable, skipped = [], []
    satisfied: set[str] = set()
    for task in chosen:
        met, reason = task.when.met()
        if not met:
            skipped.append((task.name, reason))
            continue
        missing = [d for d in task.requires if d not in satisfied]
        if missing:
            skipped.append((task.name, f"depends on skipped {', '.join(missing)}"))
            continue
        runnable.append(task)
        satisfied.add(task.name)
    return runnable, skipped
