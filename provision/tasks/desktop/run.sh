#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"

PPA_URI=https://ppa.launchpadcontent.net/mozillateam/ppa/ubuntu

debconf-set-selections <<'EOF'
ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula boolean true
ttf-mscorefonts-installer msttcorefonts/present-mscorefonts-eula note
EOF

apt_update_if_stale

# ubuntu-desktop Recommends snapd, firefox and thunderbird, all of which the
# snap task pins. The firefox and thunderbird recommendations resolve to the
# mozillateam PPA's debs instead of being dropped.
apt_install ubuntu-desktop ubuntu-restricted-extras firefox thunderbird

systemctl set-default graphical.target

if [[ $(dpkg-query -W -f='${Version}' snapd 2>/dev/null || true) != 99:* ]]; then
    die "real snapd is installed; check apt-cache policy snapd"
fi

for pkg in firefox thunderbird; do
    origin=$(apt-cache policy "$pkg" | awk '/\*\*\*/ {f=1} f && /http/ {print $2; exit}')
    [[ $origin == "$PPA_URI"* ]] \
        || die "$pkg came from ${origin:-nowhere}, expected the mozillateam PPA"
    log "$pkg origin: $origin"
done
