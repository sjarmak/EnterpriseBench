# Support Ticket: Alert notifications coming late or not at all

**Priority:** High
**Submitted by:** SRE Team
**Product:** Grafana Alerting (self-hosted) with Alertmanager integration

---

Hi,

We're having a serious issue with our alerting setup. We have about 200 alert rules configured in Grafana and they've been working fine for months. Starting last week, some alerts are firing way later than expected -- like 10-15 minutes after the condition is met -- and a few don't seem to fire at all.

We checked the Grafana server logs and see warnings about "alert evaluation took longer than expected" but we're not sure what that means or what's causing it. The database and data sources all seem healthy. The Grafana server isn't running out of memory or CPU.

The weird thing is that simple alerts still work fine. It's mainly the ones with complex queries or rules that have multiple conditions that seem to be delayed. We haven't added many new rules recently, maybe 20 or so in the past month.

Additionally, for some alerts that DO fire in Grafana, the actual notifications never arrive. We use Alertmanager as our notification backend and we're seeing some alerts get routed but the notifications seem to get stuck or silenced unexpectedly. We checked and there are no active silences we created, but some alerts appear to be suppressed by the Alertmanager dispatch routing tree. We also noticed that a few notification integrations are timing out.

We need to understand:

1. What controls alert evaluation timing in Grafana's codebase? How does Grafana decide when to check each rule and what happens when a check takes too long?
2. How does the Alertmanager notification pipeline process alerts received from Grafana? Where could alerts get lost between Grafana firing and the notification actually being delivered?

Repos are available at:

- `/workspace/grafana/` — Grafana source (alert scheduler and evaluation engine)
- `/workspace/alertmanager/` — Prometheus Alertmanager source (dispatch routing and notification delivery)

Regards,
Marcus
