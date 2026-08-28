# 04 — LangChain, LangGraph & AI Agents Q&A

**Format:** **Say this** = speak in interview · **Compare** = why one vs other · **Follow-up** = next question they ask

---

## A. LangChain basics

### Q1. What is LangChain?

**Say this:**

> LangChain is a Python framework that connects LLMs with other pieces — prompts, retrievers, tools, memory, and parsers. Instead of writing the same glue code again and again, you use ready-made building blocks. On VoXgent I used LangChain for RAG parts like Pinecone retriever and prompt templates. For the full call flow with retries and branching, I moved that to LangGraph.

**Compare:**

> Raw OpenAI SDK = you write everything yourself. LangChain = faster to wire RAG and tools. LangGraph = when the flow is not a straight line.

**Follow-up:**

1. **When would you skip LangChain?**  
   **Say this:** For a single API call or when I need full control and easy debugging, I use the SDK directly. LangChain helps when the app has retriever + tools + prompts together.

2. **Did you use LangChain for the whole VoXgent backend?**  
   **Say this:** No. RAG and tool wiring used LangChain pieces. Orchestration — retrieve, tool, human transfer — was LangGraph because we needed loops and clear state.

---

### Q2. What is LCEL (LangChain Expression Language)?

**Say this:**

> LCEL lets you chain steps with the pipe operator — like prompt, then model, then parser. It is good for a fixed flow: retrieve documents, pass to model, return answer. It supports streaming and batching out of the box.

**Compare:**

> LCEL chains go **one direction**. They cannot easily say: "retrieval failed, rewrite query, try again" or "call tool, then retrieve again." That is where LangGraph takes over.

**Follow-up:**

1. **Give an example LCEL chain for RAG.**  
   **Say this:** `retriever | format_docs | prompt | llm | parser` — user question in, grounded answer out. Fine for FAQ bots. Not enough for multi-step voice agents.

---

### Q3. Chains vs Agents in LangChain?

**Say this:**

> A **chain** has fixed steps — always retrieve, then generate. An **agent** lets the LLM pick which tool to call next. Agents are more flexible but harder to control in production. You need max steps, timeouts, and allowed tool lists.

**Compare:**

> Chain = predictable, easier to test. Agent = flexible but can loop forever or call wrong tools. In production voice, I prefer a **graph with fixed nodes** (LangGraph) over a free-form agent executor.

**Follow-up:**

1. **Which did VoXgent use?**  
   **Say this:** LangGraph with defined nodes — retrieve, classify intent, tool call, respond, or human transfer. The LLM decides inside those nodes, but the graph controls the overall flow.

---

### Q4. What are retrievers in LangChain?

**Say this:**

> A retriever is an interface: you pass a query string, you get back relevant documents. LangChain has Pinecone retriever, BM25, and ensemble retriever for hybrid search. I wrapped ours with a tenant filter so client A never sees client B data.

**Compare:**

> LangChain retriever = quick integration. Custom retriever = when you need strict filters, logging per stage, or custom hybrid ranking. Both are fine — evaluation matters more than the wrapper.

**Follow-up:**

1. **How did you add tenant filter?**  
   **Say this:** Metadata filter on every Pinecone query — `tenant_id` from auth token. Never trust the prompt to say "only use this client docs."

---

### Q5. Output parsers — why use them?

**Say this:**

> The LLM returns text. Parsers turn that into JSON or Pydantic objects. I prefer OpenAI structured output or Pydantic validation with retry — not regex on free text. Production code should never assume the model always returns valid JSON.

**Compare:**

> LangChain parsers help in demos. In production I validate with Pydantic at the API boundary — same whether I use LangChain or raw SDK.

**Follow-up:**

1. **What if JSON is invalid?**  
   **Say this:** Retry once with the validation error in the prompt. If still bad, safe default — like `needs_human: true` — never write bad data to CRM.

---

### Q6. When would you avoid LangChain?

**Say this:**

> When the path is one LLM call, when debugging LangChain abstractions slows me down, or when latency is so tight I want zero extra layers. Many teams use LangChain at the edges and raw SDK in the hot path.

**Follow-up:**

1. **So why use it at all on VoXgent?**  
   **Say this:** It saved time on retriever + prompt + tool definitions. The trade-off was worth it for RAG setup; orchestration still needed LangGraph for production control.

