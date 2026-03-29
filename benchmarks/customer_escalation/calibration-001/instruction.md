# Support Ticket: Nested Blueprint url_prefix ignored

**Priority:** Medium
**Submitted by:** Backend Developer
**Product:** Flask web application

---

Hi team,

We're building a modular Flask app using nested Blueprints. We have a top-level `api` blueprint with `url_prefix="/api"` and a nested `users` blueprint with `url_prefix="/users"`. When we register `users` inside `api`, the nested prefix is being ignored and routes end up at `/api/` instead of `/api/users/`.

```python
api_bp = Blueprint('api', __name__, url_prefix='/api')
users_bp = Blueprint('users', __name__, url_prefix='/users')
api_bp.register_blueprint(users_bp)
```

We expect routes in `users_bp` to be at `/api/users/<route>` but they appear at `/api/<route>`.

We need to know:

1. Where in the Flask source code the nested blueprint URL prefix resolution happens
2. How the `register_blueprint` method propagates (or fails to propagate) the url_prefix for nested blueprints
3. Under what conditions the nested prefix gets dropped

The repository is available at `/workspace/flask/`.
