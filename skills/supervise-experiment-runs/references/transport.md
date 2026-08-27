# Execution Transport

Choose `local` when the controlling agent can execute inside the target Linux environment. Choose `ssh` for a separate server. Preserve the same contract, runner, progress, completion, recovery, and manifest semantics across both.

## Local transport

Run bounded probes and bundled scripts directly. Record the observed host identity, user, environment boundary, and absolute role paths in private deployment state. Launch through `remote_runner.sh` to detach from the controlling shell and retain the same terminal-state evidence as SSH runs. Verify that the local host keeps detached descendants before treating this as disconnect persistence.

Use a caller-owned campaign state directory and a fresh result destination. Do not equate a live controlling terminal with workload health. Poll the retained runner state and useful progress independently. Collect completed results with `collect_local_results.sh`.

## SSH transport

Create one private state directory per deployment and retain `connection/known_hosts` plus redacted attempts. Use the same `known_hosts` file throughout the campaign. `scripts/ssh_session.sh` selects `accept-new` before a key is present and `yes` after pinning it. Treat a changed key as terminal until the caller verifies identity through a trusted channel.

Inspect effective non-secret settings and probe with:

```sh
scripts/ssh_session.sh config \
  --host "$REMOTE_HOST" --user "$REMOTE_USER" --port "${REMOTE_PORT:-22}" \
  --known-hosts "$CAMPAIGN_STATE/connection/known_hosts"
scripts/ssh_session.sh probe <connection-options>
```

Use `run`, `shell`, and `upload` with the same options. Let OpenSSH prompt interactively or pass a caller-managed mode-`0600` password file for headless authentication. Keep password values and private-key contents outside deployment records and logs. The helper ignores ambient per-user SSH configuration, disables proxies and forwarding, and binds the supplied endpoint directly.

## Failure classes

Record a UTC time, redacted endpoint or host label, transport, exit code, bounded duration, and one class:

| Class | Evidence | Action |
| --- | --- | --- |
| `LOCAL_POLICY` | process, device, or network authority denied | use an authorized execution layer |
| `RESOLUTION` | SSH host cannot be resolved | verify the supplied endpoint |
| `TIMEOUT` | transport deadline elapsed | inspect route or local system health |
| `REFUSED` | SSH endpoint rejected the connection | confirm service and port |
| `HOST_KEY` | SSH key changed or verification failed | verify identity before changing the pinned key |
| `AUTHENTICATION` | server rejected authentication | verify account and allowed method |
| `COMMAND` | transport worked and the command failed | preserve exit code and bounded stderr |

Test from the exact execution layer used for supervision. A transport interruption changes observability; it does not by itself establish the workload's terminal state.
