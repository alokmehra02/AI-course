import {
  Button,
  Callout,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Pill,
  Row,
  Stack,
  Stat,
  Table,
  Text,
  useCanvasAction,
  useCanvasState,
  useHostTheme,
} from "cursor/canvas";

type Tab =
  | "overview"
  | "setup"
  | "audio-in"
  | "audio-out"
  | "gemini"
  | "barge"
  | "formats";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Big picture" },
  { id: "setup", label: "Call setup" },
  { id: "audio-in", label: "Audio IN" },
  { id: "audio-out", label: "Audio OUT" },
  { id: "gemini", label: "Gemini brain" },
  { id: "barge", label: "Barge-in" },
  { id: "formats", label: "Formats to memorize" },
];

export default function GeminiLivePipelineWhiteboard() {
  const [tab, setTab] = useCanvasState<Tab>("pipeline-tab", "overview");
  const dispatch = useCanvasAction();

  return (
    <Stack gap={20}>
      <Stack gap={6}>
        <H1>Gemini Live pipeline whiteboard</H1>
        <Text tone="secondary">
          Inbound audio is caller to Gemini. Outbound audio is Gemini to caller.
          Call setup (who dials) is a separate board. After the Media Stream
          starts, both inbound and outbound calls share this same audio path.
        </Text>
        <Row gap={8}>
          <Button
            variant="secondary"
            onClick={() =>
              dispatch({
                type: "openFile",
                path: "AI_Engineer_Prep/GEMINI_LIVE_VOICE_AGENT_INTERVIEW_GUIDE.md",
              })
            }
          >
            Open interview guide
          </Button>
        </Row>
      </Stack>
      <Row gap={8} wrap>
        {TABS.map((item) => (
          <Pill
            key={item.id}
            active={tab === item.id}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </Pill>
        ))}
      </Row>
      {tab === "overview" ? <OverviewBoard /> : null}
      {tab === "setup" ? <SetupBoard /> : null}
      {tab === "audio-in" ? <AudioInBoard /> : null}
      {tab === "audio-out" ? <AudioOutBoard /> : null}
      {tab === "gemini" ? <GeminiBoard /> : null}
      {tab === "barge" ? <BargeBoard /> : null}
      {tab === "formats" ? <FormatsBoard /> : null}
    </Stack>
  );
}

function OverviewBoard() {
  return (
    <Stack gap={20}>
      <Callout tone="info" title="One sentence to open with">
        Twilio streams 8 kHz µ-law. We clean and gate it, resample to 16 kHz,
        and send it into Gemini Live native audio. Gemini speaks 24 kHz PCM. We
        resample, encode µ-law, and pace it back to Twilio in real time.
        Transcripts ride the same Live socket.
      </Callout>

      <H2>Remember the loop as three lanes</H2>
      <Grid columns={3} gap={16}>
        <Lane
          title="Lane A — Audio IN"
          subtitle="Caller speech"
          steps={[
            "Phone / PSTN",
            "Twilio 8 kHz µ-law",
            "Decode PCM 8 kHz",
            "DSP + send gate",
            "Resample 16 kHz",
            "Gemini send_realtime_input",
          ]}
        />
        <Lane
          title="Lane B — Gemini brain"
          subtitle="Same Live WebSocket"
          steps={[
            "Server VAD (turn taking)",
            "Native audio generate",
            "input + output transcripts",
            "Tools / RAG / end_call",
            "interrupted + turn_complete",
            "Authorize next spoken turn",
          ]}
        />
        <Lane
          title="Lane C — Audio OUT"
          subtitle="Agent speech"
          steps={[
            "Gemini 24 kHz PCM",
            "Outbound queue (delay, not drop)",
            "Resample 8 kHz",
            "Encode µ-law + pace frames",
            "Twilio media JSON",
            "Phone hears the agent",
          ]}
        />
      </Grid>

      <H2>Twilio events that wrap both lanes</H2>
      <Table
        headers={["Order", "Event", "What happens", "Audio yet?"]}
        rows={[
          [
            "0",
            "Call setup",
            "Inbound: number maps to agent. Outbound: we dial, preconnect on ringing.",
            "No",
          ],
          [
            "1",
            "connected",
            "Twilio opens wss://…/ws/voice. Store streamSid.",
            "No",
          ],
          [
            "2",
            "start",
            "Load agent, create conversation, start GeminiLiveTwilioAdapter (adopt preconnect if voice+locale match).",
            "No",
          ],
          [
            "3",
            "media",
            "Repeating inbound µ-law frames. This is Lane A. Lane C sends media the other way on the same socket.",
            "Yes",
          ],
          [
            "4",
            "stop",
            "Hangup. Stop session, persist leftover transcripts, close WS so TwiML Redirect can transfer.",
            "Ends",
          ],
        ]}
      />

      <Callout tone="warning" title="Do not mix these two meanings of inbound/outbound">
        Call inbound vs outbound = who started the phone call. Audio inbound vs
        outbound = which way samples flow after the Stream is live. Interviewers
        often say “inbound pipeline” and mean audio IN. Say which one you mean.
      </Callout>
    </Stack>
  );
}

