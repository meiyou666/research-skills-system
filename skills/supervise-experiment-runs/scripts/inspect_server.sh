#!/usr/bin/env bash
set -u

section() { printf '\n[%s]\n' "$1"; }
command_path() {
  if command -v "$1" >/dev/null 2>&1; then
    printf '%s=%s\n' "$1" "$(command -v "$1")"
  else
    printf '%s=missing\n' "$1"
  fi
}

printf 'inspection_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date)"
printf 'hostname=%s\n' "$(hostname 2>/dev/null || printf unknown)"
printf 'user=%s\n' "$(id -un 2>/dev/null || printf unknown)"
printf 'uid_gid=%s\n' "$(id 2>/dev/null || printf unknown)"

section system
uname -a 2>&1 || true
if [[ -r /etc/os-release ]]; then
  grep -E '^(ID|VERSION_ID|PRETTY_NAME)=' /etc/os-release || true
fi
printf 'shell=%s\n' "${SHELL:-unknown}"
printf 'container=%s\n' "$(if [[ -f /.dockerenv ]]; then printf docker; elif grep -qaE '(docker|containerd|kubepods|podman)' /proc/1/cgroup 2>/dev/null; then printf cgroup-container; else printf host-or-unknown; fi)"

section cpu
command -v nproc >/dev/null 2>&1 && printf 'nproc=%s\n' "$(nproc)"
command -v lscpu >/dev/null 2>&1 && lscpu || true
if [[ -r /sys/fs/cgroup/cpu.max ]]; then
  printf 'cgroup_v2_cpu_max=%s\n' "$(tr '\n' ' ' < /sys/fs/cgroup/cpu.max)"
elif [[ -r /sys/fs/cgroup/cpu/cpu.cfs_quota_us ]]; then
  printf 'cgroup_v1_cpu_quota_us=%s\n' "$(cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us)"
  printf 'cgroup_v1_cpu_period_us=%s\n' "$(cat /sys/fs/cgroup/cpu/cpu.cfs_period_us 2>/dev/null || printf unknown)"
fi

section memory
command -v free >/dev/null 2>&1 && free -b || true
if [[ -r /sys/fs/cgroup/memory.max ]]; then
  printf 'cgroup_v2_memory_max=%s\n' "$(cat /sys/fs/cgroup/memory.max)"
elif [[ -r /sys/fs/cgroup/memory/memory.limit_in_bytes ]]; then
  printf 'cgroup_v1_memory_limit_bytes=%s\n' "$(cat /sys/fs/cgroup/memory/memory.limit_in_bytes)"
fi

section storage
df -PT 2>&1 || df -P 2>&1 || true
command -v lsblk >/dev/null 2>&1 && lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS 2>&1 || true
command -v findmnt >/dev/null 2>&1 && findmnt -rn -o TARGET,SOURCE,FSTYPE,OPTIONS 2>&1 || true

section gpu
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,name,uuid,driver_version,memory.total,compute_mode --format=csv,noheader 2>&1 || nvidia-smi 2>&1 || true
else
  printf 'nvidia_smi=missing\n'
fi
command -v nvcc >/dev/null 2>&1 && nvcc --version 2>&1 || printf 'nvcc=missing\n'

section tools
for tool in bash sh env sudo apt-get dnf yum apk git curl wget rsync scp tar sha256sum stat setsid timeout nohup python3 pip3 gcc g++ clang cmake ninja docker podman; do
  command_path "$tool"
done
python3 --version 2>&1 || true
git --version 2>&1 || true

section network_configuration
for variable in HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy; do
  if [[ -n ${!variable:-} ]]; then
    printf '%s=set\n' "$variable"
  else
    printf '%s=unset\n' "$variable"
  fi
done
