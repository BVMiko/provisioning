#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"

# Epoch 99 outranks any archive version, so apt never treats the real package as
# an upgrade even if the pin is lost.
STUB_VERSION='99:1'

# ubuntu-server-minimal, ubuntu-cloud-minimal, firefox and thunderbird declare
# snapd as a Depends. A stub package named snapd satisfies that edge, so nothing
# has to be removed and the metapackages keep tracking base packages across
# release upgrades.
build_stub() {
    local dir=$1
    mkdir -p "$dir/pkg/DEBIAN"
    cat > "$dir/pkg/DEBIAN/control" <<EOF
Package: snapd
Version: $STUB_VERSION
Architecture: all
Maintainer: provisioning <root@localhost>
Section: admin
Priority: optional
Description: Stub satisfying dependencies on snapd
 Occupies the snapd package name so that packages depending on snapd install
 without pulling the snap runtime. Ships no files and runs no services.
EOF
    dpkg-deb --build --root-owner-group "$dir/pkg" "$dir/snapd.deb" >/dev/null
}

if [[ $(dpkg-query -W -f='${Version}' snapd 2>/dev/null || true) != "$STUB_VERSION" ]]; then
    for unit in snapd.service snapd.socket snapd.seeded.service \
                snapd.apparmor.service snapd.snap-repair.timer; do
        systemctl disable --now "$unit" 2>/dev/null || true
    done

    while read -r mount; do
        log "unmounting $mount"
        umount -l "$mount" || true
    done < <(awk '$2 ~ /^\/(var\/)?snap\// {print $2}' /proc/mounts | sort -r)

    work=$(mktemp -d)
    build_stub "$work"
    log "installing snapd stub $STUB_VERSION"
    DEBIAN_FRONTEND=noninteractive dpkg -i "$work/snapd.deb"
    rm -rf "$work"
fi

apt-mark hold snapd >/dev/null

# Depend on snapd, so the stub would otherwise let them install.
apt_purge snapd-seed-glue snapd-installation-monitor \
          gnome-software-plugin-snap fwupd-snap snapd-desktop-integration

# snapd's conffiles survive being replaced by the stub: an APT hook, a PATH
# entry adding /snap/bin, a session autostart entry, and an AppArmor profile.
for conf in /etc/apt/apt.conf.d/20snapd.conf \
            /etc/profile.d/apps-bin-path.sh \
            /etc/xdg/autostart/snap-userd-autostart.desktop \
            /etc/apparmor.d/usr.lib.snapd.snap-confine.real; do
    [[ -e $conf ]] || continue
    log "removing $conf"
    rm -f "$conf"
done

for dir in /snap /var/snap /var/lib/snapd /var/cache/snapd /root/snap /home/*/snap; do
    [[ -e $dir ]] || continue
    log "removing $dir"
    rm -rf "$dir"
done
