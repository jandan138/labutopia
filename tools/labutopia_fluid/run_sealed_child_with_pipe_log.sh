#!/usr/bin/env bash
set -uo pipefail

if [[ $# -lt 4 || "$1" != "--log" || "$3" != "--" ]]; then
    printf 'usage: %s --log /tmp/<name>.log -- <command> [args...]\n' "$0" >&2
    exit 64
fi

log_path=$2
shift 3

if [[ "$(dirname -- "$log_path")" != "/tmp" || -e "$log_path" || -L "$log_path" ]]; then
    printf 'invalid pipe log path: %s\n' "$log_path" >&2
    exit 64
fi

umask 077
set -o noclobber
if ! exec {log_fd}> "$log_path"; then
    set +o noclobber
    printf 'pipe log exclusive create failed: %s\n' "$log_path" >&2
    exit 64
fi
set +o noclobber

"$@" 2>&1 | (trap '' XFSZ; exec /usr/bin/tee) >&"$log_fd"
pipeline_status=("${PIPESTATUS[@]}")
child_status=${pipeline_status[0]}
tee_status=${pipeline_status[1]}
exec {log_fd}>&-

if (( tee_status != 0 )); then
    exit 74
fi
if (( child_status != 0 )); then
    exit "$child_status"
fi
exit 0
