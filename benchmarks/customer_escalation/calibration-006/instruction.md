# Support Ticket: Blueprint.errorhandler restricts return type

**Priority:** Medium
**Submitted by:** Backend Developer
**Product:** Flask web application

---

Hi support,

We're trying to chain error handlers on a Blueprint. Our handler returns a tuple `(response, status_code)` but the type annotation on `Blueprint.errorhandler` restricts the return type, causing mypy errors and preventing us from chaining handlers that return different types.

```python
bp = Blueprint('api', __name__)

@bp.errorhandler(404)
def not_found(e):
    return {"error": "not found"}, 404  # Type error with strict checking
```

The app-level `errorhandler` works fine with tuple returns, but the Blueprint version seems more restrictive.

We need to know:
1. Where the `errorhandler` decorator is defined for Blueprints vs the App
2. What type restrictions are applied and where
3. How error handler results are processed differently between Blueprint and App

The repository is available at `/workspace/flask/`.
