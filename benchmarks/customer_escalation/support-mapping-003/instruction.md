# Support Ticket: Dashboards lose all their formatting after import

**Priority:** Medium
**Submitted by:** Platform Analytics Team
**Product:** Grafana (self-hosted)

---

Hi there,

We're trying to migrate dashboards from our staging Grafana instance to production. We export the dashboard as JSON from staging, then import it into production. The panels all show up and the queries work, but all the visual formatting is gone.

Specifically, our table panels lose their column widths, the text alignment resets to defaults, and some custom color thresholds we set up disappear. We spent a lot of time getting these dashboards looking right and now we have to redo all the formatting by hand every time we promote a dashboard.

This happens with every dashboard we import, not just one specific one. The JSON export looks fine when we inspect it -- all the settings are there in the file. But after import, those settings just vanish.

Is there something in the import process that strips out panel configuration? We need to understand what's happening so we can figure out a workaround.

Best,
Alex
