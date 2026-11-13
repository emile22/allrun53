#!/usr/bin/env bash
set -euo pipefail

sysrepo_repository=/var/lib/grmis/allrun53/sysrepo
if [[ ! -d "$sysrepo_repository" ]]; then
  echo "allrun53 Sysrepo repository is not provisioned; status check made no changes."
  exit 0
fi
export SYSREPO_REPOSITORY_PATH="$sysrepo_repository"
export SYSREPO_SHM_PREFIX=gr53

source /etc/os-release
printf 'WSL distribution: %s\n' "$PRETTY_NAME"
printf 'libyang: %s\n' "$(pkg-config --modversion libyang 2>/dev/null || echo unavailable)"
printf 'Sysrepo: %s\n' "$(pkg-config --modversion sysrepo 2>/dev/null || echo unavailable)"
printf 'Netopeer2: %s\n' "$(dpkg-query -W -f='${Version}' netopeer2 2>/dev/null || echo unavailable)"

for service in sysrepo-plugind.service netopeer2.service; do
  if systemctl is-active --quiet "$service"; then
    printf '%s: running\n' "$service"
  else
    printf '%s: stopped\n' "$service"
  fi
done
sysrepoctl -l | grep -E '^(ietf-power-and-energy|iana-power-and-energy|ietf-hardware|iana-hardware|ietf-inet-types|ietf-yang-types)[[:space:]]' || true
ss -ltn | awk '$4 ~ /:830$/ { print "NETCONF listener: " $4 }'
printf 'WSL address fallback: %s\n' "$(hostname -I | awk '{print $1}')"
printf 'Active Sysrepo repository: %s\n' "$(systemctl show-environment | sed -n 's/^SYSREPO_REPOSITORY_PATH=//p' | head -n 1)"