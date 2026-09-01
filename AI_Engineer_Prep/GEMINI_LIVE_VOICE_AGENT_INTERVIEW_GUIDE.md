# Gemini Live Voice Agent — Interview Guide (Production-Focused)

**Scope:** VoxGent backend, **Google Gemini 2.5 native audio-to-audio** only (`voice_stack = gemini_live_native`). Not classic Google STT → LLM → TTS, not ElevenLabs ConvAI.

**Two guides — use both:**

| Doc | Best for |
|---|---|
| **This file** — production talk track | What to *say*, tradeoffs, mistakes, interview scripts |
| [GEMINI_LIVE_VOICE_AGENT_INTERVIEW_GUIDE_COMPLETE.md](./GEMINI_LIVE_VOICE_AGENT_INTERVIEW_GUIDE_COMPLETE.md) | Full pipeline reference: mermaid diagrams, I1–O17 hops, **30+ Q&A**, cheat sheet |

**How to use this doc:** Read Parts 1–9 once. Before an interview, rehearse the **opening script** and pick **two deep dives** (usually audio IN + barge-in, or transcripts + reliability). Each section has **What to say**, **Why production does this**, and **What we got wrong** where it matters.

**Visual whiteboard:** [gemini-live-pipeline-whiteboard.canvas.tsx](/home/aalokmehra/.cursor/projects/home-aalokmehra-Desktop-lear/canvases/gemini-live-pipeline-whiteboard.canvas.tsx) — open beside chat for tabbed pipeline boards (overview, setup, audio IN/OUT, Gemini, barge-in, formats). Repo copy: [AI_Engineer_Prep/gemini-live-pipeline-whiteboard.canvas.tsx](./gemini-live-pipeline-whiteboard.canvas.tsx).

---

## Opening script (~90 seconds)

Use this almost verbatim:

> “We run phone agents on Twilio Media Streams. Audio is 8 kHz µ-law over a WebSocket — that is the PSTN contract. We do **not** send that straight to the model.
>
> On the way in we decode, denoise, and **gate** what reaches Gemini Live: TV, far-field voices, and echo must not look like the caller. We resample to 16 kHz PCM and stream into Gemini’s **native audio** API on Vertex — one bidirectional session, not separate STT and TTS.
>
> Gemini’s **server VAD** decides when the caller’s turn ends and when barge-in happens. We only **filter** audio before it gets there; we do not replace Google’s turn-taking.
>
> On the way out Gemini returns 24 kHz speech. We queue it, resample to 8 kHz, encode µ-law, and **pace** frames in real time to Twilio. Under load we **delay** agent audio; we almost never drop it — except when the caller interrupts, then we purge the queue and send Twilio `clear`.
>
> Transcripts come from Gemini’s built-in input/output transcription on the same socket. We persist them in the background so the audio path never waits on Postgres.
>
> The hard part of this stack is not calling the API. It is **PSTN noise**, **not faking end-of-turn silence**, **barge-in without echo**, and **keeping transcripts honest** when ASR is weak.”

---

## Part 1 — How production voice agents are actually built

Most production phone agents follow one of two patterns:

**Cascaded pipeline (classic)**  
`Audio → STT → text LLM → TTS → Audio`

- Pros: You control every word (TTS), STT is mature, easy to log text, easy to swap vendors.
- Cons: Higher latency (three hops), awkward barge-in (must cancel TTS and rewind LLM), STT finals lag behind speech.

**Native / speech-to-speech (what we use)**  
`Audio ↔ single multimodal model (Gemini Live)`

- Pros: Lower time-to-first-audio, natural overlap, barge-in is a first-class API event (`interrupted`).
- Cons: Less control over exact wording, transcripts are model ASR (not a dedicated STT), accent control is mostly prompt-based, you own **all** telephony DSP because the model hears whatever you send.

**What interviewers expect you to know:** Production systems always add a **telephony layer** between the carrier and the model — codec conversion, pacing, echo avoidance, noise handling, and backpressure. Whether you use cascaded or native audio, that layer exists. We just do more of it because Gemini hears raw-ish audio and its VAD reacts to everything we forward.

**Our stack in one line:**

```
Twilio (8k µ-law) → our DSP + gate → Gemini Live (16k in / 24k out) → pace → Twilio → caller
```

