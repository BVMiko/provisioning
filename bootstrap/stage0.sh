#!/bin/sh
# Stage 0: fetch the repository, record roles, hand off to the provisioner.
set -eu

REPO="${PROVISION_REPO:-https://github.com/BVMiko/provisioning.git}"
REF="${PROVISION_REF:-master}"
DEST="${PROVISION_DEST:-/opt/provision}"
STATE=/var/lib/provision
UNIT=/etc/systemd/system/provision-firstboot.service

log() { printf '[stage0] %s\n' "$*" >&2; }
die() { printf '[stage0] ERROR: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "must run as root"

mode=run
case "${1:-}" in
    --boot) mode=boot; shift ;;
    --run) mode=run; shift ;;
    "") mode=run ;;
    *) die "unknown argument: $1" ;;
esac

install_deps() {
    missing=
    for pkg in ca-certificates curl git python3 python3-jinja2; do
        dpkg-query -W -f='${db:Status-Abbrev}' "$pkg" 2>/dev/null | grep -q '^ii' \
            || missing="$missing $pkg"
    done
    [ -n "$missing" ] || return 0
    log "installing:$missing"
    DEBIAN_FRONTEND=noninteractive apt-get update
    # shellcheck disable=SC2086
    DEBIAN_FRONTEND=noninteractive apt-get install -y $missing
}

sync_repo() {
    if [ -d "$DEST/.git" ]; then
        git -C "$DEST" fetch --depth=1 origin "$REF"
        git -C "$DEST" checkout -q FETCH_HEAD
    else
        rm -rf "$DEST"
        git clone --depth=1 --branch "$REF" "$REPO" "$DEST"
    fi
    log "repository at $(git -C "$DEST" rev-parse --short HEAD)"
}

record_roles() {
    [ -n "${PROVISION_ROLES:-}" ] || return 0
    mkdir -p /etc/provision
    printf '%s\n' "$PROVISION_ROLES" | tr ' ,' '\n\n' | grep -v '^$' \
        > /etc/provision/roles
    log "roles: $(tr '\n' ' ' < /etc/provision/roles)"
}

install_unit() {
    cat > "$UNIT" <<EOF
[Unit]
Description=First-boot provisioning
Wants=network-online.target
After=network-online.target
ConditionPathExists=!$STATE/complete

[Service]
Type=oneshot
RemainAfterExit=yes
TimeoutStartSec=0
ExecStart=$DEST/bootstrap/stage0.sh --run

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable provision-firstboot.service
}

install_deps
sync_repo
record_roles

if [ "$mode" = boot ]; then
    install_unit
    # Detached so cloud-init's first boot is not blocked by the full run.
    systemctl start --no-block provision-firstboot.service
    log "provisioning started; follow with: journalctl -fu provision-firstboot"
    exit 0
fi

mkdir -p "$STATE"
"$DEST/provision/provision" "$@"
touch "$STATE/complete"
