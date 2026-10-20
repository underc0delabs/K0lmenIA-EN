# API — Authentication

**Base URL:** `https://api.qarmy-demo.ar/v1`

---

## POST /auth/login

Logs in and returns a token.

**Request body** (JSON):

```json
{
  "email": "string (email format)",
  "password": "string"
}
```

**Responses:**

```
+--------------------+-----------------------------------------------+-----------------------------+
| Status             | Body                                          | When                        |
+====================+===============================================+=============================+
| `200 OK`           | `{ "token": "string (JWT)", "expiresIn": 1800 | Valid credentials           |
|                    | }`                                            |                             |
+--------------------+-----------------------------------------------+-----------------------------+
| `400 Bad Request`  | `{ "error": "Email or password with an        | Malformed body              |
|                    | invalid format" }`                            |                             |
+--------------------+-----------------------------------------------+-----------------------------+
| `401 Unauthorized` | `{ "error": "Invalid credentials" }`          | Email/password do not match |
+--------------------+-----------------------------------------------+-----------------------------+
| `423 Locked`       | `{ "error": "Account locked due to failed     | 3 failed attempts           |
|                    | attempts" }`                                  |                             |
+--------------------+-----------------------------------------------+-----------------------------+
```

---

## POST /auth/forgot-password

Requests that a recovery link be sent.

**Request body** (JSON):

```json
{ "email": "string" }
```

**Responses:**

```
+-------------------+------------------------------------------------+----------------------------------------+
| Status            | Body                                           | When                                   |
+===================+================================================+========================================+
| `200 OK`          | `{ "message": "If the email exists, a link was | Always (it does not reveal whether the |
|                   | sent" }`                                       | email exists)                          |
+-------------------+------------------------------------------------+----------------------------------------+
| `400 Bad Request` | `{ "error": "Email with an invalid format" }`  | Malformed email                        |
+-------------------+------------------------------------------------+----------------------------------------+
```