**Key files if they ask “where in code?”**

| Topic | File |
|---|---|
| TwiML + stream URL | `app/api/v1/quick_call_webhook.py` |
| WebSocket `/ws/voice` | `app/websocket/rt_voice_websocket.py` |
| µ-law adapter | `app/services/voice/gemini_live_twilio_adapter.py` |
| Session + DSP + Gemini | `app/services/voice/gemini_live_session.py` |
| Inbound DSP | `app/services/voice/inbound_audio_processor.py` |
| Outbound pacing | `app/services/voice/twilio_audio_codec.py` |
| Preconnect on ring | `app/services/voice/gemini_preconnect.py` |

---

## Part 2 — Two meanings of “inbound” (say this early)

Interviewers mix these up. Clarify in one sentence:

| Term | Meaning |
|---|---|
| **Call inbound** | Customer called **us**. We route their number to an agent. |
| **Call outbound** | **We** dialed the customer (campaign / quick call). |
| **Audio inbound** | Caller → our server → Gemini (their speech). |
| **Audio outbound** | Gemini → our server → Twilio → caller (agent speech). |

After Twilio Stream `start`, **audio inbound and audio outbound are identical** for both call types. Only **setup** differs (preconnect on outbound ring, number routing on inbound).

---

## Part 3 — Call lifecycle (what to say step by step)

### 3.1 Before anyone speaks

**Outbound (we dial):**

1. API creates a call session (agent, prompt, voice, language).
2. Twilio REST dials the customer; status callbacks fire (`ringing`, `answered`, …).
3. On **`ringing`**, we **preconnect** Gemini Live (`preconnect_gemini_live`) so “hello” after answer is not a cold WebSocket connect.
4. Customer answers → Voice webhook returns TwiML: `<Connect><Stream url="wss://…/ws/voice">` with `agentId`, `organizationId`, `call_sid`, `patient_phone`, `call_direction=outbound`.
5. We skip Google TTS greeting; Gemini speaks the opening natively.

**Inbound (they dial):**

1. Customer hits our Twilio number → Voice webhook.
2. **Inbound routing** maps `Called` number → org + agent. If no mapping: Say + Hangup (no AI).
3. Create inbound session; `patient_phone` = `From`, `call_direction=inbound`.
4. Same TwiML Stream. Preconnect usually does **not** run (stream starts immediately).

**Shared after Stream connects:**

1. **Pod admission** — if this server is at capacity, accept WebSocket then close **1013** so Twilio retries another pod. (Closing before accept = HTTP 403 — wrong signal.)
2. Events: `connected` (store `streamSid`) → `start` (load agent, create conversation, start `GeminiLiveTwilioAdapter`) → `media` loop → `stop` (tear down).
3. Adapter adopts preconnect **only if voice + locale match** — those are fixed on Gemini’s setup frame and cannot be changed mid-session.
4. Three async loops start: **receive** (Gemini → us), **playout** (us → Twilio), **silence timeout** (dead air handling).

**What to say:** “We optimize time-to-first-word with preconnect on outbound ring. Inbound is colder but the media path is the same once the stream starts.”

### 3.2 During the conversation

- Every ~20 ms: Twilio `media` event → decode µ-law → `send_audio` → DSP → gate → 16 kHz → Gemini.
- Gemini streams back 24 kHz audio + transcripts + tool calls on the same connection.
- We pace agent audio to real time; transcripts write in background tasks.

### 3.3 Hangup

- Twilio `stop` → `pipeline.stop` → close WebSocket (so TwiML can Redirect for transfer).
- Post-call: optional transcript script normalization (fix wrong alphabet, not translation).
- Usage recorded to `gemini_live_usage` (billing source of truth).

---

## Part 4 — Audio IN: caller → Gemini (deep dive)

This is where most production bugs live. Walk it in **plain language**, not as 17 bullet labels.

### What to say