---

## B. LangGraph (high weight for this JD)

### Q7. What is LangGraph?

**Say this:**

> LangGraph models your app as a **graph** — nodes are steps, edges are what happens next, and **state** is shared data passed between steps. You can loop, branch, and stop after N tries. That is built for agents and production workflows, not just one-shot Q&A.

**Compare:**

> **LangChain chain:** A → B → C, mostly one way.  
> **LangGraph:** A → B → if fail go back to A → C → D or END.  
> For VoXgent — retrieve, maybe call Salesforce, maybe transfer to human — you need that branching. LangChain alone makes loops messy; LangGraph makes them explicit.

**Follow-up:**

1. **Is LangGraph a replacement for LangChain?**  
   **Say this:** No. LangGraph often uses LangChain runnables inside nodes. LangChain = building blocks. LangGraph = how those blocks connect in production.

2. **Why not use LangChain AgentExecutor?**  
   **Say this:** AgentExecutor hides the flow. In production I need to see every node, set max retries, log state, and route to human transfer. LangGraph gives that visibility.

---

### Q8. Why LangGraph over LangChain for production?

**Say this:**

> Three reasons on VoXgent: **loops** — if retrieval is weak, rewrite query and search again; **branching** — answer vs tool vs human transfer; **state** — one place for messages, retrieved docs, intent, tool results. LangChain chains do not handle that cleanly. LangGraph does.

**Compare:**

| Need | LangChain chain | LangGraph |
|------|-----------------|-----------|
| Simple RAG Q&A | ✅ Good | Overkill |
| Retry retrieval | ❌ Awkward | ✅ Loop edge |
| Human handoff | ❌ Hacky | ✅ Conditional edge |
| Debug production issue | Hard | Read state per node |
| Voice agent multi-step | Risky | ✅ Built for this |

**Follow-up:**

1. **Example loop in VoXgent?**  
   **Say this:** User asks about policy → retrieve → if confidence low, rewrite query from chat history → retrieve again → if still low, set `needs_human` and Twilio transfer.

---

### Q9. What is State in LangGraph?

**Say this:**

> State is a shared object — usually a typed dict — that every node reads and updates. Example fields: `messages`, `retrieved_docs`, `intent`, `tool_results`, `needs_human`. Nodes return partial updates; reducers merge them, like appending to message list.

**Compare:**

> In a LangChain chain, data passes through the pipe implicitly. In LangGraph, state is **explicit** — you can inspect it after each node, which is gold for production debugging.

**Follow-up:**

1. **What reducers did you use?**  
   **Say this:** Messages append — new turn adds to list. Retrieved docs might replace each retrieval. Tool results append with timestamp.

---

### Q10. Nodes, edges, conditional edges?

**Say this:**

> A **node** is one step — retrieve, call LLM, run tool. An **edge** connects nodes. A **conditional edge** picks the next node based on state — e.g. if `needs_human` then `transfer_node` else `respond_node`.

**Compare:**

> LangChain: you if/else in Python around the chain. LangGraph: routing is part of the graph definition — easier to test and visualize.

**Follow-up:**

1. **Draw VoXgent flow in words.**  
   **Say this:** Start → rewrite query → RAG retrieve → decide node → either tool call → respond, or human transfer, or direct respond → end.

---

### Q11. Cycles / loops — give an example.

**Say this:**

> `retrieve → generate → check faithfulness → if bad, rewrite query → retrieve again` — loop until pass or max 2 hops. Always cap loops or cost and latency explode.

**Compare:**

> Putting a while-loop in LangChain chain code works in a demo. In LangGraph the loop is a **first-class edge** — reviewers and testers can see it.

**Follow-up:**

1. **Max hops you used?**  
   **Say this:** Usually 2 retrieval attempts for voice — latency budget is tight. After that, refuse or human transfer.

---

### Q12. Checkpointing?

**Say this:**

> LangGraph can save state after each node. Useful for long workflows, resume after crash, or pause for human approval. For short voice calls we relied more on DB call state; checkpointing matters more for long async jobs.

**Follow-up:**

1. **Human approval example?**  
   **Say this:** Before CRM write above a threshold, graph pauses, human approves in dashboard, then graph continues — common in enterprise, less in real-time voice.

