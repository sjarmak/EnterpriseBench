# Config Drift: Flask config layering between default_config and environment

## Background
A Flask application uses multiple configuration layers:
1. `app.config.from_object('default_settings')` sets defaults
2. `app.config.from_envvar('APP_SETTINGS')` overrides with env-specific config
3. Some config keys are also set via `app.config['KEY'] = value` directly

After a deployment, `SECRET_KEY` and `SESSION_COOKIE_SECURE` are not being overridden as expected from the environment config file. The defaults are leaking through.

## Task
1. Examine Flask's configuration system: how `Config` class handles layered loading
2. Identify the drift points where config values from `from_object` vs `from_envvar` may conflict
3. Determine the correct override chain and where the precedence logic lives
4. For each drift point, specify the config key, expected behavior, and actual behavior

Write your analysis to `/workspace/agent_output/answer.json`:
```json
{
  "drift_points": [
    {
      "key": "<config key>",
      "file": "<source file path>",
      "expected": "<expected override behavior>",
      "actual": "<actual behavior>",
      "override_chain": ["default_settings -> env_settings -> ..."]
    }
  ],
  "override_chain": ["from_object", "from_envvar", "direct assignment"],
  "fix": "description of correct usage"
}
```

The repository is available at `/workspace/flask/`.