> “Twilio gives us small chunks of 8 kHz µ-law, base64 in JSON. First we **only keep the inbound track**. If we forward the outbound track — our own agent audio echoed back — Gemini thinks the caller is talking and we get **self barge-in**.
>
> We convert µ-law to linear PCM because all our DSP expects PCM. We batch about **100 ms** before sending upstream: fewer packets, but if the server event loop stalls we **cap** the buffer so we do not dump seconds of audio at once and trigger Gemini error **1011** (input too fast).
>
> Denoising runs **off the asyncio loop** — RNNoise by default, optional Hush (stronger). We also run AGC because quiet handset users are common on PSTN. Then we classify **near vs far** field and **music/TV** beds so background audio does not become ‘caller speech’.
>
> Important: our gate is **not** VAD. **Gemini’s server VAD** ends the turn after about **1.2 seconds** of silence in what we send. If we send too many zero-filled frames, we **fake** that silence and the model talks over the caller. So we cap destructive mutes at ~**400 ms** and then leak attenuated real audio instead.
>
> Finally we resample 8 kHz → **16 kHz** and call `send_realtime_input`. That is the only audio Gemini’s VAD sees.”

### Why production does this

| Problem on real phones | What we do |
|---|---|
| TV / room chatter | Near/far gate, music-like detector, noisy-environment prompt |
| Quiet caller | AGC, `soft_speech` paths, do not gate on denoised RMS alone |
| Echo of agent | Drop Twilio outbound track; mute inbound while agent speaks until barge confirmed |
| Event loop lag | DSP in thread pool; inbound buffer cap; min ~100 ms between Gemini sends |
| Over-denoising | `foreground_safe` blend (~10% raw + 90% filtered on speech) |

### Numbers worth knowing (not memorizing every flag)

- Twilio: **8 kHz** µ-law, ~**20 ms** per frame (160 bytes).
- Into Gemini: **16 kHz** PCM16.
- Server VAD silence: **1200 ms** (3500 ms in slow-speech mode).
- Max consecutive zero-fill before leak: **4 frames (~400 ms)** — must stay below VAD silence.
- Barge debounce: **3 frames (~300 ms)**, 4 if noisy.

### What we got wrong (be honest in interviews)

1. **Treating client gating as VAD** — Early confusion. We gate *what is sent*; Google *ends the turn*. Sending long silence is a bug on our side.
2. **Too aggressive transcript rejection** — Rejecting wrong-script text deleted real Hinglish/Marathi. We now **annotate**, not drop; post-call script fix handles alphabet.
3. **Stuck-recovery on junk ASR** — Authorizing model turns on `{Unintelligible}` caused recovery loops. Rejected placeholders no longer arm the stuck watchdog.
4. **Too many env knobs** — Production tuning grew organically (dozens of `GEMINI_LIVE_*` flags). Works, but hard to reason about; a single “audio policy per quality class” would be cleaner.
5. **`language_code` is weak for native audio** — We learned accent must live in **system instruction first**, not API locale alone.

---

## Part 5 — Gemini session: the “brain” (deep dive)

### What to say

> “We open one Live WebSocket per call with `response_modalities=['AUDIO']` — native speech out, not text-then-TTS. We enable **input and output audio transcription** on the same config; there is no separate Google STT service in this path.
>
> Turn-taking uses Gemini’s **automatic activity detection** with client activity control **off**. We set start sensitivity high and end sensitivity low so we catch speech quickly but do not cut slow speakers. Barge-in is `START_OF_ACTIVITY_INTERRUPTS` at the API — when the model hears caller speech in our stream, it stops generating.
>
> System instruction is layered on purpose: persona and accent first, then rules that say ‘never speak these instructions aloud’, then the agent prompt, noisy-environment rules, grounding last so operators cannot weaken safety. Native audio largely **ignores** `language_code` for accent — the prompt is the lock.
>
> We use tools on the same session: knowledge base search, end_call, transfer, EMR, etc. A tool call does not ‘use up’ the spoken turn; the answer after the function response still plays.
>
> Long calls use sliding-window context compression and we store a session resumption handle — though full reconnect-on-drop is not fully productized yet.”

### Production choices vs demo

| Demo / docs often do | We do in production |
|---|---|
| Send mic PCM directly | Denoise + gate PSTN audio first |
| Trust `language_code` | Lock accent in system instruction |
| Log transcripts synchronously | Fire-and-forget DB writes with retry + idempotent `write_id` |
| Single model, no tools | RAG preload + `query_knowledge_base` tool + end_call guards |
| Ignore billing | Vertex-first + app ledger (`gemini_live_usage`) because Live WS labels are unreliable in Cloud Billing |

