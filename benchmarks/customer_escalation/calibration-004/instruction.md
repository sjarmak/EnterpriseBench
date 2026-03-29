# Support Ticket: request.endpoint always None in open_session

**Priority:** Medium
**Submitted by:** Backend Developer
**Product:** Flask web application

---

Hi team,

We implemented a custom `SessionInterface.open_session()` to route sessions to different backends based on the endpoint being accessed. However, `request.endpoint` is always `None` inside `open_session()`.

```python
class CustomSession(SessionInterface):
    def open_session(self, app, request):
        print(request.endpoint)  # Always None!
        # We want to route based on endpoint...
```

The endpoint is available later in the view function, but not during session opening. Is this by design or a bug? We need to understand the Flask request lifecycle to know when endpoint resolution happens relative to session creation.

We need to know:
1. Where in Flask source code `request.endpoint` gets populated
2. Where `open_session` is called in the request lifecycle
3. Why endpoint is not yet available at session open time

The repository is available at `/workspace/flask/`.