---

### Q13. Human-in-the-loop (HITL)?

**Say this:**

> Stop the graph before a risky action — refund, CRM update — wait for human OK, then continue. LangGraph supports interrupt and resume. On VoXgent we used intent-based **live transfer** to a human agent on Twilio when confidence was low.

**Compare:**

> LangChain agent: hard to pause mid-flight cleanly. LangGraph: designed for interrupt → wait → resume.

**Follow-up:**

1. **Transfer vs approval?**  
   **Say this:** Transfer = customer talks to human on call. Approval = backend human OKs an automated action. Both are HITL; VoXgent did live transfer more.

---

### Q14. Map VoXgent to a LangGraph.

**Say this:**

> Nodes: ingest user text from voice → rewrite query → Pinecone retrieve → classify (answer / tool / human) → tool node for Salesforce or Sheets → generate response → optional structured summary → end or Twilio transfer. Conditional edges on intent and confidence.

**Follow-up:**

1. **Where does LangChain fit in each node?**  
   **Say this:** Inside the retrieve node — LangChain retriever. Inside generate node — prompt template + LLM. LangGraph only wires the nodes.

---

### Q15. Error recovery in LangGraph?

**Say this:**

> Catch errors inside nodes, write `error` to state, route to fallback or human. Never half-update CRM — use transactions or idempotency keys. After N failures, dead-letter and alert.

**Follow-up:**

1. **Tool timeout?**  
   **Say this:** Set 5–10s timeout on external APIs, return error to state, LLM tells user "system temporarily unavailable" or triggers transfer.

---

## C. Agents

### Q16. What is an AI agent?

**Say this:**

> An agent is a system where the LLM does not just answer once — it can call tools, read results, and keep going until the task is done. RAG gives knowledge; agents add **actions**.

**Compare:**

> RAG-only chain = read knowledge, answer. Agent = read knowledge, check CRM, send SMS, summarize call — VoXgent needed both.

**Follow-up:**

1. **Agent vs chatbot?**  
   **Say this:** Chatbot mostly talks. Agent talks plus uses tools. Our voice platform was an agent with RAG grounding.

---

### Q17. ReAct pattern?

**Say this:**

> ReAct is Reason then Act — model thinks, picks a tool, sees result, repeats until done. LangGraph can implement this as explicit nodes instead of one black-box agent loop.

**Compare:**

> LangChain ReAct agent = quick prototype. LangGraph ReAct-style graph = same idea but visible steps for production.

**Follow-up:**

1. **One-line ReAct?**  
   **Say this:** Think → tool → observe → think → answer.

---

### Q18. Single-agent vs multi-agent?

**Say this:**

> **Single agent** — one LLM, many tools. Simpler, faster, good for voice. **Multi-agent** — separate roles like research agent, writer agent, checker agent. Better for complex tasks, more cost and latency.

**Compare:**

> VoXgent production = single agent + tools + RAG. My side project Multi-Agent Chatbot had specialized agents for learning — not the same as production voice latency needs.

**Follow-up:**

1. **When multi-agent?**  
   **Say this:** When domains conflict — e.g. legal checker separate from sales writer — or when one agent context gets too large.

---

### Q19. Supervisor pattern?

**Say this:**

> A supervisor LLM routes work to worker agents and combines results. Good for enterprise copilots with many skills. Adds one extra LLM call — watch latency.

**Follow-up:**

1. **Used on VoXgent?**  
   **Say this:** No — we used a classify node in the graph instead of a full supervisor multi-agent setup.

---

### Q20. Agent failure modes?

**Say this:**

> Infinite tool loops, wrong tool picked, bad tool arguments, prompt injection through tool output, runaway token cost. Fix with max steps, tool allowlist, schema validation, and budgets.

**Compare:**

> LangChain AgentExecutor without limits = demo. LangGraph with max hops and conditional END = production.

**Follow-up:**

1. **Max steps?**  
   **Say this:** Typically 3–5 tool rounds for voice; more for async backend jobs.

---

### Q21. Planning vs reactive agents?

**Say this:**

> **Planning** — model writes full plan first, then executes. **Reactive** — picks next tool each turn. Reactive fits call-center style turns. Planning fits long research tasks.

**Follow-up:**

