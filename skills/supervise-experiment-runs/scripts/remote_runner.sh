#!/usr/bin/env bash
set -euo pipefail
umask 077

usage() {
  cat >&2 <<'EOF'
Usage:
  remote_runner.sh preflight
  remote_runner.sh start --run-id ID --run-dir DIR --work-dir DIR --launch-script FILE
    --validation-script FILE --expected-launch-sha256 HEX
    --expected-validation-sha256 HEX --maximum-runtime-seconds N
    --validation-timeout-seconds N --progress-file FILE
    --no-progress-seconds N [--heartbeat-seconds N]
    [--telemetry-sampler FILE --telemetry-config FILE
     --expected-telemetry-sampler-sha256 HEX
     --expected-telemetry-config-sha256 HEX --telemetry-output FILE]
  remote_runner.sh status --run-dir DIR
EOF
  exit 2
}

atomic_text() {
  local path=$1 value=$2 tmp
  tmp="${path}.tmp.$$.$RANDOM"
  printf '%s\n' "$value" > "$tmp"
  mv -f -- "$tmp" "$path"
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -- "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 -- "$1" | awk '{print $1}'
  else
    echo "sha256sum or shasum is required" >&2
    return 127
  fi
}

check_runtime_dependencies() {
  command -v setsid >/dev/null 2>&1 || { echo "setsid is required" >&2; return 127; }
  command -v timeout >/dev/null 2>&1 || { echo "timeout is required" >&2; return 127; }
  command -v stat >/dev/null 2>&1 || { echo "GNU stat is required" >&2; return 127; }
  command -v nohup >/dev/null 2>&1 || { echo "nohup is required" >&2; return 127; }
  command -v python3 >/dev/null 2>&1 || { echo "Python 3 is required" >&2; return 127; }
  if ! command -v sha256sum >/dev/null 2>&1 && ! command -v shasum >/dev/null 2>&1; then
    echo "sha256sum or shasum is required" >&2
    return 127
  fi
  setsid --fork --wait true >/dev/null 2>&1 || {
    echo "setsid with --fork and --wait support is required" >&2
    return 127
  }
}

runner_preflight() {
  check_runtime_dependencies
  python3 - <<'PY'
import ctypes
import os
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 or newer is required")
if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
    error = ctypes.get_errno()
    raise SystemExit(f"child subreaper is unavailable: {os.strerror(error)}")
Path(f"/proc/{os.getpid()}/task/{os.getpid()}/children").read_text(encoding="ascii")
PY
  printf 'PREFLIGHT_OK\n'
}

