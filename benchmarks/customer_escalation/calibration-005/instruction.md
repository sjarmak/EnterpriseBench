# Support Ticket: Internal Sentinel object leaks into Click callback

**Priority:** Medium
**Submitted by:** CLI Developer
**Product:** Click-based CLI tool

---

Hi support,

After upgrading Click to 8.3.x, our option callbacks started receiving a `Sentinel` object instead of `None` when no value is provided. Our callback code does `if value is None:` checks which now fail because it receives `Sentinel.UNSET` instead of `None`.

```python
@click.option('--format', callback=my_callback)
def cmd(format):
    pass

def my_callback(ctx, param, value):
    if value is None:  # This no longer works!
        return "default"
    return value
```

The `value` is now `<Sentinel.UNSET>` instead of `None`.

We need to know:
1. Which source files define and use the Sentinel object
2. The code path from option parsing to callback invocation that passes Sentinel
3. Whether this is intentional behavior or a bug

The repository is available at `/workspace/click/`.
