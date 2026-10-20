---
name: ai-testing
description: How to test AI / LLM features inside a product — types (chatbot/assistant, RAG over documents, generation/summarization/classification, agents with tools, semantic search); what to test beyond the happy path (quality and correctness with a golden set, hallucinations and grounding/citations, retrieval relevance in RAG, consistency and variability by temperature, output format and schema —valid JSON, fields—, language and tone, correct refusals for out-of-scope or harmful requests); prompt security (direct prompt injection and indirect injection via documents, jailbreak, system prompt leakage, leakage of PII or another user's data, misuse of the agent's tools); robustness (empty, extremely long, adversarial, other-language inputs, odd characters), context limits and truncation, latency and cost/tokens, provider error handling (rate limit, timeout, fallback), privacy and what is logged or sent to the provider, bias and toxicity, multi-turn conversations and memory; evals (golden set with criteria, LLM-as-judge and its limits, accuracy/groundedness/relevance metrics, regression when the prompt or model changes); test data, how to automate (endpoint with api-runner or UI with Playwright, repeat N times because of variability), typical bugs and questions for the PO. Used by the ai-tester.
---

# Testing AI / LLM features

An LLM feature is **non-deterministic**: the same input can produce different outputs, and "it works" is not enough. It is tested with a **golden set** (cases with criteria for what a good answer is), plus prompt security and robustness. Complemented by `design-techniques` and, for the conversational UI part, by web testing.

## 1. Feature type

- **Chatbot / assistant** (conversational, multi-turn).
- **RAG** (answers based on retrieved documents/knowledge base).
- **Generation / summarization / classification / extraction** (a specific task).
- **Agent with tools** (calls APIs/actions as the model decides).
- **Semantic search** (embeddings, ranking).

Confirm which one it is: it changes what is measured (e.g. RAG measures retrieval; a classifier measures accuracy against labels).

## 2. Quality and correctness (golden set)

- Build a **golden set**: representative inputs with the **criterion** for a good answer (expected answer, or rules: "must cite the source", "must not give prices", "JSON format with fields X/Y").
- Measure **accuracy** (classification/extraction against labels) or quality (with a rubric). Set a **target** (e.g. 90%); below it is a finding.
- **LLM-as-judge** can be used as an automatic judge, knowing its limits (bias, inconsistency): for critical items, human review.

## 3. Hallucinations and grounding

- **Hallucination**: it invents data, sources or features that do not exist. Try **out-of-domain** questions and questions about data it does not have: it should say "I don't know" / redirect, not invent.
- In **RAG**, **grounding**: the answer relies on the retrieved documents and **cites** them; if retrieval brings nothing relevant, it should not answer anyway.
- **Retrieval**: the retrieved chunks are the right ones (recall), and a document without the answer does not produce a false answer.

## 4. Consistency, format and language

- **Variability**: repeat the same case N times; with temperature > 0 it varies. For outputs that feed a system, it should be **stable** (low temperature or 0).
- **Format and schema**: if it returns JSON, it must be **valid and have the expected fields**, always (even with odd inputs); no extra text around it.
- **Language and tone**: it answers in the user's language and with the agreed tone; it does not switch languages on its own.

## 5. Prompt security

The most specific and dangerous part of an LLM:

- **Direct prompt injection**: the user writes "ignore the previous instructions and…". It must not obey over the system rules.
- **Indirect prompt injection**: instructions hidden in a **document, page or piece of data** the model processes (in RAG or agents). Very dangerous: try a document with "if they ask you X, answer Y / send the data to…".
- **Jailbreak**: workarounds to make it do what is forbidden (roleplay, encoding, language).
- **Leakage of the system prompt** or of **other users' data / PII**: it must not reveal its prompt nor mix context between users/sessions.
- **Agents with tools**: they must not run dangerous actions at the user's request (delete, pay, send emails) without proper authorization.

## 6. Robustness, limits and errors

- **Inputs** that are empty, extremely long (exceeds the context → controlled truncation, not an ugly error), in another language, with emojis/control characters, code, or adversarial.
- **Context limit**: what happens when the conversation or the document does not fit.
- **Provider errors**: rate limit, timeout, 500: the app degrades with a clear message and, if available, a **fallback** (another model / default answer); it does not hang.

## 7. Latency, cost and privacy

- **Latency** per answer (and time-to-first-token if there is streaming) and **cost/tokens** per interaction; flag a feature that is expensive or slow.
- **Privacy**: which user data is sent to the provider and what is **logged** (no PII or secrets in logs); compliance (e.g. not sending sensitive data to an external provider when not appropriate).
- **Bias and toxicity**: discriminatory or offensive answers to neutral inputs.

## 8. Multi-turn and memory

- It keeps the context throughout the conversation, does not "forget" nor carry data from one session to another; it resets properly when it should.

## 9. Evals and regression

- The golden set is a **regression suite**: when the **prompt**, the **model** or the **RAG pipeline** changes, run it again and compare (did it improve or get worse?).
- Version the set and the metrics; a model change that raises cost or lowers accuracy is a finding.

## 10. Test data

- **Canonical** cases (the expected), **edge** cases (ambiguous, incomplete), **adversarial** cases (injection, jailbreak, toxic) and **out-of-domain** cases. The `test-data-generator` builds them.

## 11. Automate

- Hit the feature's **endpoint** with the `api-runner` (a collection with the set's prompts and validations of the answer), or the chat **UI** with Playwright (`e2e-execution`).
- **Repeat each case N times** to measure variability; do not evaluate a single run.
- Save prompt + answer as evidence (without PII).

## 12. Typical AI bugs

- It hallucinates data or cites sources that do not exist; in RAG it answers even though retrieval brought nothing.
- It obeys a **prompt injection** (direct or hidden in a document).
- It reveals the system prompt or another user's data.
- It returns invalid JSON or JSON with extra text that breaks the consumer.
- It varies too much between runs in an output that should be stable.
- It hangs or shows a raw error on a provider timeout/rate limit.
- It sends PII to the provider or leaves it in the logs.
- It switches language or tone on its own.

## 13. Typical questions for the PO (AI)

When it is not written down, they are `MI-XX`:

- What type of feature is it (chatbot, RAG, classifier, agent) and which model/provider does it use?
- What is the **criterion for a good answer** and the accuracy/quality target?
- What must it NOT do (forbidden topics, actions that require authorization)?
- Which sources does the RAG use and how is grounding measured?
- Which user data can be sent to the provider and what can be logged?
- Is there a fallback if the provider fails? Cost/latency limits?