function SetupBoard() {
  return (
    <Stack gap={16}>
      <Text>
        Setup is the only place inbound and outbound calls really differ. After
        step S5 both join the same Media Stream audio pipeline.
      </Text>
      <Grid columns={2} gap={20}>
        <Stack gap={10}>
          <H2>Outbound call (we dial)</H2>
          <Step
            n="S1"
            title="Create call session"
            detail="Quick Call / campaign stores agent, system prompt, voice, language, dynamic variables, To number."
          />
          <Step
            n="S2"
            title="Twilio REST dials the customer"
            detail="Outbound API call. Status callbacks: initiated, ringing, answered, completed."
          />
          <Step
            n="S3"
            title="Ringing → preconnect Gemini"
            detail="preconnect_gemini_live(call_sid) opens Gemini Live during ring so answer is not a cold connect. Greeting transcripts buffer until the adapter binds."
          />
          <Step
            n="S4"
            title="Answer → Voice webhook"
            detail="Twilio asks for TwiML. We already know org, agent, prompt. AMD may later flag voicemail."
          />
          <Step
            n="S5"
            title="TwiML Connect + Stream"
            detail="wss://…/ws/voice with agentId, organizationId, call_sid, language, call_direction=outbound, patient_phone=To. Native Gemini greeting (no Google TTS)."
          />
        </Stack>
        <Stack gap={10}>
          <H2>Inbound call (they dial us)</H2>
          <Step
            n="S1"
            title="Customer dials Twilio number"
            detail="PSTN hits our Voice webhook. No call session exists yet."
          />
          <Step
            n="S2"
            title="Map number → org + agent"
            detail="InboundRoutingService on the Called number. If none: Say + Hangup fallback, no Stream."
          />
          <Step
            n="S3"
            title="Create inbound session"
            detail="QuickCallService.create_inbound_call_session. patient_phone=From, call_direction=inbound. Usually no preconnect — Stream starts immediately."
          />
          <Step
            n="S4"
            title="Optional inbound recording"
            detail="If enabled, recording starts here. Outbound recording is handled on the dial path instead."
          />
          <Step
            n="S5"
            title="Same TwiML Connect + Stream"
            detail="Same /ws/voice. Custom params include call_direction=inbound. Gemini connects cold on start unless a race preconnect exists."
          />
        </Stack>
      </Grid>

      <Divider />
      <H2>Shared after Stream (both call directions)</H2>
      <Step
        n="S6"
        title="Pod admission"
        detail="try_acquire. If full: accept WebSocket then close 1013 (try later). Never close before accept — that becomes HTTP 403."
      />
      <Step
        n="S7"
        title="connected + start"
        detail="Resolve locale the same way as preconnect (do not collapse en-IN → en-US). Adopt preconnect only if voice and locale match. Else cold GeminiLiveSession.start()."
      />
      <Step
        n="S8"
        title="LiveConnectConfig"
        detail="response_modalities AUDIO, voice, system instruction (accent first), tools, input+output transcription, server VAD, session_resumption, sliding-window compression."
      />
      <Step
        n="S9"
        title="Greeting kickoff"
        detail="If Gemini owns the hello: send_client_content text kickoff, turn_complete=true, authorize initial_greeting. If Twilio already played cached audio: tell Gemini not to repeat; emit system greeting into the transcript."
      />
      <Step
        n="S10"
        title="Three tasks now run"
        detail="receive_loop (Gemini → us), playout_loop (us → Twilio), silence_timeout_loop. media events feed send_audio."
      />
    </Stack>
  );
}

