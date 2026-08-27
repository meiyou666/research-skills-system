#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  ssh_session.sh config|probe|shell|run|upload --host HOST --user USER
    [--port PORT] --known-hosts FILE [--password-file FILE]
    [--identity-file FILE] [--connect-timeout SECONDS]
    [--source LOCAL_FILE --destination REMOTE_FILE [--mode OCTAL]]
    [-- COMMAND]
EOF
  exit 2
}

[[ $# -ge 1 ]] || usage
action=$1
shift

host=
user=
port=22
known_hosts=
password_file=
identity_file=
connect_timeout=15
remote_command=()
local_source=
remote_destination=
remote_mode=600

need_value() {
  [[ $# -ge 2 && -n ${2:-} ]] || usage
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) need_value "$@"; host=$2; shift 2 ;;
    --user) need_value "$@"; user=$2; shift 2 ;;
    --port) need_value "$@"; port=$2; shift 2 ;;
    --known-hosts) need_value "$@"; known_hosts=$2; shift 2 ;;
    --password-file) need_value "$@"; password_file=$2; shift 2 ;;
    --identity-file) need_value "$@"; identity_file=$2; shift 2 ;;
    --connect-timeout) need_value "$@"; connect_timeout=$2; shift 2 ;;
    --source) need_value "$@"; local_source=$2; shift 2 ;;
    --destination) need_value "$@"; remote_destination=$2; shift 2 ;;
    --mode) need_value "$@"; remote_mode=$2; shift 2 ;;
    --) shift; remote_command=("$@"); break ;;
    *) usage ;;
  esac
done

[[ -n $host && -n $user && -n $known_hosts ]] || usage
[[ -n $host && $host != -* && $host != *' '* && $host != *$'\t'* && $host != *$'\r'* && $host != *$'\n'* ]] || { echo "invalid SSH host" >&2; exit 2; }
[[ $user =~ ^[A-Za-z0-9_][A-Za-z0-9._-]*$ ]] || { echo "invalid SSH user" >&2; exit 2; }
[[ $port =~ ^[0-9]+$ ]] && (( port >= 1 && port <= 65535 )) || {
  echo "invalid SSH port: $port" >&2
  exit 2
}
[[ $connect_timeout =~ ^[0-9]+$ ]] && (( connect_timeout >= 1 )) || {
  echo "invalid connect timeout: $connect_timeout" >&2
  exit 2
}
command -v ssh >/dev/null 2>&1 || { echo "OpenSSH client is required" >&2; exit 127; }
command -v ssh-keygen >/dev/null 2>&1 || { echo "OpenSSH ssh-keygen is required" >&2; exit 127; }

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

umask 077
mkdir -p -- "$(dirname -- "$known_hosts")"
touch -- "$known_hosts"
chmod 600 -- "$known_hosts"

host_key_alias="[$host]:$port"
strict=accept-new
if ssh-keygen -F "$host_key_alias" -f "$known_hosts" >/dev/null 2>&1; then
  strict=yes
fi

ssh_options=(
  -F /dev/null
  -p "$port"
  -o "HostName=$host"
  -o "User=$user"
  -o "UserKnownHostsFile=$known_hosts"
  -o GlobalKnownHostsFile=/dev/null
  -o "StrictHostKeyChecking=$strict"
  -o "ConnectTimeout=$connect_timeout"
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=3
  -o CanonicalizeHostname=no
  -o "HostKeyAlias=$host_key_alias"
  -o UpdateHostKeys=no
  -o VerifyHostKeyDNS=no
  -o ForwardAgent=no
  -o ForwardX11=no
  -o ClearAllForwardings=yes
  -o ControlMaster=no
  -o ControlPath=none
  -o PermitLocalCommand=no
  -o BatchMode=no
  -o PasswordAuthentication=yes
  -o KbdInteractiveAuthentication=yes
)

if [[ -n $password_file ]]; then
  [[ -r $password_file ]] || { echo "password file is not readable" >&2; exit 2; }
  mode=$(stat -c '%a' -- "$password_file" 2>/dev/null || stat -f '%Lp' -- "$password_file" 2>/dev/null || true)
  [[ $mode =~ ^[0-7]{3,4}$ ]] || { echo "cannot verify password-file permissions" >&2; exit 2; }
  mode_value=$((8#$mode))
  (( (mode_value & 077) == 0 )) || { echo "password file must not be accessible by group or others" >&2; exit 2; }
  command -v sshpass >/dev/null 2>&1 || { echo "sshpass is required for --password-file" >&2; exit 127; }
  ssh_options+=( -o PreferredAuthentications=keyboard-interactive,password )
  ssh_options+=( -o NumberOfPasswordPrompts=1 )
  auth_prefix=(sshpass -f "$password_file")
else
  ssh_options+=( -o PreferredAuthentications=publickey,keyboard-interactive,password )
  auth_prefix=()
fi

if [[ -n $identity_file ]]; then
  [[ -r $identity_file ]] || { echo "identity file is not readable" >&2; exit 2; }
  ssh_options+=( -i "$identity_file" -o IdentitiesOnly=yes )
fi

ssh_options+=( -o ProxyCommand=none -o ProxyJump=none )

target=$host

case "$action" in
  config)
    ssh -G "${ssh_options[@]}" "$target" 2>/dev/null |
      awk '$1 ~ /^(hostname|hostkeyalias|user|port|batchmode|preferredauthentications|passwordauthentication|kbdinteractiveauthentication|proxycommand|proxyjump|userknownhostsfile|globalknownhostsfile|stricthostkeychecking)$/ {print}'
    printf 'connectionroute direct\n'
    if [[ $strict == accept-new ]]; then
      printf 'hostkeymode accept-new\n'
    else
      printf 'hostkeymode pinned\n'
    fi
    ;;
  probe)
    "${auth_prefix[@]}" ssh "${ssh_options[@]}" "$target" 'printf "SSH_OK\n"'
    ;;
  shell)
    "${auth_prefix[@]}" ssh "${ssh_options[@]}" "$target"
    ;;
  run)
    [[ ${#remote_command[@]} -gt 0 ]] || { echo "run requires a command after --" >&2; exit 2; }
    "${auth_prefix[@]}" ssh "${ssh_options[@]}" "$target" "${remote_command[@]}"
    ;;
  upload)
    [[ -f $local_source && ! -L $local_source ]] || { echo "upload source must be a regular local file" >&2; exit 2; }
    valid_remote_path "$remote_destination" || {
      echo "upload destination must be a normalized absolute path using letters, digits, dot, underscore, slash, or hyphen" >&2
      exit 2
    }
    [[ $remote_mode =~ ^[0-7]{3,4}$ ]] || { echo "invalid upload mode" >&2; exit 2; }
    remote_parent=$(dirname -- "$remote_destination")
    remote_upload_command="set -e; umask 077; mkdir -p -- '$remote_parent'; cat > '$remote_destination'; chmod '$remote_mode' '$remote_destination'"
    "${auth_prefix[@]}" ssh "${ssh_options[@]}" "$target" "$remote_upload_command" < "$local_source"
    ;;
  *) usage ;;
esac
