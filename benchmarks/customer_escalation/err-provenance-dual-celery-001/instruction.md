# Trace Celery task retry storm to kombu connection pool exhaustion and ConnectionResetError origin

A customer reports that their Celery workers enter a "retry storm" where tasks
keep retrying indefinitely. The worker logs show:

    [2024-01-15 10:23:45,123: ERROR/ForkPoolWorker-1] Task
    myapp.tasks.process_order[abc-123] raised unexpected:
    ConnectionResetError(104, 'Connection reset by peer')

    [2024-01-15 10:23:45,456: WARNING/ForkPoolWorker-1] Task
    myapp.tasks.process_order[abc-123] retry: Retry in 60s

The RabbitMQ management UI shows the connection count climbing rapidly and
eventually hitting the configured limit (256 connections). The customer's task
is configured with `autoretry_for=(Exception,)` and `max_retries=10`.

The customer wants to understand why a connection pool issue in the message
broker layer triggers cascading retries instead of a clean failure.

Your task:

1. Find where Celery's task retry mechanism is implemented — trace from the
   task base class through the retry decision logic and how autoretry_for
   interacts with arbitrary exceptions like ConnectionResetError.
2. Find where kombu manages its connection pool and how connection exhaustion
   manifests — trace through the connection acquisition, heartbeat, and
   recovery mechanisms.
3. Trace the full error propagation chain: kombu connection pool exhaustion ->
   ConnectionResetError -> Celery worker catches exception -> autoretry_for
   matches -> retry publishes new message -> kombu connection pool is still
   exhausted -> cycle repeats. Document each file and function in the chain.
4. Identify why Celery's retry mechanism does not distinguish between
   task-level exceptions (which should retry) and broker-level connection
   errors (which should not) — examine the exception classification logic.

Write your analysis to /workspace/ERROR_PROVENANCE.md with:

- Full error chain (file:function at each step)
- Error origin in kombu connection pool
- Retry decision logic in Celery task base
- Why broker errors are not excluded from autoretry_for
