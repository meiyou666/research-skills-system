#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  fetch_results.sh --host HOST --user USER [--port PORT]
    --known-hosts FILE [--password-file FILE] [--identity-file FILE]
    --remote-root DIR --remote-manifest FILE
    --execution-record FILE --destination DIR
EOF
  exit 2
}

host=
user=
port=22
known_hosts=
password_file=
identity_file=
remote_root=
remote_manifest=
execution_record=
destination=

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) [[ $# -ge 2 ]] || usage; host=$2; shift 2 ;;
    --user) [[ $# -ge 2 ]] || usage; user=$2; shift 2 ;;
    --port) [[ $# -ge 2 ]] || usage; port=$2; shift 2 ;;
    --known-hosts) [[ $# -ge 2 ]] || usage; known_hosts=$2; shift 2 ;;
    --password-file) [[ $# -ge 2 ]] || usage; password_file=$2; shift 2 ;;
    --identity-file) [[ $# -ge 2 ]] || usage; identity_file=$2; shift 2 ;;
    --remote-root) [[ $# -ge 2 ]] || usage; remote_root=$2; shift 2 ;;
    --remote-manifest) [[ $# -ge 2 ]] || usage; remote_manifest=$2; shift 2 ;;
    --execution-record) [[ $# -ge 2 ]] || usage; execution_record=$2; shift 2 ;;
    --destination) [[ $# -ge 2 ]] || usage; destination=$2; shift 2 ;;
    *) usage ;;
  esac
done

[[ -n $host && -n $user && -n $known_hosts && -n $remote_root && -n $remote_manifest && -n $execution_record && -n $destination ]] || usage
[[ -f $execution_record && ! -L $execution_record ]] || { echo "execution record must be a regular local file" >&2; exit 2; }

valid_remote_path() {
  local value=$1 trimmed segment
  local -a parts
  [[ $value == /* && $value != / && $value != */ ]] || return 1
  trimmed=${value#/}
  IFS=/ read -r -a parts <<< "$trimmed"
  for segment in "${parts[@]}"; do
    [[ -n $segment && $segment != . && $segment != .. && $segment =~ ^[A-Za-z0-9._-]+$ ]] || return 1
  done
}

valid_remote_path "$remote_root" || { echo "remote root is not a normalized absolute path" >&2; exit 2; }
valid_remote_path "$remote_manifest" || { echo "remote manifest is not a normalized absolute path" >&2; exit 2; }
command -v tar >/dev/null 2>&1 || { echo "local tar is required" >&2; exit 127; }
command -v python3 >/dev/null 2>&1 || { echo "local Python 3 is required" >&2; exit 127; }
mv --help 2>&1 | grep -q -- '-T' && mv --help 2>&1 | grep -q -- '-n' || {
  echo "GNU mv with -T and -n support is required" >&2
  exit 127
}

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
ssh_helper="$script_dir/ssh_session.sh"
verifier="$script_dir/verify_result_manifest.py"
[[ -x $ssh_helper && -f $verifier ]] || { echo "skill scripts are incomplete" >&2; exit 127; }

parent_input=$(dirname -- "$destination")
base=$(basename -- "$destination")
[[ $base != . && $base != .. && -n $base ]] || { echo "invalid destination" >&2; exit 2; }
mkdir -p -- "$parent_input"
parent=$(cd -- "$parent_input" && pwd -P)
destination="$parent/$base"
[[ ! -e $destination ]] || { echo "destination already exists: $destination" >&2; exit 3; }

staging=$(mktemp -d "$parent/.${base}.partial.XXXXXX")
cleanup() {
  if [[ -n ${staging:-} && -d $staging && $staging == "$parent/.${base}.partial."* ]]; then
    rm -rf -- "$staging"
  fi
}
trap cleanup EXIT
mkdir -p -- "$staging/raw"
cp -- "$execution_record" "$staging/execution-record.json"

connection=(--host "$host" --user "$user" --port "$port" --known-hosts "$known_hosts")
[[ -n $password_file ]] && connection+=(--password-file "$password_file")
[[ -n $identity_file ]] && connection+=(--identity-file "$identity_file")

"$ssh_helper" run "${connection[@]}" -- "cat -- '$remote_manifest'" > "$staging/result-manifest.json"

"$ssh_helper" run "${connection[@]}" -- "tar -C '$remote_root' -cf - ." |
  tar -C "$staging/raw" --no-same-owner --no-same-permissions -xf -

python3 "$verifier" \
  --root "$staging/raw" \
  --manifest "$staging/result-manifest.json" \
  --execution-record "$staging/execution-record.json" \
  --report "$staging/verification.json"

mv -Tn -- "$staging" "$destination"
[[ ! -e $staging ]] || { echo "destination appeared during finalization: $destination" >&2; exit 3; }
trap - EXIT
printf 'VERIFIED destination=%s\n' "$destination"
