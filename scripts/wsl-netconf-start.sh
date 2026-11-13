#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
plugin_dir="$project_dir/netconf/plugins"
state_file="$project_dir/runtime/operational.json"
trace_file="$project_dir/logs/netconf-trace.log"
sysrepo_repository="/var/lib/grmis/allrun53/sysrepo"
sysrepo_shm_prefix=gr53
mkdir -p "$(dirname -- "$state_file")" "$(dirname -- "$trace_file")"

active_repository="$(systemctl show-environment | sed -n 's/^SYSREPO_REPOSITORY_PATH=//p')"
services_active=0
if systemctl is-active --quiet netopeer2.service || systemctl is-active --quiet sysrepo-plugind.service; then
  services_active=1
fi
port_occupied=0
if ss -ltn | awk '$4 ~ /:830$/ { found=1 } END { exit !found }'; then
  port_occupied=1
fi
if (( services_active || port_occupied )) && [[ "$active_repository" != "$sysrepo_repository" ]]; then
  echo "Refusing to replace another active NETCONF stack (repository: ${active_repository:-unknown}, TCP/830 occupied: $port_occupied)." >&2
  exit 2
fi

systemctl stop netopeer2.service sysrepo-plugind.service
"$project_dir/scripts/wsl-netconf-install.sh"
"$project_dir/scripts/wsl-netconf-build-plugin.sh"

systemctl set-environment \
  "SYSREPO_REPOSITORY_PATH=$sysrepo_repository" \
  "SYSREPO_SHM_PREFIX=$sysrepo_shm_prefix" \
  "SRPD_PLUGINS_PATH=$plugin_dir" \
  "GREEN_NETCONF_STATE_FILE=$state_file" \
  "GREEN_NETCONF_TRACE_FILE=$trace_file"
service_environment="SYSREPO_REPOSITORY_PATH SYSREPO_SHM_PREFIX SRPD_PLUGINS_PATH GREEN_NETCONF_STATE_FILE GREEN_NETCONF_TRACE_FILE"
for service in sysrepo-plugind.service netopeer2.service; do
  drop_in_dir="/etc/systemd/system/$service.d"
  install -d -o root -g root -m 0755 "$drop_in_dir"
  printf '[Service]\nPassEnvironment=%s\n' "$service_environment" > "$drop_in_dir/50-grmis-allrun53-netconf-environment.conf"
done
systemctl daemon-reload
systemctl restart sysrepo-plugind.service
systemctl restart netopeer2.service

for attempt in $(seq 1 15); do
  if ss -ltn | awk '$4 ~ /:830$/ { found=1 } END { exit !found }'; then
    echo "Netopeer2 is listening on TCP port 830"
    exit 0
  fi
  sleep 1
done

echo "Netopeer2 did not open TCP port 830." >&2
exit 1