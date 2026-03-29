# Support Ticket: Messages showing up on the wrong topic during maintenance

**Priority:** Critical
**Submitted by:** Data Platform Engineer
**Product:** Apache Kafka (self-managed cluster)

**Codebase:** Available at `/workspace/kafka/`

---

Hi,

We discovered a really alarming problem with our Kafka cluster. During planned broker restarts (rolling maintenance), some messages that producers send to topic A are ending up on topic B instead. We only caught it because our consumers on topic B started processing records with schemas that don't match that topic.

This doesn't happen during normal operation -- only when brokers are going down and coming back up. The producers get some connection errors during the restart (which we expect), but instead of just retrying the failed messages to the correct topic, it seems like the message data is getting mixed up somehow.

We've verified it's not a consumer-side issue. The messages are genuinely written to the wrong topic partition -- we can see them with kafka-console-consumer. It's intermittent and we can't reliably reproduce it, but it happens often enough during maintenance windows that we're very concerned about data integrity.

We're running the standard Java producer client. Can you help us understand what part of the producer code handles message buffering and sending, especially during connection failures? We suspect something is going wrong with how the producer manages its internal buffers when batches fail and get retried.

Regards,
Avery
