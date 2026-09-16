# Container PDF workers (Photon OS / Portainer)

The default `PDF_WORKER_BACKEND=landlock` retains the existing Linux Landlock + seccomp and macOS Seatbelt process isolation. Operators may explicitly select `PDF_WORKER_BACKEND=container` when the host lacks Landlock. There is no automatic fallback or unsandboxed parsing mode.

## Trust boundary

The web application does **not** receive the Docker socket. An installation-specific runner service runs `python -m backend.runner_service`. Its Unix socket is shared only with that edition's application, mode 0600 and owned by UID 10001. It exposes fixed parse/status/result/cancel/reset operations, with no caller-selected image, command, mounts, environment, privileges, or network options. This internal control protocol is not a user-facing API; existing upload, progress, retry, cancellation, deletion and export APIs are unchanged.

Only the runner receives `/var/run/docker.sock`. Docker socket access is host-administrator-equivalent: the runner is trusted deployment infrastructure, not a sandboxed parser. Keep its code and image operator-controlled, use separate runner/state/socket volumes per edition, and never expose its Unix socket through a web proxy or TCP listener. The runner itself has network mode `none`, a read-only root, resource limits and only the capabilities needed for staging ownership and cleanup.

Each PDF runs in a newly created container, using a worker image resolved to an immutable image ID at runner startup. It runs as UID/GID 10001, drops all capabilities, has no new privileges, no network, Docker's default seccomp policy, a read-only root, a private PID namespace, a one-CPU limit, memory/swap limits and a 64-process limit. The parser adds its existing deny rules for networking, exec, ptrace and related syscalls. It verifies the container restrictions before accepting the container-worker mode.

The worker receives **only a staging copy of one PDF and its optional signed-pack profile**. Its one writable bind mount is that random staging subdirectory. It never receives the application's uploads, database, credentials, runner socket or Docker socket. The runner rejects path traversal, symbolic/hard links, devices and oversized inputs/outputs. Result and progress files are read as bounded data. Source PDFs remain unchanged.

## Operator settings

Application:

- `PDF_WORKER_BACKEND=container`
- `PDF_RUNNER_SOCKET=/runner/runner.sock`
- Mount that edition's runner-socket volume at `/runner`.

Runner:

- `RUNNER_ID`: unique installation/edition identifier; also scopes worker cleanup.
- `RUNNER_IMAGE`: matching application image. Pin the deployment image; the runner resolves it to an image ID and never pulls images.
- `RUNNER_STATE_VOLUME`: Docker volume name mounted at `/state`. It **must** use the local driver with `type=tmpfs`, `device=tmpfs`, and `o=size=512m,mode=700`. This is a hard aggregate staging-space limit per runner.
- `MAX_WORKERS`: 1–8; default 2. Match the application's ceiling.
- `WORKER_MEMORY_MIB`: 256–8192; default 2048.
- Mount that edition's uploads volume at `/uploads:ro`, its runner-socket volume at `/runner`, and the Docker socket at `/var/run/docker.sock`.

Workers retain per-file page limits (up to 2000), per-attempt timeout (up to 120 minutes), parser address-space/CPU/file-size/open-file limits, and the application's existing bounded persistent queue. User-configured limits cannot exceed the runner's hard validation limits. Public retention remains 24 hours.

## Recovery and operations

Start the runner before the API. API startup checks connectivity and asks its runner to remove stale workers before recovering interrupted database jobs. Runner startup removes only containers carrying its exact identity label. Queue cancellation deletes the matching worker immediately. A runner watchdog also expires abandoned workers and staging directories, independent of the API process. No PDF content or filenames are written to runner or worker container logs.

Restart the runner together with its edition's API: in-flight imports will be marked failed/interrupted and can be retried. Do not delete persistent report/upload/system volumes when replacing images. Runner staging and sockets are disposable.

Use the normal Dockerfile for fresh offline builds. `deployment/Dockerfile.worker-update` supports an offline maintenance layer over the immutable ID of the matching prior edition image; it changes backend code and build identity without changing PDF dependencies or frontend assets. Retain both source revisions and the base image identity with the deployment record.

## Verification

Run `tests/test_container_workers.py` in both editions and the existing security, queue/progress and PDF regression tests. On the target host additionally verify: real PDF parsing and source parity, progress/page counts, cancellation and deadline cleanup, restart recovery, denial of network/other-job/database/socket access, read-only root and dropped capabilities, rejected arbitrary launch fields and path escapes, unchanged source PDF hashes, public ownership enforcement, and persistent reports after restart. Never use a passing health endpoint alone as proof that the parser works.

### Progress update races

The supervisor tolerates progress files disappearing between directory enumeration and stat, as happens during the parser's atomic progress rename. It continues checking remaining files and retains aggregate-size and deadline enforcement. Regression coverage simulates this exact race alongside oversized and expired jobs.
