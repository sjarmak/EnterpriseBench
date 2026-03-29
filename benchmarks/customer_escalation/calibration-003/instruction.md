# Support Ticket: Proxy-Authorization header removed silently

**Priority:** High
**Submitted by:** Infrastructure Engineer
**Product:** Python HTTP client using requests

---

Hi team,

After upgrading to requests 2.26+, our proxy authentication stopped working. We manually set the `Proxy-Authorization` header in our requests:

```python
headers = {"Proxy-Authorization": "Basic dXNlcjpwYXNz"}
requests.get("https://example.com", headers=headers, proxies={"https": "http://proxy:8080"})
```

The header is silently stripped from the request before it reaches the proxy. This worked fine in 2.25.x.

We need to know:
1. Where in the requests source code the Proxy-Authorization header is removed
2. What logic decides to strip this header
3. Under what conditions is the header preserved vs. stripped

The repository is available at `/workspace/requests/`.
