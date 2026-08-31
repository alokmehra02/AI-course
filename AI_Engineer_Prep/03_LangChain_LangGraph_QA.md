# 03 — LangChain & LangGraph Interview Q&A (Additional)

**Format:** **Say this** = speak in interview · **Compare** = why one vs other · **Follow-up** = next question they ask

**Note:** [Infosys_Interview_Prep/04_LangChain_LangGraph_Agents_QA.md](../Infosys_Interview_Prep/04_LangChain_LangGraph_Agents_QA.md) has the **30 base questions** (LangChain basics, LangGraph nodes, VoXgent flow). This file adds **15 advanced questions** on checkpointing, subgraphs, production patterns.

**Audience:** Alok — ~2 years exp, VoXgent (RAG, LangGraph, Pinecone, voice agents, GCP), FastAPI/Python

---

## A. Persistence & checkpointing

### Q1. What is checkpointing in LangGraph?

**Say this:**

> Checkpointing saves graph **state** after each node so you can resume, replay, or debug a run. LangGraph writes checkpoints to a checkpointer — in-memory for dev, **Postgres** or **SQLite** for production. Each step gets a `thread_id`; state includes messages, retrieved docs, flags like `needs_human`. On VoXgent we used checkpoints to inspect why a call routed to human transfer without re-running Twilio.

**Compare:**

> **Stateless run** = fast, no history if server restarts. **Checkpointed** = durable, supports HITL pause and audit — required for production agents.

**Follow-up:**

1. **What is a thread_id?**  
   **Say this:** Stable ID per conversation — phone call SID or session UUID. All checkpoints for that call share it.

---

### Q2. How does persistence work with a checkpointer?

**Say this:**

> Compile graph with `checkpointer=PostgresSaver(...)`. Every node execution persists merged state. New invoke uses same `thread_id` to load latest checkpoint and continue. Enables multi-turn voice: user calls back, graph picks up history if you keep thread mapping in your DB.

**Follow-up:**

1. **What do you store outside LangGraph?**  
   **Say this:** Business records — CRM IDs, billing — in your app DB. Checkpointer holds orchestration state, not source of truth for customer data.

---

### Q3. What is time-travel debugging?

**Say this:**

> With checkpoints you can list history for a `thread_id` and **replay from any prior step** — change a node or prompt and fork. LangGraph Studio shows this visually. On VoXgent debugging, we replayed from the retrieve node with a fixed query to see if bad answer was retrieval or generation.

**Compare:**

> **Print debugging** = one run, gone. **Time travel** = reproduce production failure at exact graph step — worth the Postgres checkpointer cost.

**Follow-up:**

1. **Can you edit past state in prod?**  
   **Say this:** Only in staging or support tools with auth — never silently mutate prod checkpoints without audit log.

---

## B. Graph structure

### Q4. What are subgraphs?

**Say this:**

> A **subgraph** is a graph used as a node inside a parent graph. Example: `rag_subgraph` does rewrite → retrieve → rank; parent graph calls it then branches to tool or respond. Keeps files small and teams can own subgraphs. VoXgent could split `sales_flow` and `support_flow` subgraphs sharing a common `retrieve` subgraph.

**Compare:**

> **One giant graph** = hard to test. **Subgraphs** = modular, reusable — compile parent with `add_node("rag", rag_graph)`.

**Follow-up:**

1. **State across subgraph boundary?**  
   **Say this:** Parent and child share schema or map fields — define shared keys like `messages` and `retrieved_docs` explicitly.

---

### Q5. How do you run parallel nodes in LangGraph?

**Say this:**

> Fan out from one node to multiple nodes that do not depend on each other — e.g. **retrieve from Pinecone** and **fetch CRM summary** in parallel — then a join node merges results into state. Cuts latency on VoXgent when we needed both RAG context and live account status before speaking.

**Compare:**

> **Sequential** = simpler, slower. **Parallel** = faster, need join node and error handling if one branch fails.

**Follow-up:**

1. **One branch fails?**  
   **Say this:** Join node checks partial results — proceed with RAG only, or retry branch, or escalate to human.

---

### Q6. How do you stream from a LangGraph run?

**Say this:**

> Use `graph.stream()` or `astream_events()` — yields state updates or LLM tokens per node. FastAPI wraps async generator as SSE to client. For voice, stream only from the **respond** node LLM, not internal classify nodes. Filter events by `on_chat_model_stream` so TTS does not read tool JSON aloud.

**Compare:**

> **invoke()** = full result at end. **stream()** = incremental — required for chat and voice UX.

**Follow-up:**

1. **Stream state vs stream tokens?**  
   **Say this:** `stream_mode="updates"` for node completion; `astream_events` for token-level — pick based on UI needs.

---

## C. Human-in-the-loop & tools

### Q7. What is interrupt / HITL in LangGraph?

**Say this:**

> **Interrupt** pauses the graph before or after a node — e.g. before CRM write — and waits for human approval via API. Checkpointer holds state while paused. Resume with `Command(resume=...)` and human decision. VoXgent used light HITL for high-value sales leads; voice transfers were the main "human" path.

**Compare:**

> **Auto-execute tools** = fast, risky for writes. **Interrupt** = compliance and trust — adds latency, needs dashboard for approvers.

**Follow-up:**

1. **Timeout on interrupt?**  
   **Say this:** Yes — if no approval in N minutes, route to cancel or default safe action, notify ops.

---

### Q8. What are state reducers?

**Say this:**

> Reducers define how node updates merge into state. Default for lists is often **append** — new messages add to `messages`. Other fields **replace** — `retrieved_docs` overwrites each retrieval. Wrong reducer causes duplicate messages or lost docs. VoXgent typed state with `Annotated[list, add_messages]` for chat history.

