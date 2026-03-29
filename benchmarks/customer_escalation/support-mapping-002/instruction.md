# Support Ticket: Build pipeline crashing with compiler error

**Priority:** High
**Submitted by:** Build Infrastructure Engineer
**Product:** Internal CI/CD Pipeline (LLVM-based toolchain)

**Codebase:** Available at `/workspace/llvm-project/`

---

Hello,

Our CI pipeline started crashing yesterday when building one of our internal projects. The build log shows the compiler dying with an assertion failure that says something about "Cannot expand this type" and then the whole thing aborts.

This is blocking all of our builds on the affected platform. It only happens when targeting one specific architecture -- our other build targets compile fine. We recently updated the compiler toolchain but nothing else changed in our source code.

The crash happens deep in the compilation process, not during parsing or anything obvious. It looks like it gets partway through generating machine code and then gives up.

We need to understand what part of the compiler is responsible for "expanding types" during code generation and why it would fail. Our team doesn't have deep compiler expertise so we need your help mapping this error to the right area of the codebase.

Thanks,
Priya
