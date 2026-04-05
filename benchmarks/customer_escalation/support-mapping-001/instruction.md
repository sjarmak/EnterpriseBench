# Support Ticket: Services failing to connect to backend

**Priority:** High
**Submitted by:** DevOps Team Lead
**Product:** Internal API Gateway (Envoy-based)

---

Hi support,

We've been seeing intermittent failures hitting our backend services through the proxy layer. During peak traffic windows (usually around 2-4pm), a bunch of requests start failing and our monitoring shows the error "upstream connect error or disconnect/reset before headers. reset reason: overflow."

It seems like the proxy is refusing to send requests through even though the backend services themselves are healthy and responding fine when we curl them directly. The problem goes away after traffic dies down but comes back every day during peak hours.

We haven't changed any configuration recently. Our backends are running fine -- CPU and memory look normal. It's the proxy layer that seems to be dropping things on the floor.

Can you help us figure out what part of the proxy codebase is responsible for this "overflow" reset and what controls the limits? We need to understand the code path so we can tune the right settings.

Also, please identify any related source files, documentation, or components that are relevant to understanding the full picture (e.g., configuration schemas, related circuit-breaking mechanisms, connection pool internals).

Thanks,
Jordan
