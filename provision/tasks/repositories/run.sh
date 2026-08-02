#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../lib.sh"

if [[ -n ${PROVISION_CHANGED:-} ]]; then
    DEBIAN_FRONTEND=noninteractive apt-get update
fi
