# Support Ticket: Click flag_value with default=True ignores flag

**Priority:** Medium
**Submitted by:** CLI Developer
**Product:** Click-based CLI tool

---

Hi team,

We have a Click command with a boolean flag using `flag_value`:

```python
@click.option('--verbose/--no-verbose', flag_value=True, default=True)
```

When we pass `--no-verbose`, the flag still evaluates to True. It seems like the ordering of `flag_value` and `default` parameters matters in an undocumented way.

If we switch to:
```python
@click.option('--verbose/--no-verbose', default=True, flag_value=True)
```

It behaves differently. This is confusing and undocumented.

We need to know:
1. Where in the Click source code the `flag_value` parameter is processed
2. How `flag_value` interacts with `default` during option creation
3. Under what conditions the ordering matters

The repository is available at `/workspace/click/`.
