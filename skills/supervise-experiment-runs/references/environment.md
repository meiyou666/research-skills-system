# Execution Environment

Prepare the local or SSH-accessible target from observed host state and the frozen environment requirements.

## Inspect before mutation

Run the bundled read-only inventory and retain its output in private campaign state:

```sh
scripts/ssh_session.sh run <connection-options> -- 'bash -s' \
  < scripts/inspect_server.sh > "$CAMPAIGN_STATE/server-inspection.txt"
```

Use the inventory to establish:

- OS, architecture, container context, shell, and package manager;
- effective CPU and memory limits, including cgroups;
- devices, drivers, runtime compatibility, and accelerator memory when present;
- filesystems, mounts, free space, and candidate writable storage;
- compiler, build, language, version-control, transfer, and archive tools;
- whether common proxy variables are configured, without their values.

The raw inventory can identify infrastructure and accounts. Keep it out of the result bundle and public artifacts.

## Build an idempotent bootstrap

Materialize only the frozen environment requirements. Give the bootstrap these properties:

- use strict error handling and explicit noninteractive modes;
- pin or constrain source revisions and dependency versions;
- declare package and artifact sources;
- create directories, install packages, synchronize sources, and build idempotently;
- place caches and large artifacts on approved storage;
- keep mutations within the deployment binding's allowed scope;
- emit UTC timestamps, step identities, and preserved exit codes;
- contain no credentials or secret-bearing URLs;
- leave validation to a separate non-mutating artifact.

Hash the bootstrap before execution. Retain its content, digest, log, exit code, and any approved system-wide changes in private campaign state. A logging pipeline must preserve the bootstrap exit code.

Validate configured sources with bounded metadata operations before large transfers. Treat an installed device driver as part of the host base unless the frozen requirements explicitly authorize a compatible change.

## Apply the validation gate

Validate the exact environment that will run the workload:

1. activate the selected environment or container;
2. report source and dependency identities;
3. load required packages and compiled extensions;
4. enumerate visible devices and effective resource limits;
5. run the frozen representative smoke check;
6. verify work, run-state, checkpoint, and result roles are writable and have sufficient capacity;
7. verify Bash, Python 3.10+, tar, SHA256, `stat`, `timeout`, `nohup`, `setsid`, `/proc`, and Linux child-subreaper support;
8. run `scripts/remote_runner.sh preflight`.

Record inspection, bootstrap, and validation digests; installed identities; selected storage; commands; and exit codes. Reuse the environment only while these identities remain valid.
