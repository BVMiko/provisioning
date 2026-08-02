#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"

# netplan merges /usr/lib, /etc and /run together in filename order regardless of
# directory, so the renderer depends on how the installer happened to name its
# file. The 99- prefix settles it.
installed network-manager \
    || die "NetworkManager absent; netplan would render to a missing backend"

netplan generate

if [[ -n ${PROVISION_CHANGED:-} ]]; then
    log "renderer is now NetworkManager; reboot to hand over from networkd"
fi
