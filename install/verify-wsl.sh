#!/usr/bin/env bash
set -euo pipefail

expected_repository=/var/lib/grmis/allrun53/sysrepo
printf 'Distribution: %s\n' "$(. /etc/os-release && printf '%s' "$PRETTY_NAME")"
printf 'Python: %s\n' "$(python3 --version 2>&1)"
printf 'Sysrepo: %s\n' "$(pkg-config --modversion sysrepo 2>/dev/null || echo unavailable)"
printf 'libyang: %s\n' "$(pkg-config --modversion libyang 2>/dev/null || echo unavailable)"
printf 'libnetconf2: %s\n' "$(dpkg-query -W -f='${Version}' libnetconf2-2 2>/dev/null || echo unavailable)"
printf 'Netopeer2: %s\n' "$(dpkg-query -W -f='${Version}' netopeer2 2>/dev/null || echo unavailable)"
printf 'sysrepo-plugind: %s\n' "$(systemctl is-active sysrepo-plugind.service 2>/dev/null || echo inactive)"
printf 'netopeer2 service: %s\n' "$(systemctl is-active netopeer2.service 2>/dev/null || echo inactive)"
active_repository="$(systemctl show-environment 2>/dev/null | sed -n 's/^SYSREPO_REPOSITORY_PATH=//p')"
printf 'Active service repository: %s\n' "${active_repository:-unknown}"
if [[ ! -d "$expected_repository" ]]; then
  echo "allrun53 repository is not provisioned; verifier made no changes."
  exit 0
fi
SYSREPO_REPOSITORY_PATH="$expected_repository" SYSREPO_SHM_PREFIX=gr53 sysrepoctl -l
