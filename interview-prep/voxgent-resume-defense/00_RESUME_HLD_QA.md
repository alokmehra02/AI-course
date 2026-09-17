# VoXgent Resume Defense — HLD Interview Q&A

> **Audience:** Alok — Associate Software Developer, Backend / GenAI  
> **Goal:** Every resume line has a spoken answer grounded in what you actually shipped.  
> **Rule for this interview:** Present the platform as **Python + FastAPI + GCP**. Do not mention Node. Frame the outbound scheduler as a **Python-integrated GCP worker service** (Pub/Sub + Cloud Tasks + Cloud Run).  
> **How to use:** Read the **Say this** blocks out loud. The **If they dig** blocks are follow-ups.

---

## Contents

| # | Section | Resume anchor |
|---|---------|---------------|
| 0 | [Opening pitch + system map](#0-opening-pitch--system-map) | Objective |
| 1 | [VoXgent HLD walkthrough](#1-voxgent-hld-walkthrough-45-min-style) | Whole product |
| 2 | [RAG / LangChain / vector DB](#2-rag-langchain--vector-db) | Bullet 1 |
| 3 | [Tool-calling & prompt engineering](#3-tool-calling--prompt-engineering) | Bullet 2 |
| 4 | [Outbound campaign scheduler](#4-outbound-campaign-scheduler) | Bullet 3 |
| 5 | [Human transfer, summaries, Twilio lifecycle](#5-human-transfer-summaries-twilio-lifecycle) | Bullet 4 |
| 6 | [Enterprise integrations](#6-enterprise-integrations) | Bullet 5 |
| 7 | [Schema design & multi-tenancy](#7-schema-design--multi-tenancy) | Bullet 6 |
| 8 | [Europa Locks (client project)](#8-europa-locks-client-project) | Europa bullets |
| 9 | [Multi-Agent Chatbot project](#9-multi-agent-chatbot-project) | Projects |
| 10 | [Skills / certifications rapid fire](#10-skills--certifications-rapid-fire) | Skills + certs |
| 11 | [Honesty traps — what NOT to overclaim](#11-honesty-traps--what-not-to-overclaim) | Critical |
| 12 | [Self-test](#12-self-test-day-of) | Day-of |

---

## 0. Opening pitch + system map

### Q0.1 — “Tell me about yourself / walk me through your resume.”

**Say this:**

> I’m a Python backend and Generative AI engineer with almost two years of experience. For the last year I’ve been a core contributor on VoXgent.AI — an enterprise conversational AI voice platform. My work sits in three layers: (1) RAG pipelines so agents answer from customer knowledge bases instead of hallucinating, (2) LLM tool-calling so the agent can take actions — transfer a call, look up EMR, create a CRM case — and (3) the outbound campaign scheduler on GCP that places high-volume automated voice calls with retry and rescheduling. Before that I worked on an IoT smart-lock backend for Europa Locks — API gateway, Redis caching, real-time messaging, billing. I’m most comfortable designing production systems around FastAPI, Postgres, Redis, and GCP services, and shipping AI features end-to-end rather than stopping at demos.

### Q0.2 — “What is VoXgent in one minute?”

**Say this:**

> VoXgent is a multi-tenant platform where enterprises configure AI voice and chat agents. Each org gets its own Postgres database. Agents have prompts, tools, and a knowledge base. Inbound or outbound phone calls go through Twilio; media streams to our FastAPI backend over WebSockets; the agent talks using Gemini Live or ElevenLabs Conversational AI, grounded by RAG and able to call tools. After the call we generate summaries and can sync to CRM. Separately, campaigns dial thousands of patients/leads through a GCP Pub/Sub + Cloud Tasks scheduler that I designed.

### Mental model (draw this)

```
                    ┌─────────────┐
   Dashboard / API  │  FastAPI    │  JWT / API key
                    │  (Python)   │
                    └──────┬──────┘
           ┌───────────────┼────────────────┐
           ▼               ▼                ▼
     Vault Postgres   Org Postgres      Qdrant (vectors)
     (users, orgs,    (agents, docs,    per-agent collection
      DB mapping)      campaigns, calls)
           │
           ▼
     Redis (call routing, sessions, rate limits, caches)
           │
     ┌─────┴──────────────────────────────┐
     ▼                                    ▼
 Twilio / Exotel                    GCP Pub/Sub + Cloud Tasks
 (voice + webhooks)                 (KB embed + campaign dialer)
     │                                    │
     ▼                                    ▼
 WebSocket voice pipeline           Scheduler workers
 (STT/TTS or Gemini Live            (schedule → task → dial
  or ElevenLabs ConvAI)              → status → retry)
```

---

## 1. VoXgent HLD walkthrough (45-min style)

### Q1.1 — “Design a conversational AI voice platform.” (map to your work)

Use the 6-step playbook; **anchor every choice in VoXgent**.

| Step | What you say (VoXgent-flavored) |
|------|----------------------------------|
| Requirements | Real-time voice (<~500ms turn latency target), multi-tenant isolation, grounded answers (RAG), tool actions, outbound campaigns, post-call summary, HIPAA-ish care for healthcare tenants |
| Capacity | Concurrent live streams limited by voice pods; campaigns capped per-campaign (`maxConcurrentCalls`, often 8–10) and scaled by Cloud Run + queue depth; day volume can be hundreds of initiates |
| High-level | API layer, voice WS runtime, RAG ingest/retrieve, agent orchestrator, telephony webhooks, scheduler, vault tenancy |
| Deep dive | Pick **one**: either RAG, or scheduler, or call lifecycle — don’t deep-dive all three |
| Bottlenecks | LLM/STT latency, embed backlog, Twilio webhook storms, DB connection pools, sticky call state across pods |
| Scale-out | Stateless API + Redis for call→org lookup; separate voice pods with admission control; async ingest via Pub/Sub |

### Q1.2 — “Why FastAPI?”

**Say this:**

> Voice and webhooks are I/O heavy — waiting on Twilio, LLMs, vector search, Postgres. FastAPI’s async model lets one worker handle many concurrent connections. Pydantic gives us request validation for agent configs and tool payloads. WebSocket support is first-class for Twilio Media Streams. We deploy with Uvicorn/Gunicorn on GKE.

### Q1.3 — “How does a single outbound call flow end-to-end?”

**Say this:**

> 1. Quick Call API (or campaign dialer) places a Twilio outbound call and writes `call_sid → organization_id` in Redis, plus a session row in the org Postgres.  
> 2. Twilio answers webhook hits our `/voice` endpoint; we return TwiML that opens a Media Stream WebSocket to our voice runtime.  
> 3. Audio bridges into Gemini Live or ElevenLabs (or classic STT → orchestrator → TTS). The agent uses RAG + tools mid-call.  
> 4. Status and recording webhooks update the session, trigger conversation analysis/summary, optionally CRM sync, and — if it was a campaign call — notify the scheduler to refill the next dial slot or schedule a retry.

### If they dig — latency

**Say this:**

> We keep hot path state in Redis — call config, session, transfer intent — so any voice pod can continue if sticky routing fails. We soft-cap concurrent streams per pod (`MAX_STREAMS_PER_POD`) and reject at capacity rather than degrade everyone’s audio. Embeddings and post-call analysis run async so they don’t block the live conversation.

---

## 2. RAG / LangChain / vector DB

> Resume: *Built RAG pipelines with LangChain, LangGraph, and Pinecone…*

### Q2.1 — “Explain your RAG pipeline.”

**Say this:**

> Ingest: user uploads a file or URL → we parse (PDF/HTML/Sheets CSV export, optional vision enrichment) → chunk with RecursiveCharacterTextSplitter — roughly **1000 chars, 150–200 overlap**, with table/section-aware heuristics for datasheets → store chunks in Postgres `document_chunks` → embed with Gemini embeddings → upsert into a **per-agent vector collection**.  
>  
> Retrieve: query embed (with Redis cache) → hybrid retrieval → optional CrossEncoder re-rank → confidence checks → inject context into the agent prompt / Knowledge tool. Voice can skip low-value queries so we don’t burn latency on chitchat.  
>  
> Jobs: heavy embed work fans out on **GCP Pub/Sub** with Cloud Tasks fallback so API requests stay fast.

### Q2.2 — “Why vector DB? Why not just Postgres full-text?”

**Say this:**

> Keyword search fails on paraphrase — “appointment reschedule” vs “move my visit.” Embeddings capture semantic similarity. We still keep chunks in Postgres for audit, re-embed, and hybrid signals. Vector DB is optimized for ANN search at agent scale; we isolate collections per agent so one customer’s KB never leaks into another’s retrieval.

### Q2.3 — Pinecone on the resume — what if they ask “Do you use Pinecone today?”

**Preferred honest answer (use this):**

> We started on Pinecone. We migrated vector storage to **Qdrant** for cost/control and self-hosted ops on our infra. The service layer kept Pinecone-compatible method names during the cutover, and we have a one-shot migration script. Interview-wise I still describe the **pattern** as managed vector DB + per-tenant/agent isolation — the retrieval contract didn’t change, the backend store did.

**If they only want the buzzword and won’t dig:** you can say “Pinecone / vector DB for RAG” then immediately pivot to chunking, hybrid retrieval, and re-ranking — those are the real design points.

### Q2.4 — “Where does LangChain / LangGraph fit?”

**Say this:**

> LangChain is the glue: text splitters, embeddings wrappers, and the **tool-calling agent** (`create_tool_calling_agent` + `AgentExecutor`) for chat and classic voice orchestration. LangGraph is in the stack as a graph-style orchestration option; the production chat/voice tool loop we run day-to-day is the LangChain agent executor, and for live voice we often use **Gemini Live native function declarations** instead of AgentExecutor because streaming audio needs a tighter loop.

### Q2.5 — “How do you prevent hallucinations?”

**Say this:**

> Grounding via RAG with re-ranking and keyword-overlap / confidence checks; prompts that instruct “answer only from context”; tools for facts that must be live (EMR, CRM) instead of stuffing stale docs; post-call analysis is separate from live answers. We also isolate KBs per agent so wrong corpus can’t poison another use case.

### Q2.6 — “Chunk size trade-offs?”

**Say this:**

> Too small → loss of context, more retrieval noise. Too large → diluted embeddings, token waste in the prompt. ~1000 with ~150–200 overlap is our default; we tune via agent settings (`chunkSize` / `chunkOverlap`). Tables get special handling so we don’t split mid-row.

### Q2.7 — “How is multi-tenant RAG isolated?”

**Say this:**

> Collection name embeds org + agent IDs — like `vg-qdrant-{org}-{agent}`. API auth resolves `organization_id` from JWT or API key; we never search another org’s collection. Document metadata and chunks live in that org’s Postgres.

---

## 3. Tool-calling & prompt engineering

> Resume: *Designed LLM tool-calling pipelines and prompt engineering logic on top of the RAG layer…*

### Q3.1 — “What is tool calling and how did you build it?”

**Say this:**

> The LLM doesn’t only generate text — it emits structured function calls. We register tools from agent config: Knowledge (RAG), Database/MCP (NL→SQL/Mongo on customer data), generic API tool, document tool, `transfer_to_number`, Teams transfer, Canvas EMR tools, Shopify/TMS where enabled.  
>  
> On the chat path, LangChain wraps these as StructuredTools and the AgentExecutor runs a multi-step loop: think → call tool → observe → answer. On Gemini Live voice, we declare the same capabilities as native client tools and execute them in our adapter when the model requests them. Prompts live as versioned templates under a prompts directory — voice, MCP, analysis, transfer intent — rendered with agent-specific variables.

### Q3.2 — “How do you decide RAG vs tool vs plain LLM?”

**Say this:**

> Static product knowledge → Knowledge/RAG tool. Live transactional data → DB or domain API tools (EMR slots, Salesforce case). Side effects (transfer, book appointment) → explicit tools with validation. Small talk / persona → system prompt only. Intent heuristics and `enabled_tools` flags gate what the model is even allowed to see, which reduces accidental tool misuse.

### Q3.3 — “Multi-step agent workflow example?”

**Say this:**

> Healthcare: identify patient (Canvas) → find practitioner → check availability → book appointment → confirm. Each step is a tool; the model chains them. If confidence is low on identity, we don’t book. Sales/support: RAG answer → if user asks for human → transfer tool → mid-call summary for the human agent.

### Q3.4 — “Prompt engineering — what did you actually do?”

**Say this:**

> Separated system persona vs tool instructions vs domain policy; kept tool schemas tight (required fields, enums); added transfer-intent classifier prompts for fast-path human handoff; flow-aware mid-call summarization prompts so later turns fit context windows; analysis prompts for post-call CRM-ready summaries. We iterate on failure transcripts — wrong tool, missed transfer, hallucinated fact — and patch the prompt or tool description, not just “temperature.”

### Q3.5 — “Failure modes of tool calling?”

**Say this:**

> Model invents tool args → schema validation + retries. Tool timeout → short timeouts, user-facing fallback speech. Infinite tool loops → AgentExecutor max iterations / voice turn budgets. Dangerous tools (transfer, write EMR) → enablement flags + confirmations in prompt. Partial failures mid-chain → idempotent booking checks where possible.

---

## 4. Outbound campaign scheduler

> Resume: *Solely designed and developed the outbound campaign scheduler on GCP using Pub/Sub and Cloud Tasks, supporting 500+ concurrent calls with automated retry and rescheduling logic.*

### Q4.1 — “Walk me through the scheduler design.”  ★★★★★

**Say this:**

> It’s an event-driven dialer. Campaigns hold patients/customers and a configuration: calling window, max concurrent calls, auto-retry, reattempt frequency.  
>  
> **Flow:**  
> 1. Create campaign → import CSV (async) → publish to a **scheduling** Pub/Sub topic.  
> 2. Schedule worker computes free slots = `maxConcurrentCalls − in-flight sessions`, picks never-called or retry-eligible patients, and creates a **Cloud Task** for the exact dial time (`current` vs `future`).  
> 3. Task hits a validator endpoint — idempotent patient check, calling-window check — then inserts an `initiated` session and publishes to a **calling** queue.  
> 4. Calling worker claims the session atomically and calls our Python Quick Call API to place Twilio.  
> 5. When the call ends, telephony status comes back through the Python backend into the scheduler webhook → session becomes `ended` or `failure` → we republish scheduleIdentifier to refill slots or schedule a retry.

**Draw this:**

```
CSV / API ──► Pub/Sub SCHEDULING ──► Schedule Identifier
                                            │
                                     Cloud Tasks (time)
                                            │
                                      Validator API
                                            │
                                   Pub/Sub CALLING ──► Dial (Quick Call / Twilio)
                                            │
                                   Status webhook ──► retry / refill / complete
```

### Q4.2 — “Why Pub/Sub AND Cloud Tasks?”

**Say this:**

> Pub/Sub is for **decoupling work** — many campaign events, fan-out to workers, at-least-once delivery, horizontal scale. Cloud Tasks is for **time**: “dial this patient at 4:30 PM in Asia/Kolkata,” including deferring far-future work (we threshold around 30 days and re-check). Queues alone don’t give precise scheduleTime; cron alone doesn’t give per-patient fan-out. Together they give durable async + precise timing.

### Q4.3 — “How do you support high concurrency / the 500+ claim?”

Use the **capacity matrix** below. Interviewers accept this immediately because every row is a formula + a knob you can name.

#### Capacity matrix (memorize this)

Three different numbers people confuse — keep them separate:

| Metric | Formula | What it means | Typical / observed |
|--------|---------|---------------|--------------------|
| **A. Live media concurrency** | `VOICE_POD_REPLICAS × MAX_STREAMS_PER_POD` | How many calls can hold an open Media Stream on voice pods at once | Default soft cap **2 × 4 = 8**; scales by adding pods |
| **B. Dialer concurrency (per campaign)** | `maxConcurrentCalls` | How many sessions may be `initiated` + `in_progress` for **one** campaign | Config default **10**; prod runs at **8–10** |
| **C. Platform dial slots (multi-campaign)** | `Σ maxConcurrentCalls` over active campaigns | Theoretical simultaneous dials across orgs/campaigns | e.g. **5 campaigns × 10 = 50** dial slots |
| **D. Initiate throughput** | `peak_dial_rate × calling_window_minutes` | How many calls you **start** in a window (most end fast: busy / no-answer) | Prod peak **~11–14.5 calls/min** |
| **E. Day volume (the “500+”)** | Successful `calls.initiated` in a day | What we actually shipped under load | **549** successful initiates in one prod day |

**Why D/E can be 500+ while A stays ~8–10:** bulk outbound is mostly short ringing. Only a fraction become long live streams. Scheduler keeps **B** slots full; as soon as a call goes terminal, it refills. So **throughput ≠ simultaneous live audio**.

#### Scale-out matrix (how you justify “architecture supports 500+”)

| Layer | Knob | Scale move | Effect |
|-------|------|------------|--------|
| Scheduler workers | Cloud Run replicas + Pub/Sub pull | Add replicas | More schedule/dial workers; no single-box bottleneck |
| Timing fan-out | Cloud Tasks queue rate | Raise dispatch / shards | More precise future dials in parallel |
| Per-campaign dial | `maxConcurrentCalls` | 10 → 20 → 50 | More in-flight dials **per campaign** (must match voice cap) |
| Voice hot path | `VOICE_POD_REPLICAS`, `MAX_STREAMS_PER_POD` | 2×4 → 10×8 = **80** live | Real concurrent answered calls |
| Phone numbers | From-number pool `max_concurrent` per number | Lease more Twilio numbers | Avoid carrier CPS / from-number limits |
| Multi-tenant | Independent campaigns × orgs | N campaigns in parallel | Platform-level concurrency = sum of campaign caps |

**Back-of-envelope (say this on whiteboard):**

```
Live concurrent ≈ pods × streams_per_pod
Dial slots      ≈ campaigns × maxConcurrentCalls
Day initiates   ≈ dial_rate/min × minutes_in_window
                ≈ 12/min × 45 min ≈ 540   ← matches ~549 prod day
```

| Scenario | Pods | Streams/pod | Live cap (A) | Campaigns | maxConcurrent | Dial slots (C) | ~45 min @ 12/min |
|----------|------|-------------|--------------|-----------|---------------|----------------|------------------|
| **Current prod (observed)** | 2 | 4 | **8** | 1–2 @ 8–10 | 8–10 | ~10–20 | **~500+ initiates** ✓ |
| Modest scale | 5 | 4 | **20** | 3 × 10 | 10 | **30** | easily 500+ |
| Aggressive scale | 10 | 8 | **80** | 10 × 20 | 20 | **200** | 1000s / day |
| “500 live concurrent” target | 63 | 8 | **504** | — | capped to soft cap | — | needs pods + Twilio CPS |

Soft-warn in code: if `maxConcurrentCalls > VOICE_POD_REPLICAS × MAX_STREAMS_PER_POD`, expect audio overlap / late agent speech — so we **scale voice pods with dialer config**, not dial blind.

#### Production proof points (one day, Uptrace)

| Signal | Value |
|--------|------:|
| Successful campaign initiates | **549** |
| Twilio `initiated` webhooks | 557 |
| Peak dial rate | **14.5 / min** (concurrency ~10 run) |
| Campaign concurrency under test | **8 and 10** |
| Peak live `active_streams` on a pod | ≤ **3–4** (cap 4) while dialer still churned |

#### Say this (30–40 sec)

> I separate three numbers. **Dialer concurrency** is per-campaign `maxConcurrentCalls` — we run 8–10 so we don’t overrun voice pods. **Live media concurrency** is `replicas × streams_per_pod` — default soft cap 8, raised by adding voice pods. **Throughput** is what the resume’s 500+ refers to in production: one day we recorded **549 successful initiates** at ~12–14 dials/min because most outbound attempts are short (no-answer/busy) and the scheduler immediately refills free slots via Pub/Sub + Cloud Tasks. If the interviewer wants 500 **simultaneous live** calls, the matrix is explicit — scale voice pods and Twilio from-numbers until `pods × streams ≥ 500`, and keep campaign caps under that soft cap.

**Do not say:** “The code has a hardcoded 500 concurrent limit.” It doesn’t.

**If they push “your resume says concurrent”:**  
> Fair — concurrent dial slots and concurrent live streams are different. Architecturally both scale horizontally; the production number I can cite is **549 initiates in a day** at concurrency 8–10, with a clear formula to grow live concurrency with pods.

### Q4.4 — “Retry and rescheduling logic?”

**Say this:**

> On terminal failure (busy, no-answer, voicemail, etc.), if `isAutoRetryEnabled` and failure count `< maxAttempts`, we compute `nextRetry` from `reattemptFrequency` (minutes/days) and calling-window rules — either override the window or land on the next valid slot/weekday. We create another Cloud Task. Terminal *pre-call* errors (couldn’t even process) do **not** burn the retry budget the same way. Dedup windows avoid double-scheduling the same patient. Campaign completes when end date passes or every patient is terminal / retries exhausted.

### Q4.5 — “Idempotency and double-dial prevention?”

**Say this:**

> Validator returns success if patient already processed. Dial worker uses an atomic `claimProcessing` update so only one replica wins. Task logger + dedup window (~5 minutes) prevents duplicate Cloud Tasks for the same slot. Status webhook is idempotent on already-terminal sessions. Quick Call and campaign session are correlated by scheduler IDs in metadata.

### Q4.6 — “Campaign state machine?”

**Say this:**

> Campaign: `scheduled → ongoing → completed`, with `stopped` / `cancelled` for operator actions.  
> Session: no row → `initiated` → `in_progress` → `ended` | `failure`.  
> Mapping from Twilio: completed+duration → ended; busy/no-answer/voicemail/canceled → failure; machine detection can mark voicemail.

### Q4.7 — “What did *you* solely design?” (ownership)

**Say this:**

> I owned the outbound scheduler architecture: topic/queue split, Cloud Tasks timing model, schedule-identifier slot math, retry/reschedule policy, validator idempotency, and the contract with the Python Quick Call + Twilio status path. The main VoXgent API team consumes it; I defined the Pub/Sub message shapes and session lifecycle the voice backend must honor.

### Q4.8 — Follow-ups they love

| Question | Short answer |
|----------|--------------|
| Ordering? | Per-campaign logical slots; not global FIFO across campaigns |
| Poison messages? | Nack transient; ack non-retryable; rely on subscription DLQ |
| Far future dials? | Schedule horizon task (~30d), store intended time, re-validate later |
| Timezones? | Campaign config + `APP_TIMEZONE` (e.g. Asia/Kolkata), calling windows in civil time |
| Why not Celery beat? | Wanted managed durable tasks on GCP, multi-instance safe, no self-hosted beat SPOF |

---

## 5. Human transfer, summaries, Twilio lifecycle

> Resume: *Engineered intent-based real-time human transfer and AI-generated live call summaries; handled Twilio webhook events for complete call lifecycle management.*

### Q5.1 — “How does human transfer work?”

**Say this:**

> Two paths: (1) the model calls `transfer_to_number` / `teams_transfer` as a tool; (2) a fast-path intent classifier detects “let me talk to a human” from user speech. We write transfer intent into a registry (in-memory + Redis) keyed by call. Twilio then gets Dial/conference TwiML to the human number. For Teams transfer we first generate a Gemini summary and notify Teams/email so the human has context, then drop the AI leg.

### Q5.2 — “Live vs post-call summaries?”

**Say this:**

> **Live / mid-call:** `summarize_conversation` compresses history with Gemini Flash when the context window grows — flow-aware so the agent doesn’t forget goal state.  
> **Post-call:** `ConversationAnalyzer` runs after status/recording webhooks (and ElevenLabs call-completed). We can attach transfer-leg recordings by transcribing the human segment and merging into analysis. Summaries feed CRM sync and supervisor UI.

### Q5.3 — “Twilio call lifecycle — which webhooks?”

**Say this:**

> - `/voice` — answer; return Media Stream TwiML; resolve org via Redis `call_sid` lookup  
> - Media Stream WebSocket — real-time audio  
> - `/status-callback` — ringing/in-progress/completed/failed; finalize session; notify scheduler  
> - `/recording-status` — fetch recording; kick analysis  
> - `/transfer-recording-status` — human-leg recording  
> - conference/dial-action — transfer conference completion  

Same pattern for Exotel where India telephony needs it.

### Q5.4 — “How do you route webhooks to the right tenant?”

**Say this:**

> Twilio doesn’t know our org IDs. At dial time we cache `call_sid → organization_id` in Redis with TTL. Webhooks read that key, open the correct org DB via Vault mapping, and update the right session. Without that, multi-tenant voice breaks.

### Q5.5 — “ElevenLabs Conversational AI — where does it fit?”

**Say this:**

> One of three voice stacks: classic STT→LLM→TTS, Gemini Live native audio, or ElevenLabs ConvAI. For ElevenLabs we get a signed conversation URL and bridge Twilio 8 kHz μ-law to their 16 kHz PCM. Agent config holds `elevenlabs_agent_id`. Post-call webhooks still land in our backend for summary and CRM.

---

## 6. Enterprise integrations

> Resume: *Developed 6+ REST API integrations… Salesforce, Canvas EMR, Google Sheets, SMS/WhatsApp…*

### Q6.1 — “How do you integrate Salesforce?”

**Say this:**

> Several patterns depending on the customer: OAuth + SOQL proxy through an API gateway for contact lookup; case creation via customer portal API or an n8n webhook; post-call CRM sync service that pushes dispositions to Salesforce/HubSpot/generic webhooks; Zapier-style integration records storing outbound webhook URLs per agent. We don’t embed a giant Salesforce monolith in-process — we treat it as an external system of record behind stable HTTP contracts.

### Q6.2 — “Canvas EMR?”

**Say this:**

> FHIR R4 HTTP helpers behind a Canvas gateway: patient identify, practitioner search, availability, book appointment. Voice tools are injected when `enable_canvas_emr` is on. ElevenLabs can hit `/el/*` tool webhooks on the same gateway. Critical for healthcare agents that must act, not just chat.

### Q6.3 — “Google Sheets?”

**Say this:**

> Primarily **knowledge ingest**: detect Sheets URL, export CSV, run through the same chunk→embed pipeline. OAuth scopes include spreadsheets readonly. Some customers use Forms → Sheets → automation → our external trigger APIs for campaigns.

### Q6.4 — “SMS / WhatsApp?”

**Say this:**

> SMS via Twilio SMS API. WhatsApp via **Meta Cloud API** (not Twilio WhatsApp middleware) — conversations, credentials, bot config in Postgres; webhooks on our SMS/WhatsApp routes. Used for outreach and notifications alongside voice.

### Q6.5 — “How do you design integration contracts?”

**Say this:**

> Idempotent webhooks with delivery logs; secrets in env/Secret Manager; per-org credentials; timeouts and retries with backoff; never block the voice hot path — sync CRM async after call. Version gateway paths so partner breaking changes don’t cascade.

---

## 7. Schema design & multi-tenancy

> Resume: *Designed relational & NoSQL schema (PostgreSQL, MongoDB) and inter-service API contracts… 3-person backend team…*

### Q7.1 — “Explain your multi-tenant model.” ★★★★★

**Say this:**

> Hard isolation: a **Vault** Postgres holds users, org membership, API keys, and `organization_id → database_url` mapping. Product data lives in **per-organization Postgres** databases. JWT carries `organization_id` (not the DB URL). On each request, `get_db()` resolves the mapping and opens a pooled connection to that org’s DB. Voice webhooks use Redis call_sid lookup then the same path. This is stronger isolation than shared-schema RLS alone — important for enterprise/healthcare.

### Q7.2 — “What lives in Postgres vs Mongo vs Redis vs Qdrant?”

| Store | Role |
|-------|------|
| Vault Postgres | Auth, orgs, API keys, DB mapping |
| Org Postgres | Agents, documents, chunks, campaigns, sessions, WhatsApp, integrations |
| MongoDB | Optional customer MCP datasource (their data); not our system of record |
| Redis | Rate limits, call→org, voice session/config, transfer registry, RAG query embed cache |
| Qdrant | Vector embeddings per agent collection |

### Q7.3 — “Key relational entities you designed?”

**Say this:**

> Agents and their tool/prompt config; Document / DocumentChunk / folders for KB; Campaign / CampaignCustomer / CampaignSession / task logs for dialer; Call session + CallSid lookup; Integration + delivery logs; WhatsApp conversation models. Alembic migrations per change; connection manager so we don’t leak pools across tenants.

### Q7.4 — “Inter-service API contracts?”

**Say this:**

> REST under `/api/v1` for product APIs; `/gateway` for Salesforce/Canvas proxies; Cloud Tasks OIDC/bearer-protected worker endpoints; Pub/Sub JSON payloads for schedule/CSV/embed; Twilio form webhooks + Media Streams WS protocol. Contracts include scheduler IDs on Quick Call so status can round-trip.

### Q7.5 — “3-person team — what was your slice?”

**Say this:**

> I owned GenAI pipelines (RAG + tools), voice telephony webhooks/transfer/summary paths that touched my features, and the outbound scheduler end-to-end. Shared work: schema reviews, API contracts, multi-tenant DB mapping. I can speak to the whole platform HLD because we were small, but I’ll mark ownership clearly when asked.

---

## 8. Europa Locks (client project)

> Sep 2024 – May 2025 — IoT smart lock ecosystem. Resume lists Node; **in HLD talk architecture, not runtime language.** If pressed on language, you can say the client stack was JS services — prefer pivoting to design.

### Q8.1 — “API Gateway consolidating 8+ microservices?”

**Say this:**

> Edge gateway as single client entry: authn/authz, rate limiting, request routing to lock, user, billing, notification, video, device services, etc. Clients don’t know internal topology. Observability (correlation IDs, structured logs) at the edge. This reduced client complexity and centralized security policy.

### Q8.2 — “~40% performance improvement with Redis?”

**Say this:**

> Read-heavy paths — device status, session tokens, config — moved behind Redis cache-aside; inter-service hot data avoided repeated Postgres hits; list APIs gained pagination so we stopped shipping huge payloads. Measured latency/DB load before-after on critical endpoints — roughly 40% improvement on those paths. Classic cache invalidation on writes for device state.

### Q8.3 — “MQTT + video, 35% reliability, 10k users?”

**Say this:**

> Locks speak MQTT (Mosquitto) over TLS for command/telemetry — better than pure HTTP for flaky IoT networks (retained messages, QoS). Agora for video streaming use cases (e.g. visitor/delivery flows). Reliability work was connection backoff, TLS, QoS, and monitoring reconnect storms — ~35% fewer failed command deliveries on the paths we tracked. RBAC for admin vs end user; Razorpay for subscriptions/billing; scale to 10k+ active users with horizontal API instances + Redis + Postgres.

### Q8.4 — HLD diagram (Europa)

```
Mobile App → API Gateway (auth, rate limit) → Microservices
                                    ↓
                              Redis cache
                                    ↓
                         Postgres / Mongo
                                    ↓
              Mosquitto MQTT (TLS) ←→ Smart locks
              Agora ←→ video sessions
              Razorpay ←→ billing
```

---

## 9. Multi-Agent Chatbot project

### Q9.1 — “Tell me about your multi-agent chatbot.”

**Say this:**

> Personal/project FastAPI backend with MySQL + SQLAlchemy. Modular routers for specialized agents — general, memory, context, follow-up — each with prompt-engineered pipelines on OpenAI models. Conversation memory stores/retrieves history for RAG-style context. Dockerized; Alembic for migrations. It was how I practiced agent routing and memory before doing it in production on VoXgent.

### Q9.2 — Bridge to VoXgent

**Say this:**

> Same ideas at larger scale: tool-enabled agents, memory/summary compression, retrieval grounding, container deploy — but VoXgent adds multi-tenancy, voice, Twilio, GCP job queues, and enterprise integrations.

---

## 10. Skills / certifications rapid fire

### Q10.1 — “You have GCP PCA — how did you use GCP on VoXgent?”

**Say this:**

> Pub/Sub for async fan-out (KB embed, campaign schedule/dial), Cloud Tasks for timed dials, GKE for API/voice workloads, Secret Manager patterns, regional deploy `asia-south1`. PCA knowledge helped me choose Pub/Sub vs Tasks vs cron correctly and reason about IAM on task handlers.

### Q10.2 — “Databricks GenAI cert — did you use Databricks?”

**Say this:**

> Certification covers RAG, evaluation, governance concepts I apply on VoXgent. Day-to-day vectors are Qdrant/Gemini embeddings on our stack; the cert is conceptual depth, not “we run Databricks in prod for VoXgent.”

### Q10.3 — Redis on VoXgent?

**Say this:**

> Rate limiting, `call_sid→org` routing, voice session/config cache, transfer registry across pods, RAG query embedding cache, campaign hot keys. Redis is the nervous system for real-time voice multi-tenancy.

### Q10.4 — Docker / Kubernetes?

**Say this:**

> Backend containerized; deploy on GKE. Voice pods sized with stream capacity limits. Scheduler workers on Cloud Run. Config via env + secrets; health checks for LB.

### Q10.5 — “System design fundamentals?”

Point to your System_Design_Prep modules; pick one VoXgent story (scheduler = job queue design; RAG = multi-tenant RAG case study; webhooks = reliable webhook delivery).

---

## 11. Honesty traps — what NOT to overclaim

| Resume wording | Safe defense | Overclaim to avoid |
|----------------|--------------|--------------------|
| Pinecone | Started on Pinecone; migrated to Qdrant; same RAG design | “We only use Pinecone in prod today” if they inspect current deps |
| LangGraph | In stack; production loop is LangChain AgentExecutor + Gemini Live tools | “Everything is a LangGraph StateGraph” |
| 500+ concurrent calls | Architecture scales; day volume 500+; per-campaign caps ~8–10 | “500 simultaneous calls on one campaign by default” |
| Solely designed scheduler | Own the dialer architecture + GCP design + contracts | Claim you wrote every line of the entire VoXgent monolith |
| 6+ integrations | Gateway + tools + webhooks pattern across SF, Canvas, Sheets, SMS, WA, … | Claim deep native SDK ownership of all Salesforce objects |
| Europa 40% / 35% | Measured on specific paths you owned | Invent methodology if you don’t remember — say “p95 latency / failed MQTT commands on gateway paths” |
| MongoDB | Optional customer MCP DB | “Mongo is our primary store” |

**Golden rule:** Prefer **architecture truth** over buzzword loyalty. Interviewers respect migration stories.

---

## 12. Self-test (day of)

Answer out loud, no notes. Target <90 seconds each.

1. Draw VoXgent HLD and narrate one outbound call.  
2. Explain RAG ingest + retrieve with numbers (chunk size, overlap).  
3. Pinecone vs Qdrant — 20-second honest version.  
4. Why Pub/Sub + Cloud Tasks together?  
5. How do you prevent double-dialing a patient?  
6. How does human transfer work mid-call?  
7. How is tenant isolation enforced on a Twilio webhook?  
8. Name Postgres vs Redis vs vector DB responsibilities.  
9. Canvas EMR tool chain for booking.  
10. What breaks first at 10× campaign load, and what do you scale?

---

## Appendix A — 60-second “favorite project” (scheduler)

> The outbound campaign scheduler. Enterprises upload a patient list and need thousands of AI voice calls inside calling windows, with retries on no-answer, without overloading telephony. I designed it as Pub/Sub stages for schedule and dial, Cloud Tasks for precise timing, atomic session claims for multi-instance safety, and a clean contract back to our Python FastAPI Quick Call + Twilio webhooks. The interesting problems weren’t placing one call — they were idempotency, concurrency slots, timezone windows, and refill-after-complete so the pipeline never stalls.

## Appendix B — 60-second “favorite project” (RAG + tools)

> Building grounded voice agents: RAG so answers come from the customer KB, and tool-calling so the agent can transfer or hit EMR/CRM. The hard part is the live path — you can’t run a slow AgentExecutor the same way on a phone call — so we use Gemini Live native tools for voice and LangChain tool agents for chat, sharing the same tool semantics and prompts.

## Appendix C — Numbers to memorize

| Item | Value |
|------|--------|
| Default chunk / overlap | ~1000 / ~150–200 |
| Per-campaign concurrent default | ~10 (config-driven); prod runs 8–10 |
| Soft voice capacity | `VOICE_POD_REPLICAS × MAX_STREAMS_PER_POD` (e.g. 2×4 = **8**) |
| Day initiates (prod proof) | **549** successful in one day |
| Peak dial rate (prod) | **~11–14.5 calls/min** |
| 500+ back-of-envelope | `12/min × ~45 min ≈ 540` |
| Live vs dialer | Dial slots refill on terminal; live streams ≪ initiates |
| Cloud Tasks far-future horizon | ~30 days |
| Task dedup window | ~300 seconds |
| Retry | `maxAttempts` + `reattemptFrequency` + calling window |
| Embed model | Gemini embeddings |
| Voice stacks | Classic / Gemini Live / ElevenLabs ConvAI |
| Tenancy | Vault DB + DB-per-org |
| Team size (VoXgent backend) | 3 |

---

*Last updated from codebase review of `/home/aalokmehra/Desktop/VoxGent/backend` and `/home/aalokmehra/Desktop/VoxGent/call-scheduler` (presented as Python/GCP architecture for interviews).*
