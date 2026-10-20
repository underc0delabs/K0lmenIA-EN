---
name: ivr-testing
description: How to test voice systems, IVR and telephone conversational bots — the IVR menu tree (DTMF/tones and ASR speech recognition), prompts and TTS (clarity, language, pronunciation, barge-in/interruption), the call flow (welcome, menus, retries on no-input/no-match, timeouts, transfer to an operator, business hours), routing and queues (ACD, priority, hold music, overflow, callback), transfers (blind/consultative) and data that travels with the call (CTI/screen-pop), backend integration (phone lookups, PIN/voice authentication), telephony (SIP/VoIP, audio quality, latency, jitter, in-band DTMF vs. RFC2833, dropped calls), recording and compliance (consent, PCI for voice payments, not recording sensitive data), accessibility (TTY, speed), voicebots with NLU/LLM (intents, entities, fallback, confirmations), metrics (containment, abandonment, time in IVR), and how to automate (voice testing tools like Cyara/Hammer, or SIP scripts); typical bugs and questions for the PO. Used by the ivr-tester.
---

# Voice / IVR testing

An IVR (interactive voice response) is tested **over the phone**: the user listens to prompts and answers with **tones (DTMF)** or **voice**. What matters is that **the call isn't lost**, that the menu leads where it should, and that it reaches a human when needed. For the NLU/LLM part of a voicebot, it complements `ai-testing`.

## 1. The menu tree

- Map the **full tree**: every option of every menu, where it leads, and the submenus. Go through **every** branch, not just the main one.
- **DTMF**: every digit does what it says; an invalid digit gives the right message and retries.
- **Speech recognition (ASR)**: it understands the expected answers (and synonyms), with accents and background noise; `barge-in` (being able to speak/dial before the prompt ends).

## 2. Prompts and TTS

- The **prompts** are clear, in the right language, without cuts; the **TTS** pronounces names, numbers and amounts correctly.
- The **voice and tone** are consistent; the prompts match the real options (they don't say "press 3" if 3 doesn't exist).

## 3. Call flow and error handling

- **Welcome**, menus, and handling of **no-input** (the user doesn't answer) and **no-match** (answers something invalid): retries (usually 3) and then **transfer to an operator** or a polite ending, never an infinite loop or an abrupt hang-up.
- Reasonable **timeouts**; **reaching an operator** always available (press 0, or say "operator").
- **Business hours**: after hours, the right message and a callback/message option.

## 4. Routing, queues and transfers

- **ACD/queues**: routes to the right skill/queue, with priority; **hold music/messages**, position in the queue, **overflow** when no agents are available, and **callback** if it exists.
- **Transfers**: blind (direct) and consultative (the agent consults first); the **call data** (CTI/screen-pop: number, what was dialed, the identified customer) reaches the agent.

## 5. Backend integration and authentication

- Phone lookups (balance, order status): the data the IVR reads matches the backend.
- **Authentication** by PIN/ID number/voice: attempts, lockout, and that it doesn't read sensitive data aloud without identification.

## 6. Telephony and audio

- **SIP/VoIP**: the call connects, good **audio quality** (no echo, dropouts or robotic voice), acceptable **latency/jitter**.
- **DTMF**: tones are detected (in-band vs. RFC2833/SIP INFO); a common problem is that the IVR doesn't "hear" the digits.
- Dropped calls and reconnection; what happens if the user hangs up midway.

## 7. Recording and compliance

- Recording **consent** where the law requires it; the recording is actually stored and retrievable.
- **PCI** for voice payments: don't record the card number/CVV (pause the recording or use masked DTMF); no sensitive data in logs.

## 8. Voicebots (NLU / LLM)

- If there's a **voicebot** with NLU/LLM: intents and entities recognized, **fallback** when it doesn't understand, **confirmations** before actions with side effects, and no hallucinations (see `ai-testing` for the AI part).

## 9. Metrics

- **Containment** (how many calls the IVR resolves without an agent), **abandonment** (how many hang up in the IVR), **time in IVR** and in queue. A high abandonment rate in a menu signals a problem.

## 10. Automating

- **Voice testing** tools (Cyara, Hammer, Empirix) place automated calls and validate prompts/DTMF; alternatively, **SIP** scripts (e.g. with a softphone/SIPp) and audio validation. The agent orchestrates or documents these test cases; much of IVR testing is **assisted manual** (call and follow the script).

## 11. Typical IVR bugs

- A menu option that leads to the wrong branch or to a prompt that doesn't exist.
- No-match/no-input that loops or hangs up without transferring to an operator.
- DTMF not detected (tones ignored).
- A prompt that mentions options that no longer exist, or in another language.
- No way to reach a human.
- Recording of card data (PCI non-compliance).
- A transfer that loses the call data (the agent asks everything again).
- After hours without the right message.

## 12. Typical questions for the PO (IVR)

When it isn't written down, they are `MI-XX`:

- Do you have the IVR tree diagram and the expected prompts?
- Is input via DTMF, voice (ASR) or both? Which languages?
- How many retries before transferring to an operator? How do you reach a human?
- What are the business hours, and what happens after hours?
- Are there phone payments (PCI) or sensitive data?
- Is it a traditional IVR or a voicebot with NLU/LLM?
