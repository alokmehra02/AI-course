# Authoring template (internal)

This file defines the exact structure every module in `System_Design_Prep/` must follow.
It exists so all modules read like one book, not 16 different blog posts.

**Audience:** Aalok — ~2 years experience, Node.js + Python/FastAPI + GCP + LLM apps.
He is preparing for **SDE-2 / mid-level backend + AI engineer** interviews.

**Goal of the material:** he should be able to open any topic 30 minutes before an
interview, read the "Say this" block out loud, and sound like someone who has run
the thing in production.

---

## File-level structure

Every module file starts with:

```markdown
# Module NN — <Title>

> **What this module makes you able to do:** <1-2 sentences, concrete>
>
> **Interview weight:** ★★★★★ (asked in almost every interview) / ★★★★☆ / ★★★☆☆
>
> **Prerequisites:** Module NN, Module NN

---

## Contents

| # | Topic | Interview weight |
|---|-------|------------------|
| NN.1 | ... | ★★★★★ |

---
```

And ends with:

```markdown
---

## Module NN — self-test

Answer out loud, without notes. If you stumble, reread that section.

1. ...
2. ...
(8-12 questions)

---

## Key numbers from this module

| Fact | Number |
|------|--------|
| ... | ... |

---

**Next:** [Module NN+1 — <Title>](./NN+1_<file>.md)
```

---

## Per-topic structure (the important part)

Use this for every substantive topic. Keep the exact heading names — they make the
files skimmable and greppable.

````markdown
## NN.X <Topic Name>

> **One-liner:** <one sentence you could say in a hallway. No hedging.>

### Say this in the interview

<A 45-90 second SPOKEN script. First person. Complete sentences. This is the single
most important part of every topic — it is what he will actually recite.

Rules for this block:
- Write it as prose he can read aloud, not bullets.
- Lead with the definition, then WHY it exists, then the trade-off it creates.
- Include one concrete number or example.
- End with a sentence that invites the interviewer deeper ("...I'd size the pool to
  the database's max connections, not to the number of app instances.")
- NEVER write "In an interview you should say..." — just write the words he says.
- Use a blockquote so it visually stands out.>

### Mental model

<The real explanation. Why the thing exists, what problem it solves, what new problem
it creates. Include an ASCII diagram whenever there is a data flow — diagrams are the
highest-value part of the notes. Use box-drawing characters, keep them under 78 chars
wide, and label the arrows.>

### Enterprise production example

<REAL company, REAL system, REAL numbers wherever possible. Name the company in bold.
Explain: what they were doing, what broke or what constraint forced the design, what
they chose, and what it cost them. This is what makes an answer memorable — anyone can
say "use sharding", almost nobody says "Uber fixed 4,096 shards so routing stays
stateless".

If you cannot find a real public example, use a realistic enterprise scenario and label
it clearly as a scenario, not a claim about a company. Never invent a fact about a
named company.>

### Code

<Runnable, production-shaped code. Node.js or Python/FastAPI (his stack). Rules:
- No toy code. Include the error handling / TTL / timeout that makes it real.
- Comments only for non-obvious intent, never narration.
- Keep under ~50 lines. If longer, show the interesting half.
- SQL, YAML, and config are fine when that is the honest answer.
- Skip this section entirely for topics where code adds nothing (CAP theorem, RPO/RTO).>

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| ... | ... | ... |

### Follow-ups they will ask

**Q: <the actual question, phrased the way an interviewer phrases it>**
A: <2-4 sentence answer, specific, with a number or a name in it>

<3-5 of these per major topic. These are where mid-level candidates get separated from
senior ones — make them the genuinely hard follow-ups, not softballs.>

### Red flags — do not say this

- ❌ "<the naive thing candidates say>" → ✅ "<what to say instead>"
````

---

## Style rules

1. **Prose over fragments.** Full sentences in the "Say this" and explanation blocks.
   Bullets are for lists of genuinely parallel items.
2. **Numbers everywhere.** "Fast" is worthless; "sub-millisecond for a Redis GET on the
   same VPC, ~0.5 ms p99" is an answer. When you give a number, make it defensible.
3. **Name the trade-off.** Every technology section must state what the choice costs.
   A design with no downside is a design the candidate does not understand.
4. **His stack first.** Prefer PostgreSQL, Redis, Kafka/Pub/Sub, FastAPI, Node.js, GCP,
   and LLM examples. Mention AWS equivalents in passing.
5. **No filler.** Do not write "In today's fast-paced world" or "It is important to
   note that". Delete any sentence that survives its own removal.
6. **Diagrams.** ASCII, under 78 chars, labelled arrows. At least one per major topic.
7. **Interview weight stars** on every topic so he can triage under time pressure.
8. **Cross-link** to other modules with relative markdown links when a topic depends
   on another: `see [Module 09 — Idempotency](./09_Reliability_Patterns.md#94-idempotency)`.
9. Do not use emoji except the ❌ / ✅ pair in "Red flags" and ★ for weights.
10. Anchors: GitHub slugifies `## 9.4 Idempotency` to `#94-idempotency`. Keep that in
    mind when cross-linking.

---

## Depth calibration

- ★★★★★ topics: full template, 2+ follow-ups minimum, code, production example.
- ★★★★☆ topics: full template, can be tighter.
- ★★★☆☆ topics: "One-liner" + "Say this" + short mental model + one follow-up. He needs
  to recognise these and say something credible, not lecture on them.

A module should be **substantial** — these are meant to be the only notes he needs.
Aim for genuine depth on the ★★★★★ topics rather than even coverage.
