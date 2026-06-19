# Map customer httpx ReadTimeout-with-timeout=None complaint across the httpx -> httpcore boundary

A customer reports that their httpx async streaming download still raises
httpx.ReadTimeout even though they explicitly disable timeouts. Their code:

    timeout = httpx.Timeout(timeout=None)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("GET", "https://example.com/big.bin") as resp:
            async for chunk in resp.aiter_bytes():
                ...

After roughly 5 seconds of an idle server they get:

    httpx.ReadTimeout

They expect timeout=None to mean wait indefinitely. They are confused that
"None" is somehow being upgraded to a 5-second cap somewhere in the stack.

Your task:

1. Find where httpx defines its public Timeout configuration -- trace the
   Timeout class fields (connect / read / write / pool), how None is normalized,
   and the global default that applies when nothing is passed in.
2. Find where httpx hands the timeout to httpcore -- trace the AsyncHTTPTransport
   construction of httpcore.ConnectionPool and the per-request handle_async_request
   path, and identify exactly how the four timeout dimensions are propagated
   (note: they are NOT passed to the ConnectionPool constructor).
3. Trace the full code path: httpx.AsyncClient.stream -> AsyncHTTPTransport
   .handle_async_request -> httpcore.Request extensions -> httpcore connection
   pool / AsyncHTTP11Connection -> per-operation timeout enforcement -> httpcore
   ReadTimeout -> mapped back to httpx.ReadTimeout via HTTPCORE_EXC_MAP. Cite
   each file and the function or attribute responsible at every step.
4. Identify the *real* reason the customer still sees a ~5 second timeout when
   timeout=None should disable it. The explanation must reference both repos and
   the marshaling boundary between them.

- Full code path from public Timeout config to httpcore per-op timeout
- Why DEFAULT_TIMEOUT_CONFIG vs an explicit Timeout(None) differ in effect
- The mapping that converts httpcore.ReadTimeout into httpx.ReadTimeout