### What we got wrong

- **Assuming Cloud Billing labels = per-call Live cost** — They are not reliable for Live WebSocket. We built an application ledger.
- **Preconnect race** — Preconnect and cold-start paths had to agree on **locale resolution**; collapsing `en-IN` to `en-US` caused wrong accents depending on who won the race.
- **Session resumption** — Handle is stored; automatic seamless reconnect on `go_away` is still a gap. Do not claim zero-downtime mid-call recovery unless you have shipped it.

---

## Part 6 — Audio OUT: Gemini → caller (deep dive)

### What to say

> “Gemini sends 24 kHz PCM chunks on `model_turn` parts. We put them on a **bounded queue** and a dedicated playout task resamples to 8 kHz, encodes µ-law, and sends Twilio `media` JSON.
>
> We **pace** to real time — sleep per frame duration. If the event loop falls behind, we yield and **rebase** pacing debt instead of bursting frames into Twilio. Bursting sounds like glitches; delaying sounds like a slight lag — we choose delay.
>
> We also track `_assistant_speaking` until **estimated Twilio playout** finishes, not until our local queue is empty. If we clear that flag too early, barge-in gates open while the caller still hears the agent.
>
> We have a **turn guard**: native audio can emit extra spoken turns after noise. We only play audio authorized by a reason — user transcript, greeting, silence prompt, etc.
>
> The **only** time we intentionally drop outbound audio is **barge-in**: purge the queue, then send Twilio `clear`. If `clear` sits behind queued frames, the old sentence keeps playing — so purge first.”

### What production gets wrong (industry-wide, including us)

- **Dropping audio to reduce latency** — Sounds like the agent skipped words. We delay.
- **Clear without purge** — Caller still hears half a sentence after they interrupted.
- **Equating queue empty with caller heard** — Generation cursor and playout cursor diverge; drives re-anchor bugs after interrupt.

---

## Part 7 — Barge-in (deep dive)

### What to say

> “While the agent speaks, we mute inbound by default. To interrupt, we need **confirmed** caller speech — not a horn, not TV, not µ-law idle noise. We debounce about 300 ms of consecutive speech frames; noisy environments need a bit more.
>
> During the **greeting**, we use a higher energy threshold so connection pops do not cut the hello. If the product says the first message is non-interruptible, we **ignore** Gemini’s `interrupted` for playback but still **capture** the caller’s transcript so we can answer their question on the next turn.
>
> When interrupt is real: cancel playout, flush what the agent said as `interrupted: true` in the transcript, purge outbound audio, send `clear`, and **re-anchor** — tell the model what the caller actually heard versus what it generated but never played.”

### Memory hook

**Confirm → interrupt → purge → clear → re-anchor**

### What we got wrong

- Letting **noise** confirm barge-in → agent stops mid-sentence on TV.
- **Re-anchor** added after production incidents where Gemini thought it had already asked question two while the caller only heard question one.

---

## Part 8 — Transcripts (deep dive)

### What to say

> “Transcripts are not from a separate STT product. They are `input_transcription` and `output_transcription` on the Live session — ASR on the audio we forwarded in, and text aligned with native audio out.
>
> That coupling matters: if we gate the caller to silence, there is no input transcript. If PSTN quality is bad, you see `{Unintelligible}` — we treat that as **unusable** for authorizing the next model turn, but we **still save** it with `asr_rejected` so the UI does not show a fake silent gap.
>
> When the caller barges in, we keep assistant text the caller **already heard** and mark `interrupted: true` — the recording and transcript must agree.
>
> Writes are async with timeout and retry. A slow transcript write is usually event-loop stall, not slow SQL.
>
> After the call, optional script normalization fixes wrong **alphabet** (e.g. English words written in Devanagari) without translating — one batch LLM job, zero live latency.”

### What we got wrong

- Dropping rejected turns entirely → silent holes in conversation history.
- Using script mismatch to **reject** live turns → deleted valid multilingual speech.
- Blocking the receive loop on DB → fixed with `_spawn_turn_write` and strong refs on tasks.

---

## Part 9 — Tools, silence, reliability

