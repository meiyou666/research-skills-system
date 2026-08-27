# Contract-driven telemetry sampling

Load this reference when a run needs periodic hardware, runtime, operating-system, framework, energy, or application telemetry. Treat it as an optional method package. The experiment protocol decides which signals matter and which backend tool can observe them.

## Use the generic sampler

`scripts/telemetry_sampler.py` supervises bounded probes and exposes `start`, `status`, and `stop`. It invokes each probe as an argv array with `shell=False`; it rejects shell command-string forms. A missing executable becomes `unavailable`, a declared unavailable exit code remains `unavailable`, and timeout, oversized output, parse failure, or another nonzero exit becomes `failed`. One probe failure does not suppress other probes.

Use a fresh state directory and output path:

```bash
python3 scripts/telemetry_sampler.py start \
  --config telemetry-config.json \
  --state-dir run-state/telemetry \
  --output results/telemetry.jsonl
python3 scripts/telemetry_sampler.py status --state-dir run-state/telemetry
python3 scripts/telemetry_sampler.py stop --state-dir run-state/telemetry
```

The state directory retains a config snapshot, tool/config hashes, process state, heartbeat, and terminal summary. Supply the config as a direct regular file and the output as a fresh path; the sampler rejects config symlinks and any existing output directory entry, including dangling symlinks and special files, before launch and again in the worker. On Linux it also retains launcher and worker `/proc` start ticks; status rejects zombie processes and a reused PID whose observed ticks do not match. On other operating systems status explicitly reports a `signal_only` process check with unverified identity because `/proc` identity is unavailable. The JSONL output retains every committed sample and every probe outcome. Bound the campaign with `max_samples`, interval, per-command timeout, the shared stdout/stderr cap `max_output_bytes`, and the whole-file cap `max_telemetry_bytes`. The sampler reads both process pipes concurrently and stops a probe as soon as their shared cap is exceeded; it never stages unbounded probe output on disk. For an oversized probe, byte counts and hashes describe only the retained prefix and `output_truncated` is true.

Every sample records adjacent UTC and monotonic-clock observations plus elapsed seconds. Use `monotonic_ns` or `elapsed_seconds` for ordering, interval calculations, and energy integration; treat `observed_at` as a wall-clock label that can jump when the host clock is corrected. If the next complete JSONL record would cross `max_telemetry_bytes`, the sampler commits no partial line and closes with `FAILED` plus `error_code: telemetry_output_limit_exceeded`.

## Write a minimal config

```json
{
  "schema_version": 1,
  "sampler_id": "run-telemetry",
  "interval_seconds": 5,
  "command_timeout_seconds": 2,
  "max_samples": 7200,
  "max_output_bytes": 65536,
  "max_telemetry_bytes": 268435456,
  "environment_allowlist": ["PATH", "CUDA_VISIBLE_DEVICES"],
  "probes": [
    {
      "id": "device",
      "argv": ["telemetry-tool", "--machine-readable"],
      "format": "json",
      "unavailable_exit_codes": [127]
    }
  ]
}
```

Replace the example tool and parser contract with a capability-detected backend. An NVIDIA, AMD, Intel, framework, operating-system, or application-specific probe is a caller-selected adapter, not a sampler invariant. Prefer machine-readable, read-only commands. Keep tokens and secret values out of argv and config. Restrict `environment_allowlist` to non-secret run settings needed by the probe, such as device visibility or locale. The sampler rejects secret-shaped names; inherited values can still be emitted by a probe, so review trusted probe behavior before retaining excerpts or parsed values.

Defaults and hard ceilings prevent an accidental unbounded campaign while leaving ordinary long runs configurable:

| Setting | Default | Hard ceiling |
| --- | ---: | ---: |
| `max_telemetry_bytes` | 256 MiB | 4 GiB |
| `max_output_bytes` | 64 KiB | 16 MiB per probe invocation |
| combined probe capture | sum of configured probe caps | 64 MiB per sample |
| `command_timeout_seconds` | 10 s | 1 h |
| `interval_seconds` | required | 24 h |
| `max_samples` | required | 10,000,000 |
| probe count | required | 128 |

## Let the runner host it when useful

Pass all five optional telemetry arguments to `remote_runner.sh start`: sampler file, config file, both expected SHA256 values, and output path. The runner snapshots and verifies the two files, starts sampling before the workload, stops it after workload exit, and reports sampler state independently. It does not turn optional telemetry failure into workload failure. Set `telemetry.required: true` in the materialized execution record and enforce it in the completion validator only when missing telemetry invalidates the experiment or removes a required safety signal.

Put shareable raw samples under the result root and declare the relative path in `required_results` when required downstream. Keep control logs, process IDs, and sensitive diagnostics in run state. Preserve `unavailable` and `failed` records; do not impute them as zero or claim a backend was observed when its probe was absent.
