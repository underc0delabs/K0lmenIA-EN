# Test design techniques — detail

Extended reference for the `design-techniques` skill. For each technique: what it is, when to use it, how to apply it, a worked example and common mistakes.

---

## 1. Equivalence classes (Equivalence Partitioning)

**What it is.** Split the universe of possible inputs into groups ("classes") that the system should treat the same way. If one value in the class works, all values in that class are assumed to work the same, so you test **one representative per class** instead of every value.

**When.** Inputs with ranges or categories; whenever testing "every value" is not feasible.

**How.**
1. For each input, identify the **valid** classes (what the system accepts) and the **invalid** ones (what it must reject).
2. Pick a representative for each class.
3. Generate one case per representative.

**Example — "age" field (accepts 18 to 65).**

```
+------------------------+-----------------+------------+
| Class                  | Representative  | Expected   |
+========================+=================+============+
| Valid (18–65)          | 40              | Accepted   |
+------------------------+-----------------+------------+
| Invalid (below)        | 15              | Rejected   |
+------------------------+-----------------+------------+
| Invalid (above)        | 70              | Rejected   |
+------------------------+-----------------+------------+
| Invalid (non-numeric)  | "abc"           | Rejected   |
+------------------------+-----------------+------------+
```

Four cases cover the behavior, instead of dozens.

**Common mistakes.** Testing only valid classes and forgetting the invalid ones. Lumping into a single class things the system distinguishes (e.g. "empty" and "invalid format" are usually different classes).

---

## 2. Boundary values (Boundary Value Analysis)

**What it is.** Defects concentrate at the **edges** of ranges (`<` vs `<=` errors, off-by-one). You test the values at the boundary and their immediate neighbors.

**When.** Whenever there is a numeric, date or length range. It complements equivalence classes.

**How.** For a range [min, max], test **min−1, min, min+1** and **max−1, max, max+1**.

**Example — password of 8 to 16 characters.**

```
+------------+---------+------------+
|     Length | Point   | Expected   |
+============+=========+============+
|          7 | min−1   | Rejected   |
+------------+---------+------------+
|          8 | min     | Accepted   |
+------------+---------+------------+
|          9 | min+1   | Accepted   |
+------------+---------+------------+
|         15 | max−1   | Accepted   |
+------------+---------+------------+
|         16 | max     | Accepted   |
+------------+---------+------------+
|         17 | max+1   | Rejected   |
+------------+---------+------------+
```

**Common mistakes.** Testing only "inside" and "outside" far from the edge (e.g. 5 and 20) and missing the off-by-one between 7/8 and 16/17.

---

## 3. Decision table

**What it is.** A table that crosses **conditions** (inputs) with **actions** (results), with one column per relevant combination. It makes explicit the business rules that depend on several conditions.

**When.** When the result depends on **several combined conditions** ("if A and B then C").

**How.**
1. List the conditions and the actions.
2. Build one column per combination of conditions (Yes/No).
3. Define the expected action for each column.
4. Each column is a case.

**Example — discount: "premium" customers get 10%; purchases over $10,000 add 5%.**

```
+---------------------+------+------+------+------+
| Condition / Rule    | R1   | R2   | R3   | R4   |
+=====================+======+======+======+======+
| Is premium?         | No   | No   | Yes  | Yes  |
+---------------------+------+------+------+------+
| Purchase > $10,000? | No   | Yes  | No   | Yes  |
+---------------------+------+------+------+------+
| **Discount**        | 0%   | 5%   | 10%  | 15%  |
+---------------------+------+------+------+------+
```

Four cases cover all combinations.

**Common mistakes.** Omitting combinations (testing only premium + expensive and non-premium + cheap). Not simplifying when a condition is irrelevant to the result.

---

## 4. State transition

**What it is.** Model the system as **states** and **events** that move it from one to another. You test the valid transitions and, above all, the **invalid** ones (events not allowed in a state).

**When.** Flows with states: orders, subscriptions, sessions, lockouts.

**How.**
1. List the states and the events.
2. Map which event leads from which state to which (and which are not allowed).
3. Test each valid transition and also the attempts at invalid transitions.

**Example — account lockout after 3 failed attempts.**
- States: *Active*, *Locked*.
- *Active* + 3 failed logins → becomes *Locked*.
- *Active* + correct login → stays *Active* (the attempt counter resets to 0).
- *Locked* + correct login → **rejected**: while locked you can't get in, even if the password is valid (invalid transition).
- *Locked* + waiting N minutes → back to *Active* (if the rule defines it).

**Common mistakes.** Testing only the path that locks the account and not what happens **while** it is locked. Forgetting the counter reset after a successful login.

---

## 5. Pairwise (reduced combinatorics)

**What it is.** When there are many independent parameters, testing **all** combinations explodes. Pairwise covers **all pairs** of values between parameters —where most defects show up— with far fewer cases.

**When.** Several independent parameters with several values each (configurations, compatibility).

**How.** List the parameters and their values, and build a minimal set of combinations that includes each pair (a value of A together with a value of B) at least once. There are tools that generate it (PICT, AllPairs).

**Example — browser (Chrome, Firefox, Safari) × OS (Windows, macOS) × language (ES, EN).**
All combinations are 3 × 2 × 2 = 12. With pairwise all pairs are covered in about 6 cases, while keeping good coverage.

**Common mistakes.** Using pairwise when the parameters are **not** independent: if certain combinations have their own rules, those go in a decision table.

---

## How to combine them

A single one is rarely used. The typical approach:

- For each field: **equivalence classes** + **boundary values**.
- If there are combined rules: **decision table**.
- If there is a flow with states: **state transition**.
- If there are many configurations: **pairwise**.

And always: negative and edge cases, not just the happy path; whatever is not defined is recorded as `MI-XX` (Missing information) with its question for the PO.
