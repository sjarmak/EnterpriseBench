# Support Ticket: Spreadsheet formulas giving wrong numbers

**Priority:** Critical
**Submitted by:** Finance Department
**Product:** LibreOffice Calc

**Codebase:** Available at `/workspace/core/`

---

Hi,

We have a serious problem with our spreadsheets in LibreOffice Calc. Our finance team uses large spreadsheets with SUM formulas to calculate monthly totals, and the numbers are coming out wrong.

When we change a value in a cell that's part of a SUM range, the SUM doesn't always update. Sometimes it shows the old total, sometimes it shows a number that doesn't match what we get when we add the cells up manually. If we close and reopen the file, the totals fix themselves, but then they go stale again as we make edits.

This is really concerning because we rely on these spreadsheets for financial reporting. We've been cross-checking everything by hand but that defeats the purpose of using formulas.

The problem seems worse in larger spreadsheets with lots of formulas that reference each other. Our smaller files seem fine. We're not sure if this is a calculation bug or if the spreadsheet isn't realizing it needs to recalculate when we change things.

Can you help us understand what part of the code handles formula calculation and when cells decide to recalculate? We need to know if this is a known issue and what's going on under the hood.

Thank you,
Dana