process_start_ticks() {
  local pid=$1 stat_line remainder
  [[ -r /proc/$pid/stat ]] || return 1
  stat_line=$(cat "/proc/$pid/stat")
  remainder=${stat_line##*) }
  awk '{print $20}' <<< "$remainder"
}

process_is_active() {
  local pid=$1 stat_line remainder state
  [[ -r /proc/$pid/stat ]] || return 1
  stat_line=$(cat "/proc/$pid/stat")
  remainder=${stat_line##*) }
  state=${remainder%% *}
  [[ $state != Z && $state != X ]]
}

write_process_tree_supervisor() {
  local path=$1
  cat > "$path" <<'PY'
#!/usr/bin/env python3
import ctypes
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


PR_SET_CHILD_SUBREAPER = 36
RESIDUAL_EXIT = 125
SETUP_EXIT = 126
stop_signal = 0


def active(pid: int) -> bool:
    try:
        raw = Path(f"/proc/{pid}/stat").read_bytes()
        state = raw[raw.rfind(b") ") + 2 :].split()[0]
        return state not in {b"Z", b"X"}
    except (FileNotFoundError, PermissionError, IndexError):
        return False


def children(pid: int) -> list[int]:
    try:
        value = Path(f"/proc/{pid}/task/{pid}/children").read_text(encoding="ascii").strip()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return []
    return [int(item) for item in value.split()] if value else []


def descendants() -> list[int]:
    found: set[int] = set()
    pending = children(os.getpid())
    while pending:
        pid = pending.pop()
        if pid in found:
            continue
        found.add(pid)
        pending.extend(children(pid))
    return sorted(pid for pid in found if active(pid))


def reap() -> None:
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def signal_processes(pids: list[int], signum: int) -> None:
    own_group = os.getpgrp()
    groups: set[int] = set()
    for pid in pids:
        try:
            group = os.getpgid(pid)
            if group != own_group:
                groups.add(group)
        except ProcessLookupError:
            pass
    for group in groups:
        try:
            os.killpg(group, signum)
        except ProcessLookupError:
            pass
    for pid in pids:
        try:
            os.kill(pid, signum)
        except ProcessLookupError:
            pass


def terminate_descendants(grace_seconds: float = 3.0) -> list[int]:
    initial = descendants()
    signal_processes(initial, signal.SIGTERM)
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        reap()
        remaining = descendants()
        if not remaining:
            return initial
        signal_processes(remaining, signal.SIGTERM)
        time.sleep(0.05)
    remaining = descendants()
    signal_processes(remaining, signal.SIGKILL)
    kill_deadline = time.monotonic() + 1.0
    while time.monotonic() < kill_deadline:
        reap()
        if not descendants():
            break
        time.sleep(0.05)
    return sorted(set(initial) | set(remaining))


def write_residual(path: Path, pids: list[int]) -> None:
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    temporary.write_text(",".join(str(pid) for pid in pids) + "\n", encoding="ascii")
    os.replace(temporary, path)


def handle_signal(signum: int, _frame: object) -> None:
    global stop_signal
    stop_signal = signum


def main() -> int:
    if len(sys.argv) != 4:
        return SETUP_EXIT
    maximum_runtime = int(sys.argv[1])
    launch_script = sys.argv[2]
    residual_file = Path(sys.argv[3])

    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        print(f"failed to enable child subreaper: {os.strerror(error)}", file=sys.stderr)
        return SETUP_EXIT

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    child = subprocess.Popen(["bash", launch_script], start_new_session=True)
    deadline = time.monotonic() + maximum_runtime
    timed_out = False

    while child.poll() is None:
        if stop_signal:
            break
        if time.monotonic() >= deadline:
            timed_out = True
            break
        time.sleep(0.05)

    if stop_signal or timed_out:
        terminate_descendants()
        try:
            child.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            pass
        if timed_out:
            return 124
        return 128 + stop_signal

    return_code = child.returncode
    reap()
    remaining = descendants()
    if remaining:
        terminated = terminate_descendants()
        write_residual(residual_file, sorted(set(remaining) | set(terminated)))
        print("launch exited while descendant processes remained; residual work was terminated", file=sys.stderr)
        return RESIDUAL_EXIT

    if return_code is None:
        return SETUP_EXIT
    if return_code < 0:
        return 128 - return_code
    return return_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"process supervisor failed: {exc}", file=sys.stderr)
        raise SystemExit(SETUP_EXIT)
PY
  chmod 500 "$path"
}

worker() {
  local run_id=$1 run_dir=$2 work_dir=$3 launch_script=$4 validation_script=$5 heartbeat_seconds=$6
  local expected_launch_sha256=$7 expected_validation_sha256=$8
  local maximum_runtime_seconds=$9 validation_timeout_seconds=${10}
  local progress_file=${11} no_progress_seconds=${12}
  local telemetry_sampler=${13} telemetry_config=${14}
  local expected_telemetry_sampler_sha256=${15} expected_telemetry_config_sha256=${16}
  local telemetry_output=${17}
  local heartbeat_pid= workload_pid= launch_rc validation_rc final_state launch_hash validation_hash
  local snapshot_dir launch_snapshot validation_snapshot process_supervisor_snapshot snapshot_hash
  local workload_start_ticks= last_progress_epoch progress_signature previous_progress_signature= now stalled=0 residual_workload=0
  local telemetry_enabled=0 telemetry_state_dir telemetry_sampler_snapshot telemetry_config_snapshot
  local telemetry_sampler_hash telemetry_config_hash telemetry_start_rc telemetry_stop_rc telemetry_stopped=0

  if [[ $telemetry_sampler != - ]]; then
    telemetry_enabled=1
    telemetry_state_dir="$run_dir/telemetry"
  fi

  cleanup_heartbeat() {
    if [[ -n $heartbeat_pid ]]; then
      kill "$heartbeat_pid" 2>/dev/null || true
      wait "$heartbeat_pid" 2>/dev/null || true
    fi
  }

  cleanup_telemetry() {
    (( telemetry_enabled == 1 )) || return 0
    (( telemetry_stopped == 0 )) || return 0
    telemetry_stopped=1
    if [[ ! -d $telemetry_state_dir ]]; then
      atomic_text "$run_dir/telemetry.stop_exit_code" 125
      return 0
    fi
    set +e
    python3 "$telemetry_sampler_snapshot" stop \
      --state-dir "$telemetry_state_dir" --wait-seconds 10 \
      > "$run_dir/telemetry-status.json.tmp" 2>> "$run_dir/telemetry-control.log"
    telemetry_stop_rc=$?
    set -e
    atomic_text "$run_dir/telemetry.stop_exit_code" "$telemetry_stop_rc"
    if [[ -s $run_dir/telemetry-status.json.tmp ]]; then
      mv -f -- "$run_dir/telemetry-status.json.tmp" "$run_dir/telemetry-status.json"
    else
      rm -f -- "$run_dir/telemetry-status.json.tmp"
    fi
  }

  terminate_workload() {
    if [[ -n $workload_pid ]] && process_is_active "$workload_pid"; then
      kill -TERM -- "-$workload_pid" 2>/dev/null || true
      kill -TERM "$workload_pid" 2>/dev/null || true
    fi
    for _ in {1..50}; do
      process_is_active "$workload_pid" || return 0
      sleep 0.1
    done
    [[ -z $workload_pid ]] || kill -KILL "$workload_pid" 2>/dev/null || true
  }

  handle_signal() {
    local signal_exit=$1
    trap - EXIT INT TERM
    terminate_workload
    [[ -z $workload_pid ]] || wait "$workload_pid" 2>/dev/null || true
    cleanup_telemetry
    cleanup_heartbeat
    [[ -f $run_dir/launch.exit_code ]] || atomic_text "$run_dir/launch.exit_code" "$signal_exit"
    [[ -f $run_dir/validation.exit_code ]] || atomic_text "$run_dir/validation.exit_code" 125
    atomic_text "$run_dir/finished_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    atomic_text "$run_dir/state" INTERRUPTED
    exit "$signal_exit"
  }

  fail_before_launch() {
    local detail=$1
    printf '%s\n' "$detail" >> "$run_dir/stderr.log"
    atomic_text "$run_dir/launch.exit_code" 126
    atomic_text "$run_dir/validation.exit_code" 125
    atomic_text "$run_dir/finished_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    atomic_text "$run_dir/state" FAILED
    return 126
  }

  atomic_text "$run_dir/state" RUNNING
  atomic_text "$run_dir/run.id" "$run_id"
  atomic_text "$run_dir/work.dir" "$work_dir"
  atomic_text "$run_dir/started_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  atomic_text "$run_dir/worker.pid" "$$"
  if worker_start_ticks=$(process_start_ticks "$$"); then
    atomic_text "$run_dir/worker.start_ticks" "$worker_start_ticks"
  fi
  if ! launch_hash=$(sha256_file "$launch_script") || [[ ! $launch_hash =~ ^[0-9a-f]{64}$ ]]; then
    fail_before_launch "failed to hash launch script"
    return $?
  fi
  if ! validation_hash=$(sha256_file "$validation_script") || [[ ! $validation_hash =~ ^[0-9a-f]{64}$ ]]; then
    fail_before_launch "failed to hash validation script"
    return $?
  fi
  if [[ $launch_hash != "$expected_launch_sha256" ]]; then
    fail_before_launch "launch script SHA256 does not match the frozen execution record"
    return $?
  fi
  if [[ $validation_hash != "$expected_validation_sha256" ]]; then
    fail_before_launch "validation script SHA256 does not match the frozen execution record"
    return $?
  fi
  snapshot_dir="$run_dir/.runner-started"
  launch_snapshot="$snapshot_dir/launch.sh"
  validation_snapshot="$snapshot_dir/validation.sh"
  process_supervisor_snapshot="$snapshot_dir/process_tree_supervisor.py"
  if ! cp -- "$launch_script" "$launch_snapshot.tmp" || ! chmod 500 "$launch_snapshot.tmp" || ! mv -f -- "$launch_snapshot.tmp" "$launch_snapshot"; then
    fail_before_launch "failed to snapshot launch script"
    return $?
  fi
  if ! snapshot_hash=$(sha256_file "$launch_snapshot") || [[ $snapshot_hash != "$expected_launch_sha256" ]]; then
    fail_before_launch "launch snapshot SHA256 does not match the frozen execution record"
    return $?
  fi
  if ! cp -- "$validation_script" "$validation_snapshot.tmp" || ! chmod 500 "$validation_snapshot.tmp" || ! mv -f -- "$validation_snapshot.tmp" "$validation_snapshot"; then
    fail_before_launch "failed to snapshot validation script"
    return $?
  fi
  if ! snapshot_hash=$(sha256_file "$validation_snapshot") || [[ $snapshot_hash != "$expected_validation_sha256" ]]; then
    fail_before_launch "validation snapshot SHA256 does not match the frozen execution record"
    return $?
  fi
  if ! write_process_tree_supervisor "$process_supervisor_snapshot"; then
    fail_before_launch "failed to create process-tree supervisor"
    return $?
  fi
  if (( telemetry_enabled == 1 )); then
    telemetry_sampler_snapshot="$snapshot_dir/telemetry_sampler.py"
    telemetry_config_snapshot="$snapshot_dir/telemetry-config.json"
    if ! telemetry_sampler_hash=$(sha256_file "$telemetry_sampler") || [[ $telemetry_sampler_hash != "$expected_telemetry_sampler_sha256" ]]; then
      fail_before_launch "telemetry sampler SHA256 does not match the frozen execution record"
      return $?
    fi
    if ! telemetry_config_hash=$(sha256_file "$telemetry_config") || [[ $telemetry_config_hash != "$expected_telemetry_config_sha256" ]]; then
      fail_before_launch "telemetry config SHA256 does not match the frozen execution record"
      return $?
    fi
    if ! cp -- "$telemetry_sampler" "$telemetry_sampler_snapshot.tmp" || ! chmod 500 "$telemetry_sampler_snapshot.tmp" || ! mv -f -- "$telemetry_sampler_snapshot.tmp" "$telemetry_sampler_snapshot"; then
      fail_before_launch "failed to snapshot telemetry sampler"
      return $?
    fi
    if ! snapshot_hash=$(sha256_file "$telemetry_sampler_snapshot") || [[ $snapshot_hash != "$expected_telemetry_sampler_sha256" ]]; then
      fail_before_launch "telemetry sampler snapshot SHA256 does not match the frozen execution record"
      return $?
    fi
    if ! cp -- "$telemetry_config" "$telemetry_config_snapshot.tmp" || ! chmod 400 "$telemetry_config_snapshot.tmp" || ! mv -f -- "$telemetry_config_snapshot.tmp" "$telemetry_config_snapshot"; then
      fail_before_launch "failed to snapshot telemetry config"
      return $?
    fi
    if ! snapshot_hash=$(sha256_file "$telemetry_config_snapshot") || [[ $snapshot_hash != "$expected_telemetry_config_sha256" ]]; then
      fail_before_launch "telemetry config snapshot SHA256 does not match the frozen execution record"
      return $?
    fi
    telemetry_sampler=$telemetry_sampler_snapshot
    telemetry_config=$telemetry_config_snapshot
    atomic_text "$run_dir/telemetry.sampler_sha256" "$telemetry_sampler_hash"
    atomic_text "$run_dir/telemetry.config_sha256" "$telemetry_config_hash"
    atomic_text "$run_dir/telemetry.output" "$telemetry_output"
  fi
  chmod 500 "$snapshot_dir"
  launch_script=$launch_snapshot
  validation_script=$validation_snapshot
  atomic_text "$run_dir/launch.sha256" "$launch_hash"
  atomic_text "$run_dir/validation.sha256" "$validation_hash"
  atomic_text "$run_dir/maximum_runtime_seconds" "$maximum_runtime_seconds"
  atomic_text "$run_dir/validation_timeout_seconds" "$validation_timeout_seconds"
  atomic_text "$run_dir/heartbeat_seconds" "$heartbeat_seconds"
  atomic_text "$run_dir/progress.file" "$progress_file"
  atomic_text "$run_dir/no_progress_seconds" "$no_progress_seconds"

  (
    while [[ ! -f "$run_dir/finished_at" ]]; do
      atomic_text "$run_dir/heartbeat" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      sleep "$heartbeat_seconds"
    done
  ) &
  heartbeat_pid=$!
  trap 'cleanup_telemetry; cleanup_heartbeat' EXIT
  trap 'handle_signal 130' INT
  trap 'handle_signal 143' TERM

  if (( telemetry_enabled == 1 )); then
    : > "$run_dir/telemetry-control.log"
    set +e
    python3 "$telemetry_sampler" start \
      --config "$telemetry_config" --state-dir "$telemetry_state_dir" --output "$telemetry_output" \
      >> "$run_dir/telemetry-control.log" 2>&1
    telemetry_start_rc=$?
    set -e
    atomic_text "$run_dir/telemetry.start_exit_code" "$telemetry_start_rc"
  fi

  (
    cd "$work_dir"
    exec setsid python3 "$process_supervisor_snapshot" "$maximum_runtime_seconds" "$launch_script" "$run_dir/residual_processes"
  ) >> "$run_dir/stdout.log" 2>> "$run_dir/stderr.log" &
  workload_pid=$!
  atomic_text "$run_dir/workload.pid" "$workload_pid"
  if workload_start_ticks=$(process_start_ticks "$workload_pid"); then
    atomic_text "$run_dir/workload.start_ticks" "$workload_start_ticks"
  fi

  last_progress_epoch=$(date +%s)
  atomic_text "$run_dir/last_progress_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  while kill -0 "$workload_pid" 2>/dev/null; do
    if [[ -e $progress_file ]]; then
      progress_signature=$(stat -c '%y:%s' -- "$progress_file" 2>/dev/null || printf unreadable)
    else
      progress_signature=missing
    fi
    now=$(date +%s)
    if [[ $progress_signature != "$previous_progress_signature" ]]; then
      previous_progress_signature=$progress_signature
      last_progress_epoch=$now
      atomic_text "$run_dir/last_progress_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      atomic_text "$run_dir/progress.signature" "$progress_signature"
    elif (( now - last_progress_epoch >= no_progress_seconds )); then
      stalled=1
      atomic_text "$run_dir/stalled_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      terminate_workload
      break
    fi
    if (( heartbeat_seconds < 10 )); then
      sleep "$heartbeat_seconds"
    else
      sleep 10
    fi
  done
  set +e
  wait "$workload_pid"
  launch_rc=$?
  set -e
  atomic_text "$run_dir/launch.exit_code" "$launch_rc"
  cleanup_telemetry

  if [[ -s $run_dir/residual_processes ]]; then
    residual_workload=1
    printf 'launch exited while descendant processes remained\n' >> "$run_dir/stderr.log"
  fi

  validation_rc=125
  if (( stalled == 1 )); then
    printf 'completion validation skipped because project progress stalled\n' > "$run_dir/validation.log"
  elif (( residual_workload == 1 )); then
    printf 'completion validation skipped because launch left residual processes\n' > "$run_dir/validation.log"
  elif (( launch_rc == 0 )); then
    set +e
    (cd "$work_dir" && timeout --signal=TERM --kill-after=30 "$validation_timeout_seconds" bash "$validation_script") >> "$run_dir/validation.log" 2>&1
    validation_rc=$?
    set -e
  else
    printf 'completion validation skipped because launch exited %s\n' "$launch_rc" > "$run_dir/validation.log"
  fi
  atomic_text "$run_dir/validation.exit_code" "$validation_rc"

  if (( stalled == 1 )); then
    final_state=STALLED
  elif (( launch_rc == 124 )); then
    final_state=TIMED_OUT
  elif (( residual_workload == 1 )); then
    final_state=FAILED
  elif (( launch_rc == 0 && validation_rc == 0 )); then
    final_state=SUCCEEDED
  else
    final_state=FAILED
  fi
  atomic_text "$run_dir/finished_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  atomic_text "$run_dir/state" "$final_state"
  cleanup_heartbeat
  trap - EXIT INT TERM
}

[[ $# -ge 1 ]] || usage
action=$1
shift

if [[ $action == _worker ]]; then
  [[ $# -eq 17 ]] || usage
  worker "$@"
  exit 0
fi

run_dir=
run_id=
work_dir=
launch_script=
validation_script=
heartbeat_seconds=30
expected_launch_sha256=
expected_validation_sha256=
maximum_runtime_seconds=
validation_timeout_seconds=
progress_file=
no_progress_seconds=
telemetry_sampler=
telemetry_config=
expected_telemetry_sampler_sha256=
expected_telemetry_config_sha256=
telemetry_output=

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id) [[ $# -ge 2 ]] || usage; run_id=$2; shift 2 ;;
    --run-dir) [[ $# -ge 2 ]] || usage; run_dir=$2; shift 2 ;;
    --work-dir) [[ $# -ge 2 ]] || usage; work_dir=$2; shift 2 ;;
    --launch-script) [[ $# -ge 2 ]] || usage; launch_script=$2; shift 2 ;;
    --validation-script) [[ $# -ge 2 ]] || usage; validation_script=$2; shift 2 ;;
    --heartbeat-seconds) [[ $# -ge 2 ]] || usage; heartbeat_seconds=$2; shift 2 ;;
    --expected-launch-sha256) [[ $# -ge 2 ]] || usage; expected_launch_sha256=$2; shift 2 ;;
    --expected-validation-sha256) [[ $# -ge 2 ]] || usage; expected_validation_sha256=$2; shift 2 ;;
    --maximum-runtime-seconds) [[ $# -ge 2 ]] || usage; maximum_runtime_seconds=$2; shift 2 ;;
    --validation-timeout-seconds) [[ $# -ge 2 ]] || usage; validation_timeout_seconds=$2; shift 2 ;;
    --progress-file) [[ $# -ge 2 ]] || usage; progress_file=$2; shift 2 ;;
    --no-progress-seconds) [[ $# -ge 2 ]] || usage; no_progress_seconds=$2; shift 2 ;;
    --telemetry-sampler) [[ $# -ge 2 ]] || usage; telemetry_sampler=$2; shift 2 ;;
    --telemetry-config) [[ $# -ge 2 ]] || usage; telemetry_config=$2; shift 2 ;;
    --expected-telemetry-sampler-sha256) [[ $# -ge 2 ]] || usage; expected_telemetry_sampler_sha256=$2; shift 2 ;;
    --expected-telemetry-config-sha256) [[ $# -ge 2 ]] || usage; expected_telemetry_config_sha256=$2; shift 2 ;;
    --telemetry-output) [[ $# -ge 2 ]] || usage; telemetry_output=$2; shift 2 ;;
    *) usage ;;
  esac
done

if [[ $action == preflight ]]; then
  [[ -z $run_dir && -z $work_dir && -z $launch_script && -z $validation_script && -z $telemetry_sampler && -z $telemetry_config && -z $expected_telemetry_sampler_sha256 && -z $expected_telemetry_config_sha256 && -z $telemetry_output ]] || usage
  runner_preflight
  exit 0
fi

[[ -n $run_dir ]] || usage

case "$action" in
  start)
    [[ -n $run_id && -n $work_dir && -n $launch_script && -n $validation_script && -n $expected_launch_sha256 && -n $expected_validation_sha256 && -n $maximum_runtime_seconds && -n $validation_timeout_seconds && -n $progress_file && -n $no_progress_seconds ]] || usage
    [[ $run_id =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ ]] || { echo "invalid run ID" >&2; exit 2; }
    [[ -d $work_dir ]] || { echo "work directory does not exist: $work_dir" >&2; exit 2; }
    [[ -f $launch_script && -r $launch_script ]] || { echo "launch script is not readable" >&2; exit 2; }
    [[ -f $validation_script && -r $validation_script ]] || { echo "validation script is not readable" >&2; exit 2; }
    [[ $heartbeat_seconds =~ ^[0-9]+$ ]] && (( heartbeat_seconds >= 1 )) || { echo "invalid heartbeat interval" >&2; exit 2; }
    [[ $expected_launch_sha256 =~ ^[0-9a-f]{64}$ ]] || { echo "invalid expected launch SHA256" >&2; exit 2; }
    [[ $expected_validation_sha256 =~ ^[0-9a-f]{64}$ ]] || { echo "invalid expected validation SHA256" >&2; exit 2; }
    [[ $maximum_runtime_seconds =~ ^[0-9]+$ ]] && (( maximum_runtime_seconds >= 1 )) || { echo "invalid maximum runtime" >&2; exit 2; }
    [[ $validation_timeout_seconds =~ ^[0-9]+$ ]] && (( validation_timeout_seconds >= 1 )) || { echo "invalid validation timeout" >&2; exit 2; }
    [[ $no_progress_seconds =~ ^[0-9]+$ ]] && (( no_progress_seconds >= 1 )) || { echo "invalid no-progress deadline" >&2; exit 2; }
    telemetry_field_count=0
    for telemetry_field in "$telemetry_sampler" "$telemetry_config" "$expected_telemetry_sampler_sha256" "$expected_telemetry_config_sha256" "$telemetry_output"; do
      [[ -z $telemetry_field ]] || telemetry_field_count=$((telemetry_field_count + 1))
    done
    if (( telemetry_field_count != 0 && telemetry_field_count != 5 )); then
      echo "all telemetry options must be supplied together" >&2
      exit 2
    fi
    if (( telemetry_field_count == 5 )); then
      [[ -f $telemetry_sampler && -r $telemetry_sampler ]] || { echo "telemetry sampler is not readable" >&2; exit 2; }
      [[ -f $telemetry_config && -r $telemetry_config ]] || { echo "telemetry config is not readable" >&2; exit 2; }
      [[ $expected_telemetry_sampler_sha256 =~ ^[0-9a-f]{64}$ ]] || { echo "invalid expected telemetry sampler SHA256" >&2; exit 2; }
      [[ $expected_telemetry_config_sha256 =~ ^[0-9a-f]{64}$ ]] || { echo "invalid expected telemetry config SHA256" >&2; exit 2; }
    fi
    check_runtime_dependencies
    if [[ -e $run_dir/state || -e $run_dir/.runner-started ]]; then
      echo "run directory already contains state: $run_dir" >&2
      exit 3
    fi
    mkdir -p -- "$run_dir"
    mkdir -- "$run_dir/.runner-started" 2>/dev/null || {
      echo "another start already claimed this run directory: $run_dir" >&2
      exit 3
    }
    run_dir=$(cd -- "$run_dir" && pwd -P)
    work_dir=$(cd -- "$work_dir" && pwd -P)
    [[ $progress_file == /* ]] || progress_file="$work_dir/$progress_file"
    launch_script=$(cd -- "$(dirname -- "$launch_script")" && printf '%s/%s\n' "$(pwd -P)" "$(basename -- "$launch_script")")
    validation_script=$(cd -- "$(dirname -- "$validation_script")" && printf '%s/%s\n' "$(pwd -P)" "$(basename -- "$validation_script")")
    if (( telemetry_field_count == 5 )); then
      [[ $telemetry_output == /* ]] || telemetry_output="$work_dir/$telemetry_output"
      telemetry_sampler=$(cd -- "$(dirname -- "$telemetry_sampler")" && printf '%s/%s\n' "$(pwd -P)" "$(basename -- "$telemetry_sampler")")
      telemetry_config=$(cd -- "$(dirname -- "$telemetry_config")" && printf '%s/%s\n' "$(pwd -P)" "$(basename -- "$telemetry_config")")
    else
      telemetry_sampler=-
      telemetry_config=-
      expected_telemetry_sampler_sha256=-
      expected_telemetry_config_sha256=-
      telemetry_output=-
    fi
    : > "$run_dir/stdout.log"
    : > "$run_dir/stderr.log"
    : > "$run_dir/validation.log"
    script_path=$(cd -- "$(dirname -- "$0")" && printf '%s/%s\n' "$(pwd -P)" "$(basename -- "$0")")
    atomic_text "$run_dir/run.id" "$run_id"
    atomic_text "$run_dir/state" STARTING
    nohup setsid --fork --wait "$script_path" _worker "$run_id" "$run_dir" "$work_dir" "$launch_script" "$validation_script" "$heartbeat_seconds" \
      "$expected_launch_sha256" "$expected_validation_sha256" "$maximum_runtime_seconds" "$validation_timeout_seconds" "$progress_file" "$no_progress_seconds" \
      "$telemetry_sampler" "$telemetry_config" "$expected_telemetry_sampler_sha256" "$expected_telemetry_config_sha256" "$telemetry_output" \
      >> "$run_dir/supervisor.log" 2>&1 < /dev/null &
    supervisor_pid=$!
    atomic_text "$run_dir/supervisor.pid" "$supervisor_pid"
    if supervisor_start_ticks=$(process_start_ticks "$supervisor_pid"); then
      atomic_text "$run_dir/supervisor.start_ticks" "$supervisor_start_ticks"
    fi
    printf 'STARTED supervisor_pid=%s run_dir=%s\n' "$supervisor_pid" "$run_dir"
    ;;
  status)
    [[ -f $run_dir/state ]] || { echo "state=UNKNOWN"; exit 4; }
    recorded_state=$(cat "$run_dir/state")
    launcher_state=absent
    if [[ -f $run_dir/supervisor.pid ]]; then
      supervisor_pid=$(cat "$run_dir/supervisor.pid")
      if [[ $supervisor_pid =~ ^[0-9]+$ ]] && process_is_active "$supervisor_pid" && observed_supervisor_ticks=$(process_start_ticks "$supervisor_pid"); then
        if [[ ! -f $run_dir/supervisor.start_ticks || $observed_supervisor_ticks == "$(cat "$run_dir/supervisor.start_ticks")" ]]; then
          launcher_state=present
        fi
      fi
    fi
    worker_state=absent
    if [[ -f $run_dir/worker.pid ]]; then
      pid=$(cat "$run_dir/worker.pid")
      if [[ $pid =~ ^[0-9]+$ ]] && process_is_active "$pid" && observed_ticks=$(process_start_ticks "$pid"); then
        if [[ ! -f $run_dir/worker.start_ticks || $observed_ticks == "$(cat "$run_dir/worker.start_ticks")" ]]; then
          worker_state=present
        fi
      fi
    fi
    workload_state=absent
    if [[ -f $run_dir/workload.pid ]]; then
      workload_pid=$(cat "$run_dir/workload.pid")
      if [[ $workload_pid =~ ^[0-9]+$ ]] && process_is_active "$workload_pid" && observed_workload_ticks=$(process_start_ticks "$workload_pid"); then
        if [[ ! -f $run_dir/workload.start_ticks || $observed_workload_ticks == "$(cat "$run_dir/workload.start_ticks")" ]]; then
          workload_state=present
        fi
      fi
    fi
    effective_state=$recorded_state
    if [[ $recorded_state == STARTING && $worker_state == absent ]]; then
      if [[ -f $run_dir/worker.pid || $launcher_state == absent ]]; then
        effective_state=INTERRUPTED
      fi
    elif [[ $recorded_state == RUNNING && $worker_state == absent ]]; then
      if [[ $workload_state == present ]]; then
        effective_state=ORPHANED
      else
        effective_state=INTERRUPTED
      fi
    fi
    printf 'state=%s\n' "$effective_state"
    [[ $effective_state == "$recorded_state" ]] || printf 'recorded_state=%s\n' "$recorded_state"
    for field in run.id work.dir supervisor.pid supervisor.start_ticks worker.pid worker.start_ticks workload.pid workload.start_ticks residual_processes started_at heartbeat heartbeat_seconds last_progress_at progress.signature stalled_at finished_at launch.exit_code validation.exit_code launch.sha256 validation.sha256 maximum_runtime_seconds validation_timeout_seconds progress.file no_progress_seconds telemetry.sampler_sha256 telemetry.config_sha256 telemetry.output telemetry.start_exit_code telemetry.stop_exit_code; do
      if [[ -f $run_dir/$field ]]; then
        printf '%s=%s\n' "$field" "$(cat "$run_dir/$field")"
      fi
    done
    printf 'launcher_process=%s\n' "$launcher_state"
    printf 'supervisor_process=%s\n' "$worker_state"
    printf 'workload_process=%s\n' "$workload_state"
    if [[ -f $run_dir/telemetry/state ]]; then
      printf 'telemetry.state=%s\n' "$(cat "$run_dir/telemetry/state")"
    fi
    ;;
  *) usage ;;
esac
