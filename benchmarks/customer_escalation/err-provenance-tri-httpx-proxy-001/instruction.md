# Trace 'peer unexpectedly closed connection' from a proxied httpx client through httpcore's CONNECT tunnel to its origin

A customer's platform team runs async httpx workers inside a locked-down
datacenter where all egress traverses a corporate HTTP proxy. Their client:

    client = httpx.AsyncClient(
        proxy="http://proxy.internal.example-corp.net:3128",
        timeout=httpx.Timeout(120.0),
    )
    resp = await client.get("https://reports.vendor-api.com/v2/export/full.csv")

Large exports intermittently fail with:

    httpx.RemoteProtocolError: peer unexpectedly closed connection

The vendor's API team checked their access logs: every request from this
customer shows a 200 with the full body written. From a jump host that
bypasses the proxy the same download always succeeds. The customer is
escalating because the error text blames the "peer" -- they read that as
httpx accusing the vendor API of closing the connection, which the vendor
denies. Nobody on the customer side can say which component actually
generates this message.

Your task:

1. Locate the exact origin of the message text "peer unexpectedly closed
   connection" -- which repository, file, and function raise it, and the
   precise receive-buffer/state condition that triggers it.
2. Trace how a proxied httpx request wires that parser into the stack: the
   AsyncHTTPTransport branch that constructs the proxy connection pool for
   http/https proxy URLs, the tunnel connection class that issues the CONNECT
   request to the proxy, and the HTTP/1.1 connection layer that instantiates
   the parser state machine over the tunneled stream. Cite the file and the
   class or function responsible at each step.
3. Explain every exception-translation layer between the origin and what the
   customer sees: the mapping applied around next_event() in the HTTP/1.1
   connection layer, and the httpx-side context manager and exception table
   that produce httpx.RemoteProtocolError.
4. Explain the trigger conditions: when does this exact message fire versus
   the alternative "Server disconnected without sending a response." raised
   one layer up (including the their_state check that separates the two
   cases), and which network hop -- the origin server or the corporate
   proxy -- is actually the "peer" closing the tunneled connection in this
   deployment.

- Source files across all three repositories on the failure path
- The full error chain from the public httpx API down to the origin of the
  message text and back up through both translation layers
- Trigger conditions distinguishing the two disconnect messages

In answer.json, alongside your analysis fields, include a top-level
"citations" list with one entry per cited file:
{"repo": ..., "file": ..., "evidence_span": ...} -- where "repo" is the
repository directory (httpx, httpcore, or h11), "file" is the path inside
that repository, and "evidence_span" is a verbatim excerpt copied from the
cited file (at least 20 characters). Paraphrased or fabricated spans fail
verification.