function AudioInBoard() {
  return (
    <Stack gap={16}>
      <Callout tone="info" title="Say this">
        Every ~20 ms Twilio gives us 160 bytes of µ-law on track=inbound. We
        decode, denoise, gate, resample to 16 kHz, and only then call Gemini.
        We never forward the outbound track or we barge in on ourselves.
      </Callout>
      <Grid columns={2} gap={24}>
        <Stack gap={10}>
          <H2>Twilio hop</H2>
          <Step
            n="I1"
            title="Caller speaks into the handset"
            detail="PSTN / SIP. Analog at the phone, 8 kHz µ-law by the time it is Twilio Media Streams."
            fmt="phone"
          />
          <Step
            n="I2"
            title="Twilio Media Streams JSON"
            detail={'event=media, media.payload=base64, media.track=inbound, streamSid set.'}
            fmt="JSON + base64"
          />
          <Step
            n="I3"
            title="Drop non-inbound tracks"
            detail="should_forward_twilio_track: only inbound / inbound_track. Outbound is our own voice echoed back."
          />
          <Step
            n="I4"
            title="Base64 decode"
            detail="Raw µ-law bytes. Empty payload is skipped."
            fmt="µ-law 8 kHz"
          />
          <Step
            n="I5"
            title="µ-law → PCM16"
            detail="adapter.add_audio_chunk → audioop.ulaw2lin. DSP only understands linear PCM."
            fmt="PCM16 8 kHz"
          />
          <Step
            n="I6"
            title="Buffer 5 frames (~100 ms)"
            detail="send_audio appends. Flush at 5 chunks. Cap 10 and keep newest 5 if the event loop lagged — bursting causes Gemini error 1011."
          />
        </Stack>
        <Stack gap={10}>
          <H2>DSP (off the event loop)</H2>
          <Step
            n="I7"
            title="process_inbound_pcm_for_gemini"
            detail="run_dsp / thread pool. Never inline on asyncio. ~10 ms per 100 ms chunk."
          />
          <Step
            n="I8"
            title="Noise suppress + AGC"
            detail="Default RNNoise. Or Hush (DeepFilterNet) or Wiener. AGC target about -16 dBFS so quiet handsets reach Gemini."
          />
          <Step
            n="I9"
            title="Near / far + music-like + transients"
            detail="Near-field confidence. TV/music latch. Horns/slams attenuated and not treated as barge-in. Soft-speech rescue for quiet callers."
          />
          <Step
            n="I10"
            title="Audio mode foreground_safe"
            detail="Speech: ~10% raw + 90% denoised so consonants survive. Background: fully filtered. Max speech attenuation ~8 dB or raw-speech guard."
            fmt="PCM16 8 kHz"
          />
          <Step
            n="I11"
            title="Quality class"
            detail="GOOD / LOW_VOLUME / NOISY_BACKGROUND. Tightens barge debounce and noise gate. May later speak one noise warning."
          />
        </Stack>
      </Grid>
      <H2>Send gate, then Gemini</H2>
      <Grid columns={2} gap={24}>
        <Stack gap={10}>
          <Step
            n="I12"
            title="Client gate _gate_inbound_audio"
            detail="This is NOT the turn-taker. It decides pass / mute / buffer-for-barge. µ-law idle RMS ~8 is not speech."
          />
          <Step
            n="I13"
            title="Mute cap + zero-fill cap"
            detail="Max 4 consecutive destructive mutes (~400 ms). Then leak attenuated audio. Must stay under Gemini silence_duration_ms 1200 ms or we fake end-of-turn."
          />
          <Step
            n="I14"
            title="Silence-hold bookkeeping"
            detail="Near-field speech holds the 'are you still there?' ladder so long answers are not treated as hangups."
          />
        </Stack>
        <Stack gap={10}>
          <Step
            n="I15"
            title="Resample 8 kHz → 16 kHz"
            detail="audioop.ratecv with persistent state (no clicks at chunk edges)."
            fmt="PCM16 16 kHz"
          />
          <Step
            n="I16"
            title="Min send interval ~100 ms"
            detail="Sleep if we would send faster. Second 1011 defense."
          />
          <Step
            n="I17"
            title="send_realtime_input"
            detail={'Blob mime_type audio/pcm;rate=16000. Gemini server VAD now sees this stream.'}
            fmt="Gemini Live WS"
          />
        </Stack>
      </Grid>
    </Stack>
  );
}

