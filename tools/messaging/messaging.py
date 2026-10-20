#!/usr/bin/env python3
"""
Messaging / event (async) testing tool: publishes, consumes and inspects messages on the most common
brokers, and includes the QA checks that do not depend on the broker (order, duplicates, schema).

Usage (from the k0lmenIA repo root, against a QA broker):
    # Consume N messages from a Kafka topic for 10 s
    python tools/messaging/messaging.py --broker kafka --action consume --server localhost:9092 --destination orders --timeout 10
    # Publish a test message to a RabbitMQ queue (action with side effects: the agent confirms it)
    python tools/messaging/messaging.py --broker rabbitmq --action publish --server amqp://localhost --destination queue.orders --message '{"id":1}'
    # Listen to a WebSocket or an SSE stream
    python tools/messaging/messaging.py --broker websocket --action consume --destination wss://host/ws --timeout 15

Brokers: kafka (kafka-python), rabbitmq (pika), mqtt (paho-mqtt), websocket (websocket-client) and sse (stdlib).
Libraries are imported lazily: if one is missing, it tells you how to install it and the import does not fail.

`consume`/`inspect` are read-only; `publish` has side effects (it is confirmed). The order, duplicate
and schema checks (below) are pure and testable.
"""
import argparse
import json
import sys
import time
from pathlib import Path


# ------------------------------------------------------------------ pure checks (no broker)
def verify_order(expected, received):
    """Does the `expected` subsequence appear in `received` in that order? Returns (ok, detail)."""
    i = 0
    for m in received:
        if i < len(expected) and m == expected[i]:
            i += 1
    ok = i == len(expected)
    return ok, (f"{i}/{len(expected)} in order" if expected else "nothing expected")


def detect_duplicates(messages, key=None):
    """IDs that appear more than once (idempotency / at-least-once). `key`: function or field name."""
    def k(m):
        if key is None:
            return json.dumps(m, sort_keys=True) if isinstance(m, (dict, list)) else m
        if callable(key):
            return key(m)
        return m.get(key) if isinstance(m, dict) else None
    seen, dups = {}, []
    for m in messages:
        kk = k(m)
        seen[kk] = seen.get(kk, 0) + 1
    return [kk for kk, n in seen.items() if n > 1]


def validate_schema(message, required):
    """Required fields missing from the message (lightweight check, no dependencies)."""
    if not isinstance(message, dict):
        return list(required)
    return [c for c in required if c not in message or message.get(c) in (None, "")]


def _missing(lib, pip):
    return RuntimeError(f"The '{lib}' library is missing: install it with `pip install {pip}` (only for the matching broker).")


# ------------------------------------------------------------------ operations per broker (lazy import)
def _kafka(action, server, destination, message, n, timeout):
    try:
        from kafka import KafkaConsumer, KafkaProducer
    except ImportError:
        raise _missing("kafka", "kafka-python")
    if action == "publish":
        p = KafkaProducer(bootstrap_servers=server)
        p.send(destination, (message or "").encode("utf-8")).get(timeout=timeout)
        p.flush()
        return {"published": 1}
    c = KafkaConsumer(destination, bootstrap_servers=server, auto_offset_reset="earliest",
                      consumer_timeout_ms=int(timeout * 1000), enable_auto_commit=False)
    msgs = []
    for m in c:
        msgs.append(m.value.decode("utf-8", "replace"))
        if len(msgs) >= n:
            break
    c.close()
    return {"messages": msgs}


def _rabbitmq(action, server, destination, message, n, timeout):
    try:
        import pika
    except ImportError:
        raise _missing("pika", "pika")
    conn = pika.BlockingConnection(pika.URLParameters(server))
    ch = conn.channel()
    if action == "publish":
        ch.basic_publish(exchange="", routing_key=destination, body=(message or "").encode("utf-8"))
        conn.close()
        return {"published": 1}
    msgs, end = [], time.monotonic() + timeout
    while len(msgs) < n and time.monotonic() < end:
        method, _, body = ch.basic_get(queue=destination, auto_ack=False)
        if body is None:
            time.sleep(0.2)
            continue
        msgs.append(body.decode("utf-8", "replace"))
    conn.close()
    return {"messages": msgs}


def _mqtt(action, server, destination, message, n, timeout):
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        raise _missing("paho-mqtt", "paho-mqtt")
    host, _, port = server.partition(":")
    cli = mqtt.Client()
    cli.connect(host, int(port or 1883), keepalive=max(10, int(timeout) + 5))
    if action == "publish":
        cli.publish(destination, message or "")
        cli.disconnect()
        return {"published": 1}
    msgs = []
    cli.on_message = lambda c, u, m: msgs.append(m.payload.decode("utf-8", "replace"))
    cli.subscribe(destination)
    cli.loop_start()
    end = time.monotonic() + timeout
    while len(msgs) < n and time.monotonic() < end:
        time.sleep(0.2)
    cli.loop_stop()
    cli.disconnect()
    return {"messages": msgs}


def _websocket(action, destination, message, n, timeout):
    try:
        import websocket
    except ImportError:
        raise _missing("websocket", "websocket-client")
    ws = websocket.create_connection(destination, timeout=timeout)
    if message:
        ws.send(message)
    msgs = []
    end = time.monotonic() + timeout
    while len(msgs) < n and time.monotonic() < end:
        try:
            msgs.append(ws.recv())
        except Exception:
            break
    ws.close()
    return {"messages": msgs}


def _sse(destination, n, timeout):
    import urllib.request
    msgs = []
    with urllib.request.urlopen(destination, timeout=timeout) as r:
        end = time.monotonic() + timeout
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("data:"):
                msgs.append(line[5:].strip())
            if len(msgs) >= n or time.monotonic() > end:
                break
    return {"messages": msgs}


def run(broker, action, server, destination, message, n, timeout):
    if broker == "kafka":
        return _kafka(action, server, destination, message, n, timeout)
    if broker == "rabbitmq":
        return _rabbitmq(action, server, destination, message, n, timeout)
    if broker == "mqtt":
        return _mqtt(action, server, destination, message, n, timeout)
    if broker == "websocket":
        return _websocket(action, destination, message, n, timeout)
    if broker == "sse":
        return _sse(destination, n, timeout)
    raise RuntimeError(f"Unsupported broker: {broker}")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Messaging / event testing (publish, consume, inspect).")
    ap.add_argument("--broker", required=True, choices=["kafka", "rabbitmq", "mqtt", "websocket", "sse"])
    ap.add_argument("--action", default="consume", choices=["publish", "consume", "inspect"])
    ap.add_argument("--server", default="", help="broker bootstrap/URL/host (or the matching environment variable)")
    ap.add_argument("--destination", default="", help="topic / queue / URL (ws/sse)")
    ap.add_argument("--message", default="", help="payload to publish")
    ap.add_argument("--n", type=int, default=10, help="maximum number of messages to consume")
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--output", default="")
    args = ap.parse_args(argv)
    try:
        res = run(args.broker, args.action, args.server, args.destination, args.message, args.n, args.timeout)
    except RuntimeError as ex:
        print(f"[messaging] {ex}", file=sys.stderr)
        return 2
    except Exception as ex:
        print(f"[messaging] Error with {args.broker}: {ex}", file=sys.stderr)
        return 2
    data = {"broker": args.broker, "action": args.action, "destination": args.destination, **res}
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        p = Path(args.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"[messaging] Data in {p}", file=sys.stderr)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
