# Trace 'illegal header line' from an httpx client behind a SOCKS5 tunnel to its origin and exonerate the tunnel

A customer integrates with a legacy vendor appliance ("LegacyGW") that lives
on an isolated management network. Developers reach it through an SSH dynamic
port-forward used as a SOCKS5 proxy:

    ssh -D 1080 -N jump.example-corp.net

    client = httpx.AsyncClient(proxy="socks5://localhost:1080")
    resp = await client.get("http://legacygw.mgmt.internal:8080/api/status")

Every single request fails with:

    httpx.RemoteProtocolError: illegal header line: bytearray(b'X-Gw-Status : OK')

What has convinced the customer this is a proxy bug: the exact same request
through the exact same tunnel works from curl:

    curl --socks5-hostname localhost:1080 http://legacygw.mgmt.internal:8080/api/status

prints the JSON body without complaint. The customer has filed this as
"httpx SOCKS support corrupts response bytes" and wants it fixed. The
appliance vendor is unresponsive, and nobody has explained where the message
"illegal header line" even comes from.

Your task:

1. Locate the exact origin of the message text "illegal header line" --
   which repository, file, and function produce it, the validation helper
   that formats it, and the compiled grammar regex the header line is
   matched against.
2. Resolve the exception-class paradox: the raising site constructs a
   LocalProtocolError, yet the exception the customer catches is a
   RemoteProtocolError. Find the mechanism that performs this conversion,
   the file that defines it, and the except-block that invokes it.
3. Trace the SOCKS transport path and show the tunnel is NOT corrupting
   bytes: the httpx AsyncHTTPTransport branch selected for socks5:// proxy
   URLs, the httpcore SOCKS proxy pool and per-connection class, the SOCKS5
   handshake helper, and the point after tunnel establishment where the
   plain HTTP/1.1 connection layer and its parser state machine take over.
   Cite files and classes at each step.
4. State the actual trigger: which byte sequence in the appliance's response
   violates which grammar rule (look at the whitespace around the colon in
   the quoted header), and why curl accepts the same response. Give the
   support engineer a defensible verdict: is this an httpx bug, and what
   are the customer's realistic options?

- Source files across all three repositories on the failure path
- The exception conversion mechanism, named exactly
- The transport chain proving the SOCKS layer hands off before parsing
