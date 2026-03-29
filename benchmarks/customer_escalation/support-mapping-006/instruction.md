# Support Ticket: Browser crashes on certain web pages

**Priority:** High
**Submitted by:** QA Tester
**Product:** Firefox (internal deployment)

---

Hi,

We've been getting reports from several users that Firefox is crashing when they visit certain internal web pages. It doesn't happen on every page -- just ones that our designers built with heavy use of CSS animations and transitions.

The crash happens after the page starts loading. You can see the content begin to render and then the whole browser tab crashes. Sometimes it takes the entire browser down with it. Chrome handles the same pages fine.

We tried simplifying the CSS on one of the affected pages and found that removing the animated properties that use calc() values in their keyframes prevents the crash. But our designers use calc() extensively for responsive layouts and we can't just remove it everywhere.

The crash reports don't give us much to work with from the user side. We need someone to look at what part of the browser engine handles CSS calc() during animations and figure out where it's going wrong.

This affects about 30% of our internal tool pages.

Thanks,
Riley
