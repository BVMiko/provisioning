# Helpers for task run.sh scripts. Sourced, not executed.
#
# The engine owns managed files, roles and ordering. These cover only the
# imperative work a task does after its files are in place. The engine exports
# TASK, PROVISION_ROOT, PROVISION_ROLES and PROVISION_CHANGED.
set -euo pipefail

log()  { printf '[%s] %s\n' "${TASK:-provision}" "$*" >&2; }
die()  { printf '[%s] ERROR: %s\n' "${TASK:-provision}" "$*" >&2; exit 1; }

installed() {
    dpkg-query -W -f='${db:Status-Abbrev}' "$1" 2>/dev/null | grep -q '^ii'
}

apt_update_if_stale() {
    local stamp=/var/lib/apt/periodic/provision-update
    if [[ -f $stamp ]] && [[ -n $(find "$stamp" -mmin -60) ]]; then
        return 0
    fi
    DEBIAN_FRONTEND=noninteractive apt-get update
    install -D -m 0644 /dev/null "$stamp"
}

apt_install() {
    local pkg missing=()
    for pkg in "$@"; do installed "$pkg" || missing+=("$pkg"); done
    ((${#missing[@]})) || return 0
    log "installing: ${missing[*]}"
    DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}"
}

apt_purge() {
    local pkg present=()
    for pkg in "$@"; do
        if installed "$pkg"; then present+=("$pkg"); fi
    done
    ((${#present[@]})) || return 0
    log "purging: ${present[*]}"
    DEBIAN_FRONTEND=noninteractive apt-get purge -y "${present[@]}"
}
