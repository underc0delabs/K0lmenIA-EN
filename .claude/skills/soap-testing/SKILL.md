---
name: soap-testing
description: How to test SOAP web services — the WSDL (operations, messages, bindings, endpoint, port types), the SOAP envelope (Envelope, Header, Body), SOAPAction, SOAP 1.1 vs. 1.2, the types of the embedded XML Schema (XSD) (types, nillable, minOccurs/maxOccurs, enumerations, arrays), SOAP Faults (faultcode/faultstring/detail in 1.1; Code/Reason in 1.2) and how business errors are mapped, validation against the schema (request and response), namespaces and prefixes, WS-Security (UsernameToken, signature, timestamps, nonce), the mustUnderstand attribute of the headers, MTOM/attachments, WS-* (WS-Addressing, WS-ReliableMessaging), contract versioning and compatibility, idempotency of operations, authentication and transport security; how to automate it (survey the WSDL with the soap tool, build the envelope and send it over HTTP with the api-runner/Newman, or SoapUI), typical bugs and questions for the PO. Used by the soap-tester; complements the REST/GraphQL API agents.
---

# SOAP service testing

SOAP is a **strong, XML-based contract**: the **WSDL** defines exactly the operations, the types and the errors. Unlike REST, almost everything is validated against the **schema (XSD)**, and business errors travel as **SOAP Faults**, not as HTTP codes. It is complemented by `design-techniques` and by the API agents for the transport part.

## 1. The WSDL

- Defines **operations** (portType/binding), their input/output **messages**, the **endpoint** (address location) and each operation's **SOAPAction**.
- The `npm run soap` tool (`tools/soap/wsdl.py`) surveys it: service, endpoint, version (1.1/1.2) and operations, and generates a **sample envelope** per operation.
- A WSDL that doesn't load, with broken types or endpoints pointing to another environment, is a finding before testing.

## 2. The SOAP envelope

- **Envelope → Header + Body**. The Body carries the operation and its parameters; the Header, metadata (security, addressing).
- **SOAP 1.1 vs. 1.2**: the Envelope namespace, the content-type (`text/xml` vs. `application/soap+xml`) and how SOAPAction is sent all change. Confirm the version.
- **Namespaces and prefixes**: they have to match the WSDL; a wrong namespace makes the operation fail even though the XML "looks fine".

## 3. Validation against the schema (XSD)

- The **request** must comply with the XSD: correct types, required fields (minOccurs), `nillable`, enumerations, lengths, element order (sequence).
- Test with **invalid values** (wrong type, out of range, required field absent, nonexistent enumeration, bad date): the service must reject with a clear Fault, not with a generic 500.
- The **response** must also comply with the schema; a response that doesn't validate is a bug in the service.

## 4. SOAP Faults (error handling)

- Errors go as a **Fault**: in 1.1 `faultcode`/`faultstring`/`detail`; in 1.2 `Code`/`Reason`/`Detail`.
- Each expected business error (not found, not authorized, validation) must return a **Fault with the correct code and detail**, not a bare HTTP 500 or a 200 with a hidden error message.
- Test the difference between a **client fault** (bad data) and a **server fault** (internal error).

## 5. Security (WS-Security)

- **WS-Security UsernameToken** (user/password in the header, with nonce and timestamp), **signature** (XML Signature) and **encryption** (XML Encryption).
- **Timestamp/nonce** against replay: an old or repeated message must be rejected.
- `mustUnderstand="1"` on a header: if the service doesn't understand it, it must fail, not ignore it.
- **Transport**: TLS; credentials not in the URL; an endpoint without security that should have it is a finding.

## 6. Types, arrays and attachments

- **Arrays/collections** (maxOccurs), nested objects, complex types and `xsi:nil`; edges: empty list, one element, many.
- **MTOM/attachments** if it handles binary files.

## 7. Contract and compatibility

- **Versioning**: a change in the WSDL/XSD must not break old clients (adding an optional field is fine; removing one or changing a type breaks).
- **Idempotency**: resending the same write operation — does it duplicate? (especially without WS-ReliableMessaging).

## 8. Automate

- Survey the WSDL with `npm run soap`, take the sample envelope, fill in the parameters and **send it over HTTP POST** with the `api-runner` (a Postman/Newman collection with the XML in the body, the correct `Content-Type` and the `SOAPAction` header).
- Validate the response: that it is the expected XML, that it complies with the schema and that the Faults appear when appropriate. For large suites, SoapUI is an alternative.
- Test data: a valid value, one invalid by type, one with a required field absent, one that triggers each Fault.

## 9. Typical SOAP bugs

- A business error returned as **HTTP 500** or as 200 with a message, instead of a well-formed **SOAP Fault**.
- A valid request rejected because of a wrong **namespace/prefix**, or because of element order (sequence).
- The service **doesn't validate** the request against the XSD and processes invalid data.
- `mustUnderstand` ignored; timestamp/nonce not checked (replay).
- A response that **doesn't comply** with its own schema.
- The WSDL endpoint pointing to another environment; a WSDL that doesn't load.
- A **non-idempotent** write operation that duplicates on resend.

## 10. Typical questions for the PO (SOAP)

When it isn't written down, they are `MI-XX`:

- Where is the WSDL and what is the QA endpoint? SOAP 1.1 or 1.2?
- What security does it use (WS-Security UsernameToken, signature, TLS only)?
- Which operations are in scope and which have a side effect (write)?
- What Faults does each operation define and when must they be triggered?
- Is there contract versioning and old clients to keep compatible?
