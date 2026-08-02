"""provision — apply this repository's configuration to the machine."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import apply, blocks, config, facts, manifest, plan

MARKS = {"create": "+", "update": "~", "delete": "-"}


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="provision", description=__doc__)
    parser.add_argument("only", nargs="*", metavar="TASK", help="substring match; dependencies are pulled in")
    parser.add_argument("-n", "--dry-run", action="store_true", help="show what would change and exit")
    parser.add_argument("--root", type=Path, default=Path("/"), help="apply under this prefix instead of / (testing)")
    parser.add_argument("--tasks", type=Path, default=Path(__file__).resolve().parent.parent / "tasks")
    parser.add_argument("--vars", type=Path, default=Path(__file__).resolve().parent.parent / "vars.toml")
    parser.add_argument("--no-scripts", action="store_true", help="apply files but skip imperative steps")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    # Task scripts write straight to the terminal; stay in step with them.
    sys.stdout.reconfigure(line_buffering=True)

    if args.root == Path("/") and os.geteuid() != 0:
        sys.exit("must run as root (or pass --root for a test prefix)")

    variables = config.load_vars(args.vars)
    tasks = config.load_tasks(args.tasks)
    runnable, skipped = plan.select(tasks, args.only)

    for name, reason in skipped:
        print(f"skip  {name}  ({reason})")

    changes, owned = apply.stage(runnable, args.root, variables)

    state = args.root / "var/lib/provision/manifest.json"
    previous = manifest.load(state)
    # Only reconcile what this run could have redeclared, or a filtered run
    # would delete everything the unselected tasks own.
    if args.only:
        orphans = []
    else:
        orphans = manifest.orphans(previous, owned)
    changes = apply.reclaim(orphans, args.root) + changes

    for change in changes:
        label = change.note or change.task
        print(f"{MARKS[change.action]}     {change.path}  ({label})")

    if args.dry_run:
        for change in changes:
            body = change.diff()
            if body:
                print()
                print(body, end="")
        if not changes:
            print("no changes")
        return 0

    apply.commit(changes, args.root)
    if args.only:
        # A filtered run never staged the unselected tasks, so preserve theirs.
        keys = {entry.key() for entry in owned}
        owned |= {entry for entry in previous if entry.key() not in keys}
    manifest.save(state, owned)

    if not args.no_scripts:
        for task in runnable:
            if task.script_path():
                touched = [c.path for c in changes if c.task == task.name]
                print(f"run   {task.name}")
                apply.run_script(task, args.root, touched, variables)

    if not changes:
        print("no file changes")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (config.ConfigError, blocks.BlockError) as exc:
        sys.exit(f"provision: {exc}")
    except KeyboardInterrupt:
        sys.exit(130)
