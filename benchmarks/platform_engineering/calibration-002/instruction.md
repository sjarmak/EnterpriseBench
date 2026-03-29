# Config Drift: Click parameter source precedence between envvar and default

## Background
A Click CLI tool uses multiple parameter sources:
1. Command-line arguments (highest priority)
2. Environment variables via `envvar` parameter
3. Default values via `default` parameter
4. Prompt fallback via `prompt` parameter

After adding environment variable support to an existing option, the default value is no longer respected as a fallback when the env var is unset. Instead, Click prompts the user.

## Task
1. Examine Click's parameter resolution system in `core.py`
2. Identify how parameter sources are prioritized (CLI > envvar > default > prompt)
3. Find drift points where the precedence order breaks or behaves unexpectedly
4. Determine where `resolve_envvar` and `consume_value` interact with defaults

Write your analysis to `/workspace/agent_output/answer.json`:
```json
{
  "drift_points": [
    {
      "key": "<parameter/option name>",
      "file": "<source file path>",
      "expected": "<expected resolution order>",
      "actual": "<actual behavior>",
      "override_chain": ["cli_arg -> envvar -> default -> prompt"]
    }
  ],
  "override_chain": ["command_line", "envvar", "default", "prompt"],
  "fix": "description of correct parameter source configuration"
}
```

The repository is available at `/workspace/click/`.