function AudioOutBoard() {
  return (
    <Stack gap={16}>
      <Callout tone="info" title="Say this">
        Gemini emits 24 kHz native speech, not text-then-TTS. We never dump it
        into Twilio as fast as it arrives. We pace µ-law at 8 kHz real time.
        Backpressure delays audio. Only barge-in drops queued speech.
      </Callout>
      <Grid columns={2} gap={24}>
        <Stack gap={10}>
          <H2>From Gemini</H2>
          <Step
            n="O1"
            title="model_turn inline_data audio"
            detail="24 kHz PCM16 chunks on the Live receive loop. Text-only thought parts do not consume the one-turn audio token."
            fmt="PCM16 24 kHz"
          />
          <Step
            n="O2"
            title="TURN-GUARD"
            detail="Play only if authorized (greeting, user_transcript, silence prompt, tool follow-up). Extra noise-triggered turns are dropped."
          />
          <Step
            n="O3"
            title="Mute after end_call"
            detail="_muted / _mute_after_turns: do not keep talking after goodbye tool."
          />
          <Step
            n="O4"
            title="Put on outbound PCM queue"
            detail="Bounded queue. If full, await — lossless. Dropping here chops the start of the sentence."
          />
          <Step
            n="O5"
            title="playout_loop"
            detail="Marks _assistant_speaking. First chunk of the call is first_frame latency. Later chunks batch up to ~500 ms."
          />
          <Step
            n="O6"
            title="send_audio_paced"
            detail="ratecv 24 kHz → 8 kHz with persistent resample state."
            fmt="PCM16 8 kHz"
          />
        </Stack>
        <Stack gap={10}>
          <H2>To the phone</H2>
          <Step
            n="O7"
            title="PCM → µ-law"
            detail="audioop.lin2ulaw. This is what Twilio Media Streams accepts outbound."
            fmt="µ-law 8 kHz"
          />
          <Step
            n="O8"
            title="Slice frames"
            detail="Legacy 20 ms = 160 bytes. Optional 100 ms batching to wake the event loop less often. Audio to the ear is identical."
          />
          <Step
            n="O9"
            title="JSON media event"
            detail={'event=media, streamSid, payload=base64. TwilioOutboundQueueWriter enqueues; does not send on the Gemini loop.'}
          />
          <Step
            n="O10"
            title="media_sender task"
            detail="Dedicated task drains the WS send queue. Congestion delays. Timeouts are logged as backpressure, frames are not deleted."
          />
          <Step
            n="O11"
            title="Pace to real time"
            detail="Sleep by actual frame duration (len/8000). If behind, yield. If debt exceeds max pacing debt, rebase to now — shift later, lose nothing."
          />
          <Step
            n="O12"
            title="Twilio plays to PSTN"
            detail="Caller hears the agent. _assistant_speaking stays true until estimated playout finishes, not when our local queue empties."
            fmt="phone"
          />
        </Stack>
      </Grid>
      <Callout tone="warning" title="O13 — the exception that drops audio">
        On barge-in, send_clear_now purges queued outbound frames then sends
        Twilio clear. That is the only correct drop: the caller interrupted, so
        stale agent speech must never play.
      </Callout>
    </Stack>
  );
}

