# Incident: Spurious Container Restart Warnings During Docker Daemon Shutdown

## Alert

Operations team has reported that Docker daemon graceful shutdowns trigger PagerDuty alerts. The monitoring system picks up `WARN ShouldRestart failed` log messages and interprets them as container health failures.

## Error Logs

During a normal `docker stop` or daemon SIGINT shutdown, these messages appear:

```
INFO[2026-02-21T20:04:42.937Z] Processing signal 'interrupt'
INFO[2026-02-21T20:04:43.074Z] ignoring event  container=1ed1fcfd71c2 module=libcontainerd namespace=moby topic=/tasks/delete type="*events.TaskDelete"
INFO[2026-02-21T20:04:43.073Z] shim disconnected  id=1ed1fcfd71c2 namespace=moby
INFO[2026-02-21T20:04:43.074Z] cleaning up after shim disconnected  id=1ed1fcfd71c2 namespace=moby
INFO[2026-02-21T20:04:43.074Z] cleaning up dead shim  id=1ed1fcfd71c2 namespace=moby
WARN[2026-02-21T20:04:43.084Z] ShouldRestart failed, container will not be restarted  container=1ed1fcfd71c2 daemonShuttingDown=true error="restart canceled" execDuration=4.868s exitStatus="{0 2026-02-21 20:04:43 +0000 UTC}" hasBeenManuallyStopped=false restartCount=0
INFO[2026-02-21T20:04:43.231Z] stopping event stream following graceful shutdown  error="<nil>" module=libcontainerd namespace=moby
INFO[2026-02-21T20:04:44.238Z] Daemon shutdown complete
```

## Key Issues

1. **"ShouldRestart failed" warning**: This appears during normal shutdown for containers with restart policies. The warning makes it look like something went wrong, but the daemon is intentionally shutting down.

2. **"ignoring event" message**: The containerd TaskDelete event is logged as "ignoring" which suggests events are being dropped, when really the daemon just doesn't need to act on it during shutdown.

3. **exitStatus formatting**: The `exitStatus="{0 2026-02-21 20:04:43 +0000 UTC}"` is not human-readable.

## Environment

- Docker (moby) v28.0.0 at `/workspace/moby/`
- containerd v1.7.24 at `/workspace/containerd/`
- Focus on the daemon shutdown path and its interaction with containerd shim lifecycle

## What I Need

1. **Root Cause**: Which file and function produces the "ShouldRestart failed" warning? Why does `ErrRestartCanceled` get logged as a warning during normal shutdown?

2. **Error Chain**: Trace the full shutdown flow: SIGINT signal -> daemon shutdown -> container stop -> containerd shim lifecycle events -> restart manager -> the warning message. Investigate the containerd side in `/workspace/containerd/runtime/v2/shim.go` and `/workspace/containerd/pkg/process/exec.go` to understand how shim exit and TaskDelete events are generated.

3. **Affected Components**: What parts of both moby and containerd are involved? (restart manager, monitor, libcontainerd client, container state, containerd shim v2 runtime, task service)

4. **Remediation**: How should the logging be fixed to distinguish between genuine restart failures and expected shutdown behavior?

## Output

Write your findings to `/workspace/moby/INCIDENT_REPORT.md`.
