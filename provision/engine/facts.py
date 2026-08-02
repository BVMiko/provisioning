"""Machine facts, available to task conditions and to templates."""

from __future__ import annotations

import functools
import os
import pwd
import shutil
import socket
import subprocess

ROLES_FILE = "/etc/provision/roles"
USERS_FILE = "/etc/provision/users"


@functools.cache
def os_release() -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        with open("/etc/os-release") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                data[key.lower()] = value.strip("\"'")
    except FileNotFoundError:
        pass
    return data


@functools.cache
def roles() -> frozenset[str]:
    raw = os.environ.get("PROVISION_ROLES")
    if raw is None:
        try:
            raw = open(ROLES_FILE).read()
        except FileNotFoundError:
            raw = ""
    return frozenset(raw.replace(",", " ").split())


@functools.cache
def installed(package: str) -> bool:
    result = subprocess.run(
        ["dpkg-query", "-W", "-f=${db:Status-Abbrev}", package],
        capture_output=True,
        text=True,
    )
    return result.stdout.startswith("ii")


@functools.cache
def has_command(name: str) -> bool:
    return shutil.which(name) is not None


@functools.cache
def users() -> tuple[pwd.struct_passwd, ...]:
    """Login accounts that user-scoped files apply to."""
    try:
        names = set(open(USERS_FILE).read().split())
    except FileNotFoundError:
        names = set()

    selected = []
    for entry in pwd.getpwall():
        if names:
            if entry.pw_name in names:
                selected.append(entry)
        elif 1000 <= entry.pw_uid < 60000 and not entry.pw_shell.endswith(
            ("nologin", "false")
        ):
            selected.append(entry)
    return tuple(sorted(selected, key=lambda e: e.pw_name))


def context() -> dict:
    """Template and condition context."""
    release = os_release()
    return {
        "hostname": socket.gethostname(),
        "roles": sorted(roles()),
        "codename": release.get("version_codename", ""),
        "version_id": release.get("version_id", ""),
        "arch": os.uname().machine,
        "installed": installed,
        "has_command": has_command,
    }
