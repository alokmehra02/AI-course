# Study Plan — How to Prepare

## Goal

Walk into the Phyllo LLD round able to:
1. Explain Phyllo products in plain English
2. Run a clean 45–60 min design for a Phyllo use case
3. Answer follow-ups on webhooks, sync, rate limits, consent, multi-tenant safety
4. Design and talk in **Python**

---

## Tonight (recommended ~4–5 hours)

### Block A — Product (60 min)
- [ ] Read `02-product-brief/01-WHAT-IS-PHYLLO.md`
- [ ] Read `02-product-brief/02-USE-CASE-MAP.md`
- [ ] Open getphyllo.com for 15 min and match each section to a use case
- [ ] Skim their webhook blog (link in README)

### Block B — Interview craft (45 min)
- [ ] Read `03-interview-flow/01-MINUTE-BY-MINUTE.md`
- [ ] Practice out loud: `04-what-to-say/01-OPENING-SCRIPT.md`
- [ ] Memorize clarifying questions: `04-what-to-say/02-CLARIFYING-QUESTIONS.md`

### Block C — Core designs (120 min)
- [ ] Walkthrough `05-lld-walkthroughs/01-CONNECT-AND-SYNC.md` — draw on paper
- [ ] Walkthrough `05-lld-walkthroughs/02-WEBHOOK-DELIVERY.md` — draw on paper
- [ ] Skim `05-lld-walkthroughs/03-INCOME-AGGREGATION.md` OR `04-CREATOR-SEARCH.md`

### Block D — Follow-ups + Python (60 min)
- [ ] Drill `06-follow-ups/01-RAPID-FIRE.md` (cover answers with hand, speak aloud)
- [ ] Skim `07-python-patterns/01-CLASS-SKELETONS.md`
- [ ] Skim `07-python-patterns/02-API-AND-SCHEMA.md`

### Block E — Mock (40 min)
- [ ] Pick Connect+Sync OR Webhooks
- [ ] Speak a full design with timer, no notes for first 5 min then use paper
- [ ] Self-score with checklist in `03-interview-flow/02-SCORING-CHECKLIST.md`

---

## Morning of interview (60–90 min)

- [ ] Re-read `08-cheat-sheets/01-DAY-OF-ONE-PAGER.md`
- [ ] Re-draw Connect→Sync→Webhook from memory once
- [ ] Rehearse 60-sec Phyllo pitch once
- [ ] Rehearse resume bridge (VoXgent queues / Europa gateway) once
- [ ] Do **not** start a new topic

---

## Priority order of use cases

| Priority | Use case | Why |
|----------|----------|-----|
| P0 | Connect + Sync | Core product loop |
| P0 | Webhook delivery | They published the design publicly |
| P1 | Income aggregation | Distinctive consented product |
| P1 | Creator search | Scale + public product |
| P1 | Social listening / Social KYC | Website-featured |
| P2 | Rate limiter / API gateway | Infra; matches your Europa work |

---

## What “done” looks like

You can, without looking at notes:
1. Explain Phyllo in 60 seconds
2. List 5 clarifying questions
3. Draw entities for User / Account / SyncJob / Webhook
4. Explain webhook retry + HMAC
5. Explain platform Adapter pattern in Python
6. Answer “polling vs webhooks” and “at-least-once” cleanly
