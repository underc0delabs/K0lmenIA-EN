---
name: contract-testing
description: How to do contract testing between services — consumer-driven contracts (Pact) vs. provider-driven ones, the consumer→broker→provider flow, what it covers and what it doesn't compared with E2E and integration tests, how to write consumer expectations (request/response, matchers by type and not by value), provider verification against the published pacts, the Pact Broker and can-i-deploy, versioning and tags per branch/environment, backward and forward compatibility as the API evolves, provider states, contracts for REST, GraphQL, messaging/events (async) and gRPC, bi-directional (comparing OpenAPI against the consumer), pitfalls (overly strict matchers, testing business logic in the contract, outdated pacts), tools (Pact, Spring Cloud Contract, Schemathesis/Dredd against OpenAPI) and questions for the team. Used by the contract-tester; complements the API and messaging agents.
---

# Contract testing

Contract testing verifies that **two services understand each other** without spinning up the whole system: the **consumer** declares what it expects from the API and the **provider** is verified against that expectation. It catches "the integration broke" without the slowness or fragility of an E2E test. Complemented by the API skills (`api-execution`, `graphql-testing`, `grpc-testing`) and `async-testing`.

## 1. What it is and what it isn't

- It **is not** an E2E or integration test: it doesn't validate business rules or real data, it validates **the shape of the exchange** (endpoints, fields, types, status, events).
- It catches compatibility-breaking changes (a renamed field, a changed type, a different status) **before** deploying.
- It doesn't replace the provider's functional tests; it complements them.

## 2. Consumer-driven (Pact)

- The **consumer** defines the contract: "when I request `GET /payment/123`, I expect `200` with `{id, status, amount}`". That generates a **pact** (a file).
- The **provider** is **verified** against that pact: it replays each interaction and confirms it responds as the consumer expects.
- That way the provider knows **whom it breaks** if it changes something: if a verification fails, there is a real consumer that would stop working.

## 3. The Pact Broker and can-i-deploy

- Pacts are published to a **Pact Broker** (or PactFlow), versioned by commit and **tagged** per branch/environment.
- **`can-i-deploy`**: before deploying, it asks the broker whether this version is compatible with what is on the other side in that environment. It is the real safety net of contract testing.
- **WIP/pending pacts** prevent a consumer's new pact from suddenly breaking the provider's build.

## 4. Matchers and provider states

- Expectations use **matchers by type** (it's a string, a number, an ISO date), **not by exact value**: if you match the literal value, the contract breaks with any different data (false positive).
- **Provider states**: "given that payment 123 exists" — the provider sets up that state before verifying the interaction. Without well-defined provider states, verification is fragile.

## 5. Versioning and compatibility

- The contract is the unit of compatibility: **adding an optional field** doesn't break; **removing a field, changing a type or a status** does. Test the API's evolution against old consumers.
- **Backward** (old consumer, new provider) and **forward** (new consumer, old provider) according to the deployment policy.

## 6. REST, GraphQL, messaging and gRPC

- **REST**: the classic (request/response).
- **GraphQL**: the contract is about the query and the shape of `data`/`errors` (see `graphql-testing`).
- **Messaging/events** (async): **message pacts** — the producer publishes an event with a certain shape and the consumer expects it that way (see `async-testing`); the broker is not in the loop, the message shape is verified.
- **gRPC**: the `.proto` is the contract; Protobuf compatibility (reserved fields, never reuse numbers) is native contract testing (see `grpc-testing`).

## 7. Bi-directional

- **Bi-directional contract testing**: compare the **provider spec** (OpenAPI) against the **consumer pact**, without the provider running the verification. Useful when the provider already has a reliable OpenAPI.

## 8. Tools

- **Pact** (multi-language) + **Pact Broker/PactFlow** is the consumer-driven standard.
- **Spring Cloud Contract** in the JVM world.
- **Schemathesis / Dredd** validate a running API against its **OpenAPI** (provider-first contract).
- The agent orchestrates these tools (with the `api-runner` for the HTTP part) and summarizes the result.

## 9. Pitfalls

- **Matchers by value** instead of by type → fragile contracts that fail with any data.
- Putting **business logic** in the contract (validating amounts, calculations): that is functional testing, not contract testing.
- **Outdated pacts**: a consumer that no longer exists leaves a pact that blocks the provider.
- Not using `can-i-deploy`: having pacts but deploying anyway without checking compatibility.
- Provider states not implemented → verifications that fail because of the state, not the contract.

## 10. Typical questions for the team

When it is not written down, they are `MI-XX`:

- Which services are consumer and provider, and which protocol (REST/GraphQL/gRPC/events)?
- Do you use Pact/PactFlow or another tool? Is there a broker?
- Is `can-i-deploy` run in the pipeline before deploying?
- Which compatibility policy (backward, forward)?
- Who defines the provider states and how are they set up?
