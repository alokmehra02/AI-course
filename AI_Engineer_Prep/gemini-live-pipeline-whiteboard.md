# Gemini Live Pipeline Whiteboard

**Scope:** VoXgent `gemini_live_native` stack — Twilio Media Streams ↔ Gemini Live native audio.

**Companion docs:**
- [Interview guide (what to say)](./GEMINI_LIVE_VOICE_AGENT_INTERVIEW_GUIDE.md)
- [Complete reference (Q&A + diagrams)](./GEMINI_LIVE_VOICE_AGENT_INTERVIEW_GUIDE_COMPLETE.md)
- [Interactive canvas in Cursor](./gemini-live-pipeline-whiteboard.canvas.tsx) — open from `.cursor/projects/.../canvases/` beside chat

**Legend:** Inbound audio = caller → Gemini. Outbound audio = Gemini → caller. Call setup (who dials) is separate; after Media Stream starts, both call directions share the same audio path.

---

## Table of contents

1. [Big picture](#1-big-picture)
2. [Call setup](#2-call-setup)
3. [Audio IN (I1–I17)](#3-audio-in-i1i17)
4. [Audio OUT (O1–O13)](#4-audio-out-o1o13)
5. [Gemini brain (G1–G9)](#5-gemini-brain-g1g9)
6. [Barge-in (B1–B9)](#6-barge-in-b1b9)
7. [Formats to memorize](#7-formats-to-memorize)

---

## 1. Big picture

### One sentence to open with

> Twilio streams 8 kHz µ-law. We clean and gate it, resample to 16 kHz, and send it into Gemini Live native audio. Gemini speaks 24 kHz PCM. We resample, encode µ-law, and pace it back to Twilio in real time. Transcripts ride the same Live socket.

### Three lanes

#### Lane A — Audio IN (caller speech)

1. Phone / PSTN
2. Twilio 8 kHz µ-law
3. Decode PCM 8 kHz
4. DSP + send gate
5. Resample 16 kHz
6. Gemini `send_realtime_input`

#### Lane B — Gemini brain (same Live WebSocket)

1. Server VAD (turn taking)
2. Native audio generate
3. Input + output transcripts
4. Tools / RAG / `end_call`
5. `interrupted` + `turn_complete`
6. Authorize next spoken turn

#### Lane C — Audio OUT (agent speech)

1. Gemini 24 kHz PCM
2. Outbound queue (delay, not drop)
3. Resample 8 kHz
4. Encode µ-law + pace frames
5. Twilio media JSON
6. Phone hears the agent

### Twilio events (wrap both lanes)

| Order | Event | What happens | Audio yet? |
|-------|-------|--------------|------------|
| 0 | Call setup | Inbound: number maps to agent. Outbound: we dial, preconnect on ringing. | No |
| 1 | `connected` | Twilio opens `wss://…/ws/voice`. Store `streamSid`. | No |
| 2 | `start` | Load agent, create conversation, start `GeminiLiveTwilioAdapter` (adopt preconnect if voice+locale match). | No |
| 3 | `media` | Repeating inbound µ-law frames (Lane A). Lane C sends media the other way on the same socket. | Yes |
| 4 | `stop` | Hangup. Stop session, persist leftover transcripts, close WS so TwiML Redirect can transfer. | Ends |

> **Warning — two meanings of inbound/outbound**
>
> **Call** inbound vs outbound = who started the phone call.
> **Audio** inbound vs outbound = which way samples flow after the Stream is live.
> Interviewers often say “inbound pipeline” and mean audio IN. Say which one you mean.

---

## 2. Call setup

Setup is the only place inbound and outbound calls really differ. After **S5** both join the same Media Stream audio pipeline.

### Outbound call (we dial)

| Step | Title | Detail |
|------|-------|--------|
| **S1** | Create call session | Quick Call / campaign stores agent, system prompt, voice, language, dynamic variables, To number. |
| **S2** | Twilio REST dials the customer | Outbound API call. Status callbacks: initiated, ringing, answered, completed. |
| **S3** | Ringing → preconnect Gemini | `preconnect_gemini_live(call_sid)` opens Gemini Live during ring so answer is not a cold connect. Greeting transcripts buffer until the adapter binds. |
| **S4** | Answer → Voice webhook | Twilio asks for TwiML. We already know org, agent, prompt. AMD may later flag voicemail. |
| **S5** | TwiML Connect + Stream | `wss://…/ws/voice` with `agentId`, `organizationId`, `call_sid`, `language`, `call_direction=outbound`, `patient_phone=To`. Native Gemini greeting (no Google TTS). |

### Inbound call (they dial us)

| Step | Title | Detail |
|------|-------|--------|
| **S1** | Customer dials Twilio number | PSTN hits our Voice webhook. No call session exists yet. |
| **S2** | Map number → org + agent | `InboundRoutingService` on the Called number. If none: Say + Hangup fallback, no Stream. |
| **S3** | Create inbound session | `QuickCallService.create_inbound_call_session`. `patient_phone=From`, `call_direction=inbound`. Usually no preconnect — Stream starts immediately. |
| **S4** | Optional inbound recording | If enabled, recording starts here. Outbound recording is handled on the dial path instead. |
| **S5** | Same TwiML Connect + Stream | Same `/ws/voice`. Custom params include `call_direction=inbound`. Gemini connects cold on start unless a race preconnect exists. |

### Shared after Stream (both directions)

| Step | Title | Detail |
|------|-------|--------|
| **S6** | Pod admission | `try_acquire`. If full: accept WebSocket then close **1013** (try later). Never close before accept — that becomes HTTP 403. |
| **S7** | `connected` + `start` | Resolve locale the same way as preconnect (do not collapse `en-IN` → `en-US`). Adopt preconnect only if voice and locale match. Else cold `GeminiLiveSession.start()`. |
| **S8** | `LiveConnectConfig` | `response_modalities` AUDIO, voice, system instruction (accent first), tools, input+output transcription, server VAD, `session_resumption`, sliding-window compression. |
| **S9** | Greeting kickoff | If Gemini owns the hello: `send_client_content` text kickoff, `turn_complete=true`, authorize `initial_greeting`. If Twilio already played cached audio: tell Gemini not to repeat; emit system greeting into the transcript. |
| **S10** | Three tasks now run | `receive_loop` (Gemini → us), `playout_loop` (us → Twilio), `silence_timeout_loop`. `media` events feed `send_audio`. |

---

## 3. Audio IN (I1–I17)

**Say this:** Every ~20 ms Twilio gives us 160 bytes of µ-law on `track=inbound`. We decode, denoise, gate, resample to 16 kHz, and only then call Gemini. We never forward the outbound track or we barge in on ourselves.

### Twilio hop

| Step | Title | Format | Detail |
|------|-------|--------|--------|
| **I1** | Caller speaks into the handset | phone | PSTN / SIP. Analog at the phone, 8 kHz µ-law by the time it is Twilio Media Streams. |
| **I2** | Twilio Media Streams JSON | JSON + base64 | `event=media`, `media.payload=base64`, `media.track=inbound`, `streamSid` set. |
| **I3** | Drop non-inbound tracks | — | `should_forward_twilio_track`: only inbound / `inbound_track`. Outbound is our own voice echoed back. |
| **I4** | Base64 decode | µ-law 8 kHz | Raw µ-law bytes. Empty payload is skipped. |
| **I5** | µ-law → PCM16 | PCM16 8 kHz | `adapter.add_audio_chunk` → `audioop.ulaw2lin`. DSP only understands linear PCM. |
| **I6** | Buffer 5 frames (~100 ms) | — | `send_audio` appends. Flush at 5 chunks. Cap 10 and keep newest 5 if the event loop lagged — bursting causes Gemini error **1011**. |

### DSP (off the event loop)

| Step | Title | Format | Detail |
|------|-------|--------|--------|
| **I7** | `process_inbound_pcm_for_gemini` | — | `run_dsp` / thread pool. Never inline on asyncio. ~10 ms per 100 ms chunk. |
| **I8** | Noise suppress + AGC | — | Default RNNoise. Or Hush (DeepFilterNet) or Wiener. AGC target about -16 dBFS so quiet handsets reach Gemini. |
| **I9** | Near / far + music-like + transients | — | Near-field confidence. TV/music latch. Horns/slams attenuated and not treated as barge-in. Soft-speech rescue for quiet callers. |
| **I10** | Audio mode `foreground_safe` | PCM16 8 kHz | Speech: ~10% raw + 90% denoised so consonants survive. Background: fully filtered. Max speech attenuation ~8 dB or raw-speech guard. |
| **I11** | Quality class | — | GOOD / LOW_VOLUME / NOISY_BACKGROUND. Tightens barge debounce and noise gate. May later speak one noise warning. |

### Send gate, then Gemini

| Step | Title | Format | Detail |
|------|-------|--------|--------|
| **I12** | Client gate `_gate_inbound_audio` | — | This is NOT the turn-taker. It decides pass / mute / buffer-for-barge. µ-law idle RMS ~8 is not speech. |
| **I13** | Mute cap + zero-fill cap | — | Max 4 consecutive destructive mutes (~400 ms). Then leak attenuated audio. Must stay under Gemini `silence_duration_ms` **1200 ms** or we fake end-of-turn. |
| **I14** | Silence-hold bookkeeping | — | Near-field speech holds the “are you still there?” ladder so long answers are not treated as hangups. |
| **I15** | Resample 8 kHz → 16 kHz | PCM16 16 kHz | `audioop.ratecv` with persistent state (no clicks at chunk edges). |
| **I16** | Min send interval ~100 ms | — | Sleep if we would send faster. Second **1011** defense. |
| **I17** | `send_realtime_input` | Gemini Live WS | Blob `mime_type audio/pcm;rate=16000`. Gemini server VAD now sees this stream. |

---

## 4. Audio OUT (O1–O13)

**Say this:** Gemini emits 24 kHz native speech, not text-then-TTS. We never dump it into Twilio as fast as it arrives. We pace µ-law at 8 kHz real time. Backpressure delays audio. Only barge-in drops queued speech.

### From Gemini

| Step | Title | Format | Detail |
|------|-------|--------|--------|
| **O1** | `model_turn` inline_data audio | PCM16 24 kHz | 24 kHz PCM16 chunks on the Live receive loop. Text-only thought parts do not consume the one-turn audio token. |
| **O2** | TURN-GUARD | — | Play only if authorized (greeting, `user_transcript`, silence prompt, tool follow-up). Extra noise-triggered turns are dropped. |
| **O3** | Mute after `end_call` | — | `_muted` / `_mute_after_turns`: do not keep talking after goodbye tool. |
| **O4** | Put on outbound PCM queue | — | Bounded queue. If full, await — lossless. Dropping here chops the start of the sentence. |
| **O5** | `playout_loop` | — | Marks `_assistant_speaking`. First chunk of the call is first-frame latency. Later chunks batch up to ~500 ms. |
| **O6** | `send_audio_paced` | PCM16 8 kHz | `ratecv` 24 kHz → 8 kHz with persistent resample state. |

### To the phone

| Step | Title | Format | Detail |
|------|-------|--------|--------|
| **O7** | PCM → µ-law | µ-law 8 kHz | `audioop.lin2ulaw`. This is what Twilio Media Streams accepts outbound. |
| **O8** | Slice frames | — | Legacy 20 ms = 160 bytes. Optional 100 ms batching to wake the event loop less often. Audio to the ear is identical. |
| **O9** | JSON media event | — | `event=media`, `streamSid`, `payload=base64`. `TwilioOutboundQueueWriter` enqueues; does not send on the Gemini loop. |
| **O10** | `media_sender` task | — | Dedicated task drains the WS send queue. Congestion delays. Timeouts are logged as backpressure, frames are not deleted. |
| **O11** | Pace to real time | — | Sleep by actual frame duration (`len/8000`). If behind, yield. If debt exceeds max pacing debt, rebase to now — shift later, lose nothing. |
| **O12** | Twilio plays to PSTN | phone | Caller hears the agent. `_assistant_speaking` stays true until estimated playout finishes, not when our local queue empties. |

> **O13 — the exception that drops audio**
>
> On barge-in, `send_clear_now` purges queued outbound frames then sends Twilio `clear`. That is the only correct drop: the caller interrupted, so stale agent speech must never play.

---

## 5. Gemini brain (G1–G9)

Native audio-to-audio. One bidirectional WebSocket. No separate Google STT and no separate TTS in this stack.

### Server VAD (the real turn-taker)

| Step | Title | Detail |
|------|-------|--------|
| **G1** | `automatic_activity_detection` on | `CLIENT_ACTIVITY_CONTROL` is False. We do not send `activityStart`/`activityEnd`. Gemini owns start and end of speech. |
| **G2** | Start HIGH, end LOW | Catch speech quickly. Do not cut slow speakers. `prefix_padding_ms` ~300 keeps the first consonant. |
| **G3** | `silence_duration_ms` = 1200 | 3500 in `slow_speech_mode`. After this much silence in what we forwarded, Gemini ends the user turn and replies. |
| **G4** | `START_OF_ACTIVITY_INTERRUPTS` | If Gemini hears caller speech in the audio we send, it stops generating. That is barge-in at the API. |

### Receive loop branches

| Step | Title | Detail |
|------|-------|--------|
| **G5** | `input_transcription` | Caller ASR on audio we forwarded. Usability check. Persist always (rejected gets `asr_rejected`). Accepted authorizes the next spoken turn. |
| **G6** | `output_transcription` | Fragments concatenated until `turn_complete`. Interrupted flush is saved with `interrupted=true` because the caller already heard it. |
| **G7** | `tool_call` | `query_knowledge_base`, `end_call`, `transfer`, `handoff`, EMR. Tool does not consume the audio authorization. `FunctionResponse` then spoken answer. |
| **G8** | `go_away` / resumption / usage | Log `time_left`. Store resumption handle. Merge `usage_metadata` into `gemini_live_usage` ledger (billing source of truth). |

### Transcript writes (not on the audio path)

| Step | Title | Detail |
|------|-------|--------|
| **G9** | Fire-and-forget DB write | `_spawn_turn_write` with timeout, retry, `write_id`. Receive loop never awaits Postgres. Script mismatch is annotation only. After hangup, script normalizer re-spells wrong alphabet without translating. |

---

## 6. Barge-in (B1–B9)

**Memory hook:** Confirm → interrupt → clear → re-anchor. Four verbs.

| Step | Title | Detail |
|------|-------|--------|
| **B1** | Agent is speaking | `_assistant_speaking` or `greeting_active`. Inbound frames are mute-by-default. |
| **B2** | Is this a barge candidate? | Not µ-law idle. Not transient. Not music-like. Near-field / voiced. Greeting uses a higher RMS floor so connect pops do not cut hello. |
| **B3** | Debounce | Buffer consecutive speech frames. 3 frames (~300 ms), or 4 if NOISY_BACKGROUND. Gaps of 1–2 frames do not reset the candidate. |
| **B4** | Forward caller audio | Replay buffered onset then live frames. Gemini VAD hears the caller and emits `interrupted`. |
| **B5** | First-message guard | If greeting is non-interruptible: do not clear Twilio. Keep playing hello. Still capture the caller transcript. Then allow barge-in on later turns. |
| **B6** | Cancel playout + new queue | Stop sending old PCM. Flush assistant text as interrupted. |
| **B7** | Purge then Twilio clear | `send_clear_now` drops queued media then sends `clear`. A clear stuck behind the queue would keep playing the old sentence. |
| **B8** | Re-anchor | Gemini truncated at its generation cursor. We discarded unplayed audio. Inject what the caller actually heard vs the unspoken tail so the model does not skip ahead. |
| **B9** | False-interrupt recovery | If it was noise and the line goes quiet, resume instead of abandoning the turn. |

---

## 7. Formats to memorize

### Sample-rate strip (draw this first)

| Hop | Direction | Format | Rate | Why |
|-----|-----------|--------|------|-----|
| Phone ↔ Twilio | both | µ-law | **8 kHz** | PSTN / Media Streams contract |
| After `ulaw2lin` | IN | PCM16 mono | **8 kHz** | DSP (RNNoise/Hush) runs here |
| Into Gemini | IN | PCM16 | **16 kHz** | `GEMINI_LIVE_INBOUND_RATE` |
| Out of Gemini | OUT | PCM16 native audio | **24 kHz** | `GEMINI_LIVE_OUTBOUND_RATE` |
| Before Twilio send | OUT | µ-law frames | **8 kHz** | 20 ms = 160 bytes (or 100 ms batch) |

### Key numbers

| Value | Meaning |
|-------|---------|
| **8 kHz** | Twilio both ways |
| **16 kHz** | Gemini inbound |
| **24 kHz** | Gemini outbound |
| **1200 ms** | Server VAD silence (`silence_duration_ms`) |
| **100 ms** | Inbound flush / min send interval |
| **400 ms** | Max zero-fill (4 frames) |
| **300 ms** | Barge debounce (3 frames) |
| **1013** | Pod full WebSocket close code |
| **1011** | Gemini error on burst sends |

### Interview closer line

> Call setup differs. The live media path does not. Inbound audio is decode, DSP, gate, 16 kHz, Gemini VAD. Outbound audio is 24 kHz, queue, 8 kHz µ-law, paced. Transcripts are Live ASR on that same socket, written off the audio path.

---

**Related:** [AI Engineer Prep README](./README.md) · [System Design Module 14](../System_Design_Prep/14_AI_LLM_System_Design.md)