### Tools (short)

- **`query_knowledge_base`** — Search org KB; optional preload of generic facts in system prompt; skip repeated embeds if KB is empty.
- **`end_call`** — Requires explicit hangup or confirmed “I’m done”; waits for goodbye audio to finish playing.
- **Transfer / handoff** — Human transfer uses conference/dial after stream ends; AI-to-AI handoff swaps Gemini session on the **same** Media Stream.

### Silence ladder (dead air)

Progressive prompts (~9s, 16s, 23s) then disconnect (~32s). **Speech-hold** prevents “are you still there?” while the caller is mid-long-answer. Silence timer resets on **meaningful** transcripts, not every noise blip.

### Other reliability

| Mechanism | Purpose |
|---|---|
| Stuck recovery | Model authorized but no audio — capped nudge |
| Noise-stall recovery | TV holds VAD open — inject “please repeat” (rate-limited) |
| `go_away` | Log; session will end |
| AMD / voicemail | Suppress noise/silence prompts on machine |
| Hybrid fallback | `GEMINI_LIVE_FLOW_MODE=hybrid` → classic STT/TTS if Live unavailable |

---

## Part 10 — Native audio vs cascaded (when they ask “why Gemini Live?”)

**Say:**

> “We chose native audio for latency and natural turn-taking on phone calls. The tradeoff is we own telephony DSP and we have less control over exact wording than TTS. We still keep a cascaded Google pipeline as fallback for hybrid mode.
>
> In production, native audio is not ‘plug Twilio into Gemini.’ It is a **telephony front-end** plus a **playback back-end** wrapped around one model socket.”

| | Cascaded (STT→LLM→TTS) | Native (Gemini Live) |
|---|---|---|
| Latency | Higher (chained) | Lower (single session) |
| Barge-in | Cancel TTS + manage LLM state | API `interrupted` event |
| Wording control | High (TTS) | Prompt + SI only |
| Transcripts | Dedicated STT finals | Model ASR (quality ∝ audio sent) |
| Our role | Orchestrate vendors | DSP + gate + pace + guard turns |

---

## Part 11 — Interview Q&A (short answer + one line deeper)

Use these after the narrative sections. Lead with the **bold** line.

**Q1. Caller says “hello” — what happens?**  
Twilio `media` → decode → DSP → gate → 16 kHz → Gemini VAD → after ~1.2s silence, `input_transcription` → we persist and authorize reply → 24 kHz audio paced to Twilio.  
*Deeper:* Authorization links caller transcript to the next spoken agent turn (turn guard).

**Q2. Why not send Twilio audio straight to Gemini?**  
Wrong rate/format plus PSTN noise triggers false VAD and barge-in.  
*Deeper:* 8k µ-law → 16k PCM; gate TV/far-field/echo.

**Q3. Where is VAD?**  
**Gemini server VAD** turn-takes; we only pre-filter the stream.  
*Deeper:* `CLIENT_ACTIVITY_CONTROL=false`; our gate must not forge 1.2s silence.

**Q4. Gate zeros too long?**  
Gemini ends caller turn and talks over them.  
*Deeper:* Cap ~400 ms zero-fill; leak attenuated audio.

**Q5. Barge-in end-to-end?**  
Confirm speech → forward → `interrupted` → purge queue → `clear` → re-anchor transcript.  
*Deeper:* Greeting uses higher RMS; first message can be non-interruptible.

**Q6. Why purge before `clear`?**  
`clear` behind queued audio still plays the old sentence.  
*Deeper:* `send_clear_now` pattern.

**Q7. Echo / self-interrupt?**  
Drop Twilio outbound track; mute until barge confirmed.  
*Deeper:* Near/far + music gates; optional AEC off by default.

**Q8. RNNoise vs Hush?**  
RNNoise default + scene metrics; Hush stronger denoise, different gate path.  
*Deeper:* Fail-open to raw if native lib missing.

**Q9. Separate STT?**  
**No** — Live input/output transcription only.  
*Deeper:* Gating audio gates ASR.

**Q10. Wrong-script transcript?**  
**Do not drop** — annotate; fix alphabet post-call.  
*Deeper:* Hinglish is valid on `en-US` agents.

