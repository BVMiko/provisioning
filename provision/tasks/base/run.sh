#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"

want=${PROVISION_VAR_TIMEZONE:?vars.toml must set timezone}

current=$(timedatectl show -p Timezone --value 2>/dev/null) || {
    log "timedatectl unavailable; leaving timezone alone"
    exit 0
}

if [[ $current != "$want" ]]; then
    log "timezone -> $want"
    timedatectl set-timezone "$want"
fi
