#!/usr/bin/env bash
set -euo pipefail

sysrepo_repository="/var/lib/grmis/allrun53/sysrepo"
if systemctl show-environment | grep -Fxq "SYSREPO_REPOSITORY_PATH=$sysrepo_repository"; then
	systemctl stop netopeer2.service sysrepo-plugind.service
	active_services=()
	for service in netopeer2.service sysrepo-plugind.service; do
		if systemctl is-active --quiet "$service"; then
			active_services+=("$service")
		fi
	done
	if ((${#active_services[@]})); then
		printf 'Could not stop allrun53 NETCONF services; still active: %s. Repository environment retained.\n' "${active_services[*]}" >&2
		exit 1
	fi
	systemctl unset-environment SYSREPO_REPOSITORY_PATH SYSREPO_SHM_PREFIX SRPD_PLUGINS_PATH GREEN_NETCONF_STATE_FILE GREEN_NETCONF_TRACE_FILE
	echo "Stopped the allrun53 NETCONF services."
else
	echo "Skipped stopping NETCONF services; allrun53 is not the active Sysrepo repository."
fi