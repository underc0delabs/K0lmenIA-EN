---
name: graphql-testing
description: How to test GraphQL APIs — the schema and introspection (types, queries, mutations, subscriptions, deprecations), queries and mutations with variables, fragments, aliases and directives (@include/@skip), GraphQL's own error handling (always HTTP 200 with `errors` + partial `data`, not HTTP codes), nullability and partial errors that null out a field or the whole branch, pagination (cursor/Relay connections vs. offset), subscriptions over WebSocket, N+1 and the backend impact, depth and complexity/cost limits and rate limiting, per-field and per-type authorization (a field you shouldn't see), introspection disabled in production, persisted queries and APQ, operation batching, caching and invalidation, and how it differs from REST when approaching the tests; how to automate it (POST to /graphql with the api-runner/Newman, summarize the schema with summarize_graphql.py, k0lmena steps), typical bugs and questions for the PO. Used by the api-runner, the api-mapper and the api-case-generator, as well as the tester of any product with GraphQL.
---

# GraphQL API testing

GraphQL is not REST: there is **a single endpoint** (`/graphql`), the client asks for exactly the fields it wants, and **errors travel in the body** (`errors`) with HTTP **200**, not in the HTTP code. That changes how you test. It complements `api-execution` (execution) and `design-techniques` (test case design).

## 1. Schema and introspection

- The **schema** is the contract: types, `Query`, `Mutation`, `Subscription`, fields, arguments, enums, interfaces, unions and **deprecations** (`@deprecated`).
- **Introspection** (`__schema`, `__type`) lets you survey it; `scripts/summarize_graphql.py` summarizes it (from a URL, SDL or JSON).
- **Introspection in production**: it's usually disabled for security; in QA it's useful for building the test cases. Check what the policy is.

## 2. Queries and mutations

- **Queries** (read) and **mutations** (write): test every operation in scope with **variables** (not hardcoded in the query), **fragments**, **aliases** and **directives** (`@include(if:)`, `@skip(if:)`).
- Request different **subsets** of fields: the response returns exactly what was requested, no more, no less.
- **Mutations**: correct effect, idempotency where it applies, and that they return the new state.

## 3. Error handling (the biggest difference from REST)

- A response can contain **`data` and `errors` at the same time**: a field that fails becomes `null` and the error shows up in `errors` with its `path`, but the rest of the response still arrives (**partial error**).
- **Nullability**: if a **non-null** (`!`) field fails, the error **propagates upward** and nulls out the whole branch (up to a nullable field). Test that an error in an optional field doesn't take down the whole query.
- **Validation** errors (nonexistent field, wrong variable type, missing argument) → a GraphQL error, usually with HTTP 200 or 400 depending on the implementation.
- A business error should **not** be just a silent `null`: it must be in `errors` with a useful message/code.

## 4. Per-field and per-type authorization

- Authorization in GraphQL is **per field/type**, not per route: a user may see `user.name` but not `user.email`. Try requesting sensitive fields with a role that shouldn't see them → they must come back in `errors`/`null`, not leak.
- **IDOR**: request another user's resource by id.

## 5. Performance and backend abuse

- **N+1**: a query that requests a list with a related field can fire one backend query per element. Request large lists with nested fields and watch the impact (with `data-verifier`/perf).
- **Depth and complexity**: GraphQL allows very nested or expensive queries (even cycles between types). There must be a **depth limit**, a **complexity/cost** limit and **rate limiting**; try a deep/expensive query and verify that it gets rejected.
- **Batching**: several operations in one request; make sure it doesn't bypass the limits.

## 6. Pagination

- **Cursor/Relay** (`edges`, `node`, `pageInfo`, `hasNextPage`, `endCursor`) or **offset** (`limit/offset`): go through every page, the last one, an empty one, and an invalid cursor.

## 7. Subscriptions (real time)

- Over **WebSocket**: subscribe, receive the expected events, reconnection and per-subscription authorization (see `async-testing` for the WebSocket part).

## 8. Persisted queries, caching and versioning

- **Persisted queries / APQ**: if present, only pre-registered queries (by hash) are accepted; an arbitrary query is rejected.
- Per-field **caching** and its invalidation after a mutation.
- GraphQL **doesn't version** like REST: it evolves with deprecations; a `@deprecated` field keeps working until it is removed.

## 9. Automating

- **POST** to `/graphql` with `{ "query": "...", "variables": {...} }` and validate `data`/`errors` with the `api-runner` (Newman) or the **k0lmena GraphQL steps** (`k0lmena-automation`): `I send the GraphQL query:`, `the GraphQL response has no errors`, etc.
- Summarize the schema with `scripts/summarize_graphql.py` to build the test cases; the `api-case-generator` includes GraphQL cases (invalid variables, nonexistent fields, per-field authorization, partial errors, depth and pagination).

## 10. Typical GraphQL bugs

- A business error that arrives as a silent `null`, with nothing in `errors`.
- An error in a non-null field that **takes down the whole query** because of bad nullability.
- **No depth/complexity limit**: a nested query brings down the backend.
- Unresolved **N+1** (no dataloader): a list with relations fires hundreds of queries.
- Authorization per route instead of per field: a sensitive field leaks.
- Introspection enabled in production.
- Pagination that breaks on the last page or with an invalid cursor.

## 11. Typical questions for the PO (GraphQL)

When it isn't written down, they are `MI-XX`:

- Where is the endpoint, and is introspection enabled in QA? And in production?
- Which operations (queries/mutations/subscriptions) are in scope?
- Is authorization per field/type? Which fields are sensitive per role?
- Are there depth or complexity limits, or rate limiting?
- Do you use persisted queries / APQ?
- Which pagination (cursor/Relay or offset)?
