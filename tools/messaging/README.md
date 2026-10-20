# Messaging and events (async)

Testing tool for **asynchronous / event-driven** systems: publishes, consumes and inspects messages on the most common brokers, and includes the QA checks that do not depend on the broker. Used by the `messaging-tester` agent.

- **`messaging.py`** (`npm run messaging`) — publishes/consumes/inspects on **Kafka** (kafka-python), **RabbitMQ/AMQP** (pika), **MQTT** (paho-mqtt), **WebSocket** (websocket-client) and **SSE** (stdlib). Includes **pure** checks (no broker): `verify_order`, `detect_duplicates` and `validate_schema`.

```bash
# Consume from a Kafka topic
npm run messaging -- --broker kafka --action consume --server localhost:9092 --destination orders --timeout 10
# Publish a test message to RabbitMQ (action with side effects: the agent confirms it)
npm run messaging -- --broker rabbitmq --action publish --server amqp://localhost --destination queue.orders --message '{"id":1}'
# Listen to a WebSocket
npm run messaging -- --broker websocket --action consume --destination wss://host/ws --timeout 15
```

`consume`/`inspect` are **read-only**; `publish` has side effects (it triggers consumers), so the agent confirms it and it is done against a **QA broker**, never production.

**Requirements (optional, per broker)**: `pip install kafka-python` (Kafka), `pip install pika` (RabbitMQ), `pip install paho-mqtt` (MQTT), `pip install websocket-client` (WebSocket). SSE needs nothing. Libraries are imported lazily: if one is missing, the tool tells you how to install it and does not break.
