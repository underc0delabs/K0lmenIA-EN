---
name: async-testing
description: How to test messaging and event systems (asynchronous / event-driven) — brokers and protocols (Apache Kafka, RabbitMQ/AMQP, AWS SQS/SNS, Google Pub/Sub, MQTT for IoT, WebSockets and Server-Sent Events), patterns (producer/consumer, pub/sub, work queues, event sourcing, streams); what to test beyond the happy path — delivery (at-least-once, at-most-once, exactly-once and why it is almost never real), ordering (per partition/key vs. global), idempotency and deduplication (idempotency keys, processing the same event twice), retries and backoff, dead-letter queues (DLQ) and poison messages, schemas and compatibility (Avro/Protobuf/JSON Schema, Schema Registry, backward and forward changes), partitions and keys (consumer groups, rebalancing, consumer lag), slow consumers and backpressure, duplicated/out-of-order/lost messages, TTL and expiration, transactions and the outbox pattern, correlation and traces (correlation id), security (TLS, SASL/ACLs, signing), WebSocket/SSE (reconnection, heartbeat, backpressure, authorization); how to automate it (publish/consume/inspect with the messaging tool, verify order/duplicates/schema), typical bugs and questions for the PO. Used by the messaging-tester.
---

# Messaging and event testing (async)

Async is not tested like a request/response API: a producer **publishes** and a consumer **processes later**, perhaps several times, out of order or never. What matters is **delivery, ordering, idempotency and what happens when something fails**. Complemented by `design-techniques` and, for whatever ends up in a database, by `data-verifier`.

## 1. Brokers and protocols

- **Kafka**: partitioned log; ordering **per partition**, consumer groups, offsets, consumer lag, retention.
- **RabbitMQ / AMQP**: queues and exchanges (direct, topic, fanout), ack/nack, DLX (dead-letter exchange), TTL, prefetch.
- **AWS SQS/SNS, Google Pub/Sub**: managed queues/topics, visibility timeout, DLQ, fan-out.
- **MQTT** (IoT): QoS 0/1/2, retained messages, last will, hierarchical topics.
- **WebSocket / SSE**: real time over HTTP; reconnection, heartbeat, backpressure, per-connection authorization.

Confirm which one it is: it changes which guarantees exist (e.g. Kafka orders per partition, not globally).

## 2. Delivery and guarantees

- **At-least-once** is the norm: a message can be delivered **more than once** → the consumer **must be idempotent**. Test it by resending the same event.
- **Exactly-once** is rarely real end to end: confirm what the system really guarantees and test the double-delivery case.
- **Lost message**: a consumer that fails **after** processing but **before** the ack — does it reprocess or lose it? An ack before processing loses messages on a crash.

## 3. Ordering

- Ordering is usually guaranteed **per key/partition**, not globally. Events of the **same entity** (e.g. an order) must be processed in order; for different entities it does not matter.
- Test out-of-order events (a "cancelled" that arrives before the "created"): the consumer must not leave an inconsistent state.

## 4. Idempotency and deduplication

- Resend the same event (same idempotency key / id): **a single effect** (one payment, one record), not two.
- Dedup by time window, by persisted id, or by the broker's key; test the edges of that window.

## 5. Retries, backoff and DLQ

- A failing consumer must **retry with backoff**, not in a tight loop (retry storm).
- After N failures, the message goes to the **DLQ** (dead-letter); it is not lost and does not block the queue. Test a **poison message** (one that always fails): it must not stop the rest.
- Check the DLQ: messages there = something was not processed; there should be a way to reprocess them.

## 6. Schemas and compatibility

- With **Schema Registry** (Avro/Protobuf) or **JSON Schema**: a message that does not match the schema is rejected; it does not break the consumer.
- **Compatibility**: adding a field (backward), removing one, changing a type. A new producer must not break an old consumer (or vice versa), according to the compatibility policy.

## 7. Partitions, consumer lag and backpressure

- **Consumer lag**: if the consumer cannot keep up, the lag grows; measure it under load (with `performance-mapper`).
- **Rebalancing** when adding/removing consumers: messages are neither duplicated nor lost during the reassignment.
- **Slow consumer / backpressure**: the system does not crash or accumulate without limit.

## 8. Transactions and outbox

- If a service writes to its database **and** publishes an event, they must be atomic (otherwise it publishes without saving, or the other way around). The **outbox pattern** solves this: verify there are no events published without their change in the database (or vice versa), cross-checking with `data-verifier`.

## 9. Correlation and traces

- Each event carries a **correlation id** that travels through the whole chain; it is used to follow a flow that goes through several services/queues. Verify that it is propagated.

## 10. Security

- **TLS** in transit, authentication (SASL/mTLS) and **ACLs** per topic/queue (a service only publishes/consumes its own). On WebSocket/SSE, per-connection authorization and no leaking of messages from another user/room.

## 11. WebSocket / SSE

- Automatic **reconnection** after a network drop, without losing or duplicating; **heartbeat**/ping-pong; **backpressure** if the client is slow; clean close.
- Authorization: a client only receives the messages of its channel; try subscribing to someone else's.

## 12. Automate (messaging tool)

- `npm run messaging` (`tools/messaging/messaging.py`) publishes, consumes and inspects on Kafka, RabbitMQ, MQTT, WebSocket and SSE; the **pure** checks (order, duplicates, schema) do not depend on the broker and are applied to what was consumed.
- Pattern: **publish** a test event → **consume** at the other end → verify the effect (state, database with `data-verifier`), ordering and that it was not duplicated.
- For load and consumer lag, `performance-guide` + `performance-mapper`.

## 13. Typical messaging bugs

- **Non-idempotent** consumer: the same event processed twice charges/records twice.
- Ack before processing → messages lost on a crash.
- Events of the same entity processed **out of order** leave an inconsistent state.
- Poison message that **blocks the queue** (no DLQ) or a retry loop without backoff.
- Schema change that **breaks** old consumers.
- Event published **without** its change in the database (or vice versa): missing outbox/atomicity.
- WebSocket that does not reconnect or that delivers messages from another room.
- Consumer lag that grows under load with no alarm.

## 14. Typical questions for the PO (async)

When it is not written down, they are `MI-XX`:

- Which broker/protocol and which delivery guarantee is expected (at-least-once, exactly-once)?
- Does ordering matter and by which key? Which events exist for the same entity?
- Is the consumer idempotent? Which key does it deduplicate by?
- What happens to a message that always fails? Is there a DLQ and reprocessing?
- Is there a Schema Registry and what compatibility policy?
- Is the outbox pattern used to publish + persist?
