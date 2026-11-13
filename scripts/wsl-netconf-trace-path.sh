#!/usr/bin/env bash
set -euo pipefail

log_dir="$1"
session_name="$2"
shared_path="$log_dir/netconf-trace.log"

if [[ "$session_name" != netconf-trace-*.log || "$session_name" == */* || ! -f "$log_dir/$session_name" ]]; then
  echo "Invalid NETCONF session trace filename: $session_name" >&2
  exit 1
fi

temporary_link="$(mktemp -u "$log_dir/.netconf-trace-link-XXXXXXXX")"
ln -- "$log_dir/$session_name" "$temporary_link"
trap 'rm -f -- "$temporary_link"' EXIT

archive=""
if [[ -e "$shared_path" && ! -L "$shared_path" ]]; then
  existing_session="$(find "$log_dir" -maxdepth 1 -name 'netconf-trace-*.log' -samefile "$shared_path" -print -quit)"
  if [[ -z "$existing_session" ]]; then
    archive="$(mktemp "$log_dir/netconf-trace-shared-XXXXXXXX.log")"
    if ! mv -f -- "$shared_path" "$archive"; then
      rm -f -- "$archive"
      exit 1
    fi
  fi
fi

if ! mv -fT -- "$temporary_link" "$shared_path"; then
  if [[ -n "$archive" ]]; then
    mv -f -- "$archive" "$shared_path"
  fi
  exit 1
fi

if [[ -n "$archive" ]]; then
  printf 'Archived previous shared NETCONF trace: %s\n' "$archive"
fi