function GeminiBoard() {
  return (
    <Stack gap={16}>
      <H2>What Gemini Live actually does</H2>
      <Text>
        Native audio-to-audio. One bidirectional WebSocket. No separate Google
        STT and no separate TTS in this stack.
      </Text>
      <Grid columns={2} gap={24}>
        <Stack gap={10}>
          <H3>Server VAD (the real turn-taker)</H3>
          <Step
            n="G1"
            title="automatic_activity_detection on"
            detail="CLIENT_ACTIVITY_CONTROL is False. We do not send activityStart/activityEnd. Gemini owns start and end of speech."
          />
          <Step
            n="G2"
            title="Start HIGH, end LOW"
            detail="Catch speech quickly. Do not cut slow speakers. prefix_padding_ms ~300 keeps the first consonant."
          />
          <Step
            n="G3"
            title="silence_duration_ms = 1200"
            detail="3500 in slow_speech_mode. After this much silence in what we forwarded, Gemini ends the user turn and replies."
          />
          <Step
            n="G4"
            title="START_OF_ACTIVITY_INTERRUPTS"
            detail="If Gemini hears caller speech in the audio we send, it stops generating. That is barge-in at the API."
          />
        </Stack>
        <Stack gap={10}>
          <H3>Receive loop branches</H3>
          <Step
            n="G5"
            title="input_transcription"
            detail="Caller ASR on audio we forwarded. Usability check. Persist always (rejected gets asr_rejected). Accepted authorizes the next spoken turn."
          />
          <Step
            n="G6"
            title="output_transcription"
            detail="Fragments concatenated until turn_complete. Interrupted flush is saved with interrupted=true because the caller already heard it."
          />
          <Step
            n="G7"
            title="tool_call"
            detail="query_knowledge_base, end_call, transfer, handoff, EMR. Tool does not consume the audio authorization. FunctionResponse then spoken answer."
          />
          <Step
            n="G8"
            title="go_away / resumption / usage"
            detail="Log time_left. Store resumption handle. Merge usage_metadata into gemini_live_usage ledger (billing source of truth)."
          />
        </Stack>
      </Grid>
      <H2>Transcript writes (not on the audio path)</H2>
      <Step
        n="G9"
        title="Fire-and-forget DB write"
        detail="_spawn_turn_write with timeout, retry, write_id. Receive loop never awaits Postgres. Script mismatch is annotation only. After hangup, script normalizer re-spells wrong alphabet without translating."
      />
    </Stack>
  );
}

function BargeBoard() {
  return (
    <Stack gap={16}>
      <Callout tone="info" title="Memory hook">
        Confirm, then interrupt, then clear, then re-anchor. Four verbs.
      </Callout>
      <Step
        n="B1"
        title="Agent is speaking"
        detail="_assistant_speaking or greeting_active. Inbound frames are mute-by-default."
      />
      <Step
        n="B2"
        title="Is this a barge candidate?"
        detail="Not µ-law idle. Not transient. Not music-like. Near-field / voiced. Greeting uses a higher RMS floor so connect pops do not cut hello."
      />
      <Step
        n="B3"
        title="Debounce"
        detail="Buffer consecutive speech frames. 3 frames (~300 ms), or 4 if NOISY_BACKGROUND. Gaps of 1–2 frames do not reset the candidate."
      />
      <Step
        n="B4"
        title="Forward caller audio"
        detail="Replay buffered onset then live frames. Gemini VAD hears the caller and emits interrupted."
      />
      <Step
        n="B5"
        title="First-message guard"
        detail="If greeting is non-interruptible: do not clear Twilio. Keep playing hello. Still capture the caller transcript. Then allow barge-in on later turns."
      />
      <Step
        n="B6"
        title="Cancel playout + new queue"
        detail="Stop sending old PCM. Flush assistant text as interrupted."
      />
      <Step
        n="B7"
        title="Purge then Twilio clear"
        detail="send_clear_now drops queued media then sends clear. A clear stuck behind the queue would keep playing the old sentence."
      />
      <Step
        n="B8"
        title="Re-anchor"
        detail="Gemini truncated at its generation cursor. We discarded unplayed audio. Inject what the caller actually heard vs the unspoken tail so the model does not skip ahead."
      />
      <Step
        n="B9"
        title="False-interrupt recovery"
        detail="If it was noise and the line goes quiet, resume instead of abandoning the turn."
      />
    </Stack>
  );
}

