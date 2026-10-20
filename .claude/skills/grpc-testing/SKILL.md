---
name: grpc-testing
description: How to test gRPC APIs and real-time services within the API family — Protocol Buffers (.proto, messages, fields and their numbers, scalar types, enums, oneof, repeated, map, well-known types), the four RPC modes (unary, server-streaming, client-streaming, bidirectional), gRPC status codes (OK, INVALID_ARGUMENT, NOT_FOUND, UNAUTHENTICATED, PERMISSION_DENIED, DEADLINE_EXCEEDED, RESOURCE_EXHAUSTED…) and their error mapping, metadata/headers and trailers, deadlines and cancellation, TLS/mTLS and token authentication, reflection vs. having the .proto, gRPC-Web, interceptors, Protobuf schema compatibility (never reuse field numbers, reserved fields, adding is compatible), large messages and limits, compression, keepalive, and how it relates to contract tests; plus WebSocket as a real-time API (see async-testing for the reconnection/ordering details). How to automate (grpcurl, Postman/grpc, Buf, generating test cases from the .proto), typical bugs and questions for the team. Used by the api-runner, the api-mapper and the api-case-generator.
---

# gRPC testing (and real-time APIs)

gRPC is not REST: it uses **HTTP/2 + Protocol Buffers** (binary), with a **strong contract in the `.proto`**, **four RPC modes** and **its own status codes** (not HTTP). It joins the API family (`api-execution`); for WebSocket, the details are in `async-testing`.

## 1. The contract: Protocol Buffers (.proto)

- The `.proto` defines services, methods (RPCs), messages, **fields with their number** (the number is the binary contract, not the name), scalar types, `enum`, `oneof`, `repeated` (lists), `map`, and the **well-known types** (`Timestamp`, `Duration`, `Any`, `Struct`).
- **Reflection**: if the server exposes it, you can list services/methods without the `.proto`; if not, you need the file.

## 2. The four RPC modes

- **Unary**: request → response (like a normal call).
- **Server-streaming**: one request → many responses (a stream that ends).
- **Client-streaming**: many requests → one response.
- **Bidirectional**: both streams at once.
- Each mode is tested differently: in the streaming ones, test the end of the stream, an empty stream, many elements, and **cancellation** midway.

## 3. Status codes and errors

- gRPC has **its own status codes**: `OK`, `INVALID_ARGUMENT`, `NOT_FOUND`, `ALREADY_EXISTS`, `UNAUTHENTICATED`, `PERMISSION_DENIED`, `DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED`, `UNAVAILABLE`, `INTERNAL`…
- Every business error must return the **correct status** with a useful message (and optionally rich details with `google.rpc.Status`), not a generic `INTERNAL` or an `OK` with an error inside.
- Try invalid inputs → `INVALID_ARGUMENT`; nonexistent resource → `NOT_FOUND`; no token → `UNAUTHENTICATED`; no permission → `PERMISSION_DENIED`.

## 4. Metadata, deadlines and cancellation

- **Metadata** (headers/trailers): authentication (token in `authorization`), correlation id, and trailers with information about the result.
- **Deadlines/timeouts**: the client sets a deadline; if the server takes longer, `DEADLINE_EXCEEDED`. Try a short deadline on a slow operation.
- **Cancellation**: if the client cancels, the server should stop working (not keep processing).

## 5. Security

- **TLS / mTLS** (client and server certificates); token authentication in metadata; a protected method must reject calls without credentials (`UNAUTHENTICATED`/`PERMISSION_DENIED`).
- **Limits**: maximum message size (`RESOURCE_EXHAUSTED` if exceeded), compression.

## 6. Schema compatibility (native contract testing)

- Protobuf compatibility is by **field number**: **adding** a new field is compatible; **reusing** an old number or **changing the type** of a field breaks old clients; removed fields must stay **reserved** (`reserved`).
- Changing an `enum` or a `oneof` carelessly breaks things. This is contract testing (see `contract-testing`): the `.proto` is the contract.

## 7. gRPC-Web and interceptors

- **gRPC-Web** for browsers (over HTTP/1.1 or 2 with a proxy): test that the proxy translates correctly and that errors get through.
- **Interceptors** (auth, logging, retry): make sure they don't alter the contract or swallow errors.

## 8. WebSocket (real-time API)

- For real-time APIs over **WebSocket** (subscriptions, push): reconnection without losing/duplicating, heartbeat, ordering and per-connection authorization — the details are in `async-testing`. Add it when the API has live channels.

## 9. Automating

- **grpcurl** (CLI) to invoke methods with the `.proto` or via reflection; **Postman** supports gRPC; **Buf** for linting and **breaking-change detection** of the `.proto`.
- The `api-case-generator` derives test cases from the `.proto` (per method and mode, expected statuses, validation, auth); the `api-runner` runs them; the `api-mapper` automates them in k0lmena.
- Test data: a valid request, one invalid by type/required field, one that triggers each status, an empty stream and a long one.

## 10. Typical gRPC bugs

- A business error returned as a generic `INTERNAL` or as `OK` with an error inside, instead of the correct status.
- Reusing a field's number or changing its type → breaks old clients (Protobuf incompatibility).
- Ignored deadline: the server keeps processing after `DEADLINE_EXCEEDED`.
- A stream that doesn't close properly or doesn't handle client cancellation.
- A protected method that responds without credentials.
- A message that exceeds the limit without a clear `RESOURCE_EXHAUSTED`.

## 11. Typical questions for the team

When it isn't written down, they are `MI-XX`:

- Do you have the `.proto`, or does the server expose reflection? Where is the QA endpoint?
- Which RPC modes does it use (unary/streaming)?
- Which status should each business error return?
- Does it use TLS/mTLS and authentication via metadata?
- Is there a `.proto` compatibility policy (Buf breaking)?
- Is gRPC-Web or WebSocket involved?
