# Support Ticket: REQUESTS_CA_BUNDLE overrides verify=False

**Priority:** High
**Submitted by:** DevOps Engineer
**Product:** Python deployment scripts using requests

---

Hi support,

We set `session.verify = False` to skip TLS verification for internal services, but the `REQUESTS_CA_BUNDLE` environment variable is set globally in our CI environment. Even with `verify=False`, requests seems to pick up the CA bundle and fail when the internal cert doesn't match.

```python
session = requests.Session()
session.verify = False  # Should disable TLS verification
response = session.get("https://internal-service:8443/health")
# Still fails with SSL error when REQUESTS_CA_BUNDLE is set!
```

We need to know:
1. Where in the requests source code `REQUESTS_CA_BUNDLE` is read
2. How `session.verify = False` interacts with the environment variable
3. The precedence logic between explicit verify=False and env var

The repository is available at `/workspace/requests/`.