**Q11. `{Unintelligible}`?**  
Save as rejected; do not authorize next turn.  
*Deeper:* Avoids stuck-recovery storms.

**Q12. Transcripts vs audio path?**  
Background tasks; retry with `write_id`.  
*Deeper:* Never block receive loop on Postgres.

**Q13. Preconnect?**  
Open Gemini on `ringing`; adopt if voice+locale match.  
*Deeper:* Buffer greeting transcripts until adapter binds.

**Q14. Accent / locale?**  
System instruction locks accent; `language_code` alone is insufficient.  
*Deeper:* Preconnect and WS paths must resolve locale the same way.

**Q15. Error 1011?**  
Sending audio too fast after buffer stall.  
*Deeper:* Cap buffer, min send interval, DSP off loop.

**Q16. What do you drop under load?**  
Almost nothing on agent audio (delay). Drop stale inbound overflow and barge-in queue only.  
*Deeper:* Lossless outbound queue wait.

**Q17. Bill per customer?**  
App ledger `gemini_live_usage`, not Billing labels alone.  
*Deeper:* Vertex labels best-effort; `call_sid` not in GCP labels.

**Q18. Agent talked over caller — debug order?**  
Zero-fill streak → far-field leakage → false barge → early `_assistant_speaking` clear → turn guard → input transcript vs rejected.  
*Deeper:* Correlate `[GATE-MUTE-CAP]`, `[AUDIO-UTTERANCE]`, `session=`.

**Q19. What would you improve?**  
Pick one: real reconnect on `go_away`; playout vs generation cursor; fewer audio flags → one policy object.  
*Deeper:* Shows ownership without attacking the system.

**Q20. How is this different from a toy voice demo?**  
Production adds admission control, pacing, dual-VAD discipline, transcript honesty, tool guardrails, billing ledger, and months of PSTN edge cases.  
*Deeper:* Demo sends PCM; we gate PSTN.

---

## Part 12 — What NOT to say

| Wrong | Right |
|---|---|
| “Gemini is our TTS.” | Native audio-to-audio on one Live socket. |
| “We implemented our own VAD.” | We **gate** sends; Gemini **turn-takes**. |
| “We drop audio to keep latency.” | We **delay**; drop only barge-in + stale inbound cap. |
| “Bad transcripts are discarded.” | Rejected turns still saved; script fix is post-call. |
| “`language_code` sets accent.” | System instruction locks accent. |
| “Billing labels invoice Live calls.” | App ledger is source of truth. |
| “We seamlessly reconnect on disconnect.” | Resumption handle stored; full reconnect not fully shipped. |

---

## Part 13 — Quick reference (draw first on whiteboard)

```
CALL SETUP (differs)     →  TwiML Stream  →  SAME AUDIO PATH AFTER start

AUDIO IN:  phone → µ-law 8k → PCM 8k → DSP/gate → PCM 16k → Gemini
AUDIO OUT: Gemini → PCM 24k → queue → PCM 8k → µ-law paced → phone

GEMINI:    server VAD · native audio · transcripts · tools · interrupted

BARGE-IN:  confirm → interrupt → purge → clear → re-anchor
```

| Constant | Value | Why |
|---|---|---|
| Twilio rate | 8 kHz µ-law | PSTN / Media Streams |
| Gemini in / out | 16 kHz / 24 kHz | Native audio API |
| VAD silence | 1200 ms | End of caller turn |
| Zero-fill cap | ~400 ms | Do not fake end-of-turn |
| Barge debounce | ~300 ms | Confirm real speech |
| Min Gemini send gap | ~100 ms | Avoid 1011 |
| Pod full WS close | 1013 | Retry another instance |

---

## Part 14 — Suggested 45-minute interview flow

1. **5 min** — Opening script + whiteboard strip (Part 13).
2. **10 min** — Audio IN (Part 4) + “what we got wrong” on zero-fill.
3. **10 min** — Barge-in (Part 7) + outbound pacing (Part 6).
4. **10 min** — Transcripts (Part 8) + no separate STT.
5. **10 min** — Production topics: preconnect, billing ledger, hybrid fallback, honest gaps (Parts 5, 9, 10).

If they go deep on one area, stay there. Depth on **mute-cap** or **transcript authorization** beats reciting the whole pipeline.