**Compare:**

> **Replace** = last write wins. **Append** = accumulate. **Custom reducer** = dedupe by ID or merge dicts — use when needed.

**Follow-up:**

1. **Bug from wrong reducer?**  
   **Say this:** Messages doubling every node or retrieval disappearing — fix schema annotations before blaming the LLM.

---

### Q9. What is ToolNode?

**Say this:**

> LangGraph prebuilt **ToolNode** runs tools the assistant requested — reads `tool_calls` from last AI message, executes functions, returns `ToolMessage`s. Pairs with `tools_condition` edge back to model or end. VoXgent used ToolNode for Salesforce lookup and calendar booking instead of hand-rolled tool loop.

**Compare:**

> **Manual tool loop** = full control, more code. **ToolNode** = standard pattern, faster to ship — still validate args with Pydantic inside each tool.

**Follow-up:**

1. **Tool throws exception?**  
   **Say this:** Catch in tool wrapper, return error string in ToolMessage so model can apologize or retry — never crash the graph.

---

## D. Agents & migration

### Q10. Limits of prebuilt ReAct agent?

**Say this:**

> `create_react_agent` is great for demos — model picks tools in a loop. Production limits: **opaque routing**, hard to cap specific paths, weak observability per business step, loop risk, and tough compliance story. VoXgent moved to **explicit graph** — fixed nodes for retrieve, classify, tool, respond — LLM decides inside nodes, graph decides what's allowed next.

**Compare:**

> **ReAct agent** = fast prototype. **Custom graph** = production control, testable nodes, clear SLAs.

**Follow-up:**

1. **When is ReAct enough?**  
   **Say this:** Internal admin tools, low-risk read-only APIs, proof of concept before you know the flow.

---

### Q11. How do you migrate a LangChain chain to LangGraph?

**Say this:**

> Map each chain step to a **node** — retriever node, prompt+LLM node. Replace pipe with **edges**; add **conditional edges** where you had if/else in Python. Move shared data to **state** dict. Start by wrapping existing LCEL runnables inside nodes — no need to rewrite retriever day one. VoXgent migration added rewrite loop and human branch that chain could not express cleanly.

**Compare:**

> **Big-bang rewrite** = risky. **Incremental** = one node at a time, same runnables inside — lower risk.

**Follow-up:**

1. **First node to add in migration?**  
   **Say this:** Confidence check after retrieve — conditional edge to retry or human — that is the usual pain point chains hack around.

---

## E. Testing & production

### Q12. How do you test LangGraph graphs?

**Say this:**

> **Unit test** each node function with mock state — assert partial state update. **Integration test** compile graph with mock LLM and mock retriever — assert path to END or human node. **Snapshot** golden `thread_id` runs in CI. VoXgent tested: low retrieval score → human node; tool timeout → fallback message.

**Compare:**

> **Testing whole agent with live API** = flaky and costly. **Mocked graph tests** = fast CI; staging with real Pinecone subset weekly.

**Follow-up:**

1. **How to mock LLM?**  
   **Say this:** Return fixed AIMessage with tool_calls or content — LangChain fake chat model or patch `bind_tools` runnable.

---

### Q13. Production timeouts — where do you set them?

**Say this:**

> Layer timeouts: **HTTP** to Twilio webhook, **per-node** timeout in wrapper, **LLM client** read timeout, **graph global** deadline — `asyncio.wait_for` on `ainvoke`. VoXgent voice cap ~8–12s total; retrieve 2s, LLM 5s, tools 3s — if exceeded, speak apology and offer callback.

**Compare:**

> **No timeout** = hung calls and angry users. **Aggressive timeout** = fallbacks too often — tune from p95 metrics.

**Follow-up:**

1. **Timeout mid-checkpoint?**  
   **Say this:** State is saved at last completed node — next webhook can resume or start fresh with summarized context; document idempotency for Twilio retries.

---

### Q14. Observability for LangGraph in production?

**Say this:**

> Log **node name**, enter/exit time, state keys changed, retrieval scores, tool names, token usage. Trace ID from FastAPI through graph. Optional LangSmith for visual traces. Alert on human-transfer rate spike — often retrieval or tool regression.

**Follow-up:**

1. **What not to log?**  
   **Say this:** PHI, full prompts with PII — log hashes and chunk IDs instead for healthcare clients.

---

### Q15. Master answer — "Why LangGraph for VoXgent?"

**Say this:**

> Voice agents need **loops** — retry retrieval, **branches** — answer vs tool vs human, **durable state** — checkpoints per call, **parallel** fetches, and **timeouts** per step. LangChain chains are linear; ReAct agents are a black box. LangGraph made the flow explicit, testable, and observable. LangChain still wired retriever and tools inside nodes — blocks plus graph, not either-or.

**Follow-up:**

1. **30-second version?**  
   **Say this:** "LangChain wired RAG and tools. VoXgent needed loops — retry search, call CRM, transfer to human. That control flow is LangGraph."

---

**Related:** [Infosys 04 — LangChain & LangGraph (30 base Qs)](../Infosys_Interview_Prep/04_LangChain_LangGraph_Agents_QA.md) · [01_LLM_Fundamentals_QA.md](./01_LLM_Fundamentals_QA.md) · [02_RAG_Pipeline_QA.md](./02_RAG_Pipeline_QA.md) · [04_MCP_Tools_Agentic_AI_QA.md](./04_MCP_Tools_Agentic_AI_QA.md) · [Artifact lesson 6](../Artifacts/lesson_6_langgraph_and_agents.md)
