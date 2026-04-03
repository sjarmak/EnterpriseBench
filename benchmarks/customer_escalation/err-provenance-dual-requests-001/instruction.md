# Trace requests SSLError through to urllib3 certificate verification and ssl module interaction

A customer reports this error when calling an internal API endpoint signed by
their corporate CA:

    requests.exceptions.SSLError: HTTPSConnectionPool(host='api.internal.corp',
    port=443): Max retries exceeded with url: /v1/data (Caused by
    SSLError(SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED]
    certificate verify failed: unable to get local issuer certificate
    (_ssl.c:1006)')))

The customer has set `REQUESTS_CA_BUNDLE=/etc/ssl/certs/corp-ca.pem` but the
error persists. They have verified the certificate file exists and is valid
using `openssl verify`.

Your task:

1. Find where the requests library initiates HTTPS connections and how it
   resolves CA bundle configuration — trace from requests.get() through the
   Session, HTTPAdapter, and into urllib3 pool manager creation.
2. Find where urllib3 performs SSL certificate verification — trace through
   HTTPSConnectionPool, the ssl_wrap_socket utility, and how it interacts
   with Python's ssl module.
3. Trace the full error propagation chain: Python ssl module raises
   SSLCertVerificationError -> urllib3 catches and wraps in MaxRetryError ->
   requests catches and wraps in SSLError -> user sees nested exception.
   Document each file and function in the chain.
4. Identify why REQUESTS_CA_BUNDLE might not take effect — examine the
   precedence of verify parameter, environment variables, certifi fallback,
   and how the merge_environment_settings method resolves the final CA bundle
   path. Determine conditions where the env var is silently overridden.

Write your analysis to /workspace/ERROR_PROVENANCE.md with:

- Full error chain (file:function at each step)
- Error origin in urllib3/Python ssl module
- CA bundle resolution logic in requests
- Conditions where REQUESTS_CA_BUNDLE is silently ignored
