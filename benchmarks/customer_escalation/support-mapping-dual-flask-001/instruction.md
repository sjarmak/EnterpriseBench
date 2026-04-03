# Map Flask user-reported routing 405 Method Not Allowed error to Werkzeug URL routing implementation

A customer support ticket reports:

    "After upgrading to Flask 3.0.0, our API endpoint /api/users/<id> returns
    '405 Method Not Allowed' for PUT requests that worked before. POST and GET
    still work fine. We haven't changed our route definitions. The error trace
    points to werkzeug.routing but we can't figure out what changed."

Your task is to map this user-reported routing error from the Flask application
layer down to Werkzeug's URL routing internals.

Your task:
1. Find where Flask handles route registration and method checking — trace from
   @app.route() decorator through the Flask.add_url_rule() method.
2. Find where Werkzeug implements URL rule matching and method validation — identify
   the Map, Rule, and MapAdapter classes that enforce HTTP method restrictions.
3. Trace the complete path: Flask route registration → Werkzeug Rule compilation →
   request dispatch → method validation → 405 error generation.
4. Identify what changed in Werkzeug 3.0.1 (or Flask 3.0.0) that could cause
   previously-working PUT requests to return 405 — look for changes in method
   inheritance, strict_slashes behavior, or Rule.methods handling.

Write your analysis to /workspace/SUPPORT_MAPPING.md with:
- Flask route registration code path (file:function)
- Werkzeug URL routing and method validation code (file:function)
- Complete error path from request to 405 response
- What changed that could cause the regression