1. **VoXgent style?**  
   **Say this:** Reactive — each user utterance triggers retrieve → decide → act. No long plan upfront.

---

## D. Tools & Memory

### Q22. Good tool definition?

**Say this:**

> Clear name, detailed description — the model reads description to pick tools — JSON schema with types and enums, note if it writes data. Bad description = wrong tool calls.

**Follow-up:**

1. **Salesforce tool example?**  
   **Say this:** `create_lead` — description says when to use it, schema has required fields name, email, company — backend validates before API call.

---

### Q23. Parallel tool calls?

**Say this:**

> Model can request two tools at once — e.g. read CRM and read KB. Run safe reads in parallel; serialize writes to avoid race conditions.

**Follow-up:**

1. **Async in FastAPI?**  
   **Say this:** Yes — `asyncio.gather` for parallel read tools, single queue for writes.

---

### Q24. Short-term vs long-term memory?

**Say this:**

> **Short-term** — last few turns in graph state or Redis. **Long-term** — summarized history or user prefs in DB. Voice keeps short-term small for speed; full summary saved after call.

**Compare:**

> LangChain memory classes help in chat demos. Production = Redis + Postgres with clear TTL and size limits.

**Follow-up:**

1. **How many turns in context?**  
   **Say this:** Often 2–4 for voice; more for text chat if token budget allows.

---

### Q25. Memory vs RAG — difference?

**Say this:**

> **RAG** = search company documents — policies, product sheets. **Memory** = this user's conversation — "you asked about dental last turn." Both can use vectors but different indexes and purposes.

**Follow-up:**

1. **Same Pinecone index?**  
   **Say this:** Better separate — KB index vs conversation memory store — different update rules and filters.

---

## E. Design & resume

### Q26. LangChain vs LlamaIndex?

**Say this:**

> LangChain is general — chains, agents, tools. LlamaIndex is more focused on indexing and querying documents. Infosys JD mentions LangChain and LangGraph — I know LlamaIndex exists for heavy indexing but VoXgent used LangChain + Pinecone.

**Follow-up:**

1. **When LlamaIndex?**  
   **Say this:** When the project is mostly document ingestion and query with less custom agent flow.

---

### Q27. Design a refund agent with LangGraph.

**Say this:**

> Auth → RAG retrieve refund policy → tool fetch order status → decision node: if eligible and amount small, auto refund tool; else HITL approval node → structured receipt → end. Each step is a node; loops only if data missing.

**Follow-up:**

1. **Where is LangChain?**  
   **Say this:** RAG retriever and LLM calls inside nodes — graph defines the business rules.

---

### Q28. How do you test a graph?

**Say this:**

> Mock LLM and tools, feed initial state, assert next node and final state. Golden paths plus failure paths — tool timeout goes to human node.

**Follow-up:**

1. **Unit vs integration?**  
   **Say this:** Unit test each node function; integration test full graph with mocks; staging test with real Pinecone subset.

---

### Q29. Observability?

**Say this:**

> Log every node: input state summary, output, latency, tokens. Trace ID across Twilio webhook → graph → tools. Needed when Infosys client asks why wrong answer on one call.

**Follow-up:**

1. **Tools?**  
   **Say this:** Structured logs, optional LangSmith or OpenTelemetry — whatever client allows.

---

### Q30. Multi-Agent Chatbot project vs VoXgent?

**Say this:**

> Side project: FastAPI, MySQL, multiple specialized agents, Docker — good for learning architecture. VoXgent: production voice, Pinecone RAG, LangGraph flow, Twilio, GCP scale, enterprise APIs. Interview focus = VoXgent production ownership.

**Follow-up:**

1. **Why not multi-agent on VoXgent?**  
   **Say this:** Latency and reliability — single agent with tools was enough; multi-agent adds orchestration cost without clear benefit for phone calls.

---

## Master compare — say this in 30 seconds

> "LangChain helped me wire RAG and tools fast. But our voice agent had to retry search, call CRM, and transfer to a human — that is not a straight chain. LangGraph let me define nodes and conditional edges with shared state. That is why LangChain for building blocks, LangGraph for production agent flow on VoXgent."

---

**Related:** `02_RAG_Deep_Dive_QA.md` · `03_Structured_Output_LLM_Integration_Grounding.md`