function FormatsBoard() {
  return (
    <Stack gap={16}>
      <H2>Write this strip on the whiteboard first</H2>
      <Table
        headers={["Hop", "Direction", "Format", "Rate", "Why"]}
        rows={[
          ["Phone ↔ Twilio", "both", "µ-law", "8 kHz", "PSTN / Media Streams contract"],
          ["After ulaw2lin", "IN", "PCM16 mono", "8 kHz", "DSP (RNNoise/Hush) runs here"],
          ["Into Gemini", "IN", "PCM16", "16 kHz", "GEMINI_LIVE_INBOUND_RATE"],
          ["Out of Gemini", "OUT", "PCM16 native audio", "24 kHz", "GEMINI_LIVE_OUTBOUND_RATE"],
          ["Before Twilio send", "OUT", "µ-law frames", "8 kHz", "20 ms = 160 bytes (or 100 ms batch)"],
        ]}
      />
      <Grid columns={4} gap={12}>
        <Stat value="8k" label="Twilio both ways" />
        <Stat value="16k" label="Gemini inbound" />
        <Stat value="24k" label="Gemini outbound" />
        <Stat value="1200 ms" label="Server VAD silence" />
      </Grid>
      <Grid columns={4} gap={12}>
        <Stat value="100 ms" label="Inbound flush / min send" />
        <Stat value="400 ms" label="Max zero-fill (4 frames)" />
        <Stat value="300 ms" label="Barge debounce (3 frames)" />
        <Stat value="1013" label="Pod full close code" />
      </Grid>
      <H2>Interview closer line</H2>
      <Text weight="semibold">
        Call setup differs. The live media path does not. Inbound audio is
        decode, DSP, gate, 16 kHz, Gemini VAD. Outbound audio is 24 kHz, queue,
        8 kHz µ-law, paced. Transcripts are Live ASR on that same socket, written
        off the audio path.
      </Text>
    </Stack>
  );
}

function Lane({
  title,
  subtitle,
  steps,
}: {
  title: string;
  subtitle: string;
  steps: string[];
}) {
  const theme = useHostTheme();
  return (
    <Stack gap={8}>
      <H3>{title}</H3>
      <Text size="small" tone="tertiary">
        {subtitle}
      </Text>
      <Stack gap={6}>
        {steps.map((step, index) => (
          <div key={step}>
            <Row gap={8} align="center">
              <div
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: 4,
                  background: theme.fill.tertiary,
                  color: theme.text.secondary,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 11,
                  fontWeight: 590,
                  flexShrink: 0,
                }}
              >
                {index + 1}
              </div>
              <Text size="small">{step}</Text>
            </Row>
          </div>
        ))}
      </Stack>
    </Stack>
  );
}

function Step({
  n,
  title,
  detail,
  fmt,
}: {
  n: string;
  title: string;
  detail: string;
  fmt?: string;
}) {
  const theme = useHostTheme();
  return (
    <Row gap={10} align="start">
      <div
        style={{
          minWidth: 36,
          height: 22,
          paddingLeft: 6,
          paddingRight: 6,
          borderRadius: 4,
          background: theme.accent.primary,
          color: theme.text.onAccent,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 11,
          fontWeight: 590,
          flexShrink: 0,
          marginTop: 1,
        }}
      >
        {n}
      </div>
      <Stack gap={2} style={{ minWidth: 0, flex: 1 }}>
        <Row gap={8} align="center" wrap>
          <Text weight="semibold">{title}</Text>
          {fmt ? (
            <Text size="small" tone="tertiary">
              {fmt}
            </Text>
          ) : null}
        </Row>
        <Text size="small" tone="secondary">
          {detail}
        </Text>
      </Stack>
    </Row>
  );
}
