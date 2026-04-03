# Trace user-facing Docker 'executable file not found in $PATH' error through CLI to Moby daemon origin

A customer reports this error when running `docker run`:

    docker: Error response from daemon: failed to create task for container:
    failed to create shim task: OCI runtime create failed: runc create failed:
    unable to start container process: exec: "myapp": executable file not found
    in $PATH: unknown.

The customer insists the executable exists in their image. Your task is to trace
this error from the user-facing Docker CLI output all the way back to its origin
in the Moby daemon code to understand the full error chain and identify potential
false-positive conditions.

Your task:
1. Find where the Docker CLI formats and displays this error to the user — trace
   from the `docker run` command handler through the API client.
2. Find where the Moby daemon generates the "failed to create task" error — trace
   through the container runtime integration (containerd, runc shim).
3. Trace the full error propagation chain: daemon → API response → CLI parsing →
   user-visible output. Document each file and function in the chain.
4. Identify the conditions in the daemon code that can trigger this error beyond
   the obvious "file doesn't exist" — PATH resolution logic, image layer issues,
   or entrypoint/cmd override interactions.

Write your analysis to /workspace/ERROR_PROVENANCE.md with:
- Full error chain (file:function at each step)
- Error origin in daemon code
- Error formatting in CLI code
- Alternative trigger conditions beyond missing executable
