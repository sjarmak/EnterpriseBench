# Support Ticket: CliRunner.invoke raises ValueError on closed file

**Priority:** Medium
**Submitted by:** Test Engineer
**Product:** Click-based CLI test suite

---

Hi support,

When using `CliRunner.invoke()` with certain commands that read from stdin, we get a `ValueError: I/O operation on closed file` error. This happens intermittently:

```python
runner = CliRunner()
result = runner.invoke(my_cli, input="some data\n")
# Raises ValueError: I/O operation on closed file
```

It seems like the BytesIO/StringIO stream created for `input` is getting closed prematurely during invocation. The issue appears when the command tries to read from stdin after initial processing.

We need to know:
1. Where in Click source the CliRunner creates and manages the input stream
2. What code path leads to the stream being closed during invoke()
3. The interaction between CliRunner's stream handling and Click's internal I/O

The repository is available at `/workspace/click/`.
