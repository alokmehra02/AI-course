# Lesson 6: LangGraph & Agents (Siemens Interview Mode)

This document provides a detailed breakdown of **LangGraph** for production agent orchestration. We analyze StateGraph architecture, nodes and edges, conditional routing, checkpointing, ToolNode, human-in-the-loop interrupts, the ReAct pattern, when to use graphs vs chains, a VoXgent voice flow example, testing strategies, and production timeout controls.

---

## 1. Conceptual Breakdown of Concepts

For every fundamental concept below, we address **Why**, **What**, **Where**, **How**, **Production Considerations**, **Interview Explanation**, and **Common Mistakes**.

### A. StateGraph
*   **Why**: Complex agent workflows require shared, mutable state across multiple steps — message history, retrieved documents, tool results, retry counts. Passing variables through nested function calls becomes unmaintainable.
*   **What**: The core LangGraph abstraction — a directed graph where a typed **State** object flows through **Nodes** connected by **Edges**. Each node reads state, performs work, and returns a partial state update.
*   **Where**: Application orchestration layer — between the API gateway and LLM/tool execution.
*   **How**: Define a `TypedDict` or Pydantic model for state. Create `StateGraph(MyState)`, add nodes, add edges, compile to a runnable graph.
*   **Production Considerations**: Keep state schema explicit and versioned. Log state snapshots at each node boundary for debugging production incidents. Avoid storing large binary blobs in state — use references (S3 URIs, DB IDs).
*   **Interview Explanation (30 seconds)**: *"LangGraph's StateGraph models an agent workflow as a state machine. State is a typed dictionary passed between nodes — messages, retrieved docs, intent, tool results. Each node reads state, does work, and returns a partial update. The graph compiler handles merging updates and routing execution. This makes loops, branches, and retries explicit and testable."*
*   **Common Mistakes**: Putting business logic outside nodes (in edge functions) instead of keeping nodes as pure, testable units; or letting state grow unbounded without pruning message history.

### B. Nodes
*   **Why**: Agent workflows decompose into discrete steps — retrieve, classify, call tool, generate response. Each step needs isolated logic, logging, and error handling.
*   **What**: A Python function (sync or async) that accepts the current state and returns a dict of state fields to update. Nodes are the units of work in the graph.
*   **Where**: Registered on the `StateGraph` via `.add_node("name", function)`.
*   **How**:
    ```python
    def retrieve_node(state: AgentState) -> dict:
        docs = retriever.invoke(state["query"])
        return {"retrieved_docs": docs, "retrieval_count": len(docs)}
    ```
*   **Production Considerations**: Each node should be idempotent where possible. Wrap external calls (LLM, DB, APIs) with timeouts and structured error returns — not bare exceptions that crash the graph.
*   **Interview Explanation (30 seconds)**: *"Nodes are pure functions that take state and return partial updates. On VoXgent, nodes included query rewrite, hybrid retrieval, intent classification, tool execution, response generation, and human transfer. Each node logs its inputs and outputs, making production debugging a matter of reading state at the failing node — not tracing nested callbacks."*
*   **Common Mistakes**: Monolithic nodes that do retrieval + generation + tool calling in one function, defeating the purpose of graph-level observability.

### C. Edges & Conditional Routing
*   **Why**: Not every query follows the same path. Some need tools, some need human handoff, some need retrieval retry. Static linear chains cannot express this.
*   **What**:
    *   **Normal Edge**: Unconditional transition `A → B`.
    *   **Conditional Edge**: A routing function evaluates state and returns the name of the next node (e.g., `"tool_call"` vs `"generate"` vs `"human_transfer"`).
*   **Where**: Defined via `.add_edge("A", "B")` or `.add_conditional_edges("A", router_fn, {"tool": "tool_node", "answer": "generate_node"})`.
*   **How**:
    ```python
    def route_after_classify(state: AgentState) -> str:
        intent = state["intent"]
        if intent == "knowledge_query":
            return "retrieve"
        elif intent == "action":
            return "tool_call"
        elif intent == "escalation":
            return "human_transfer"
        return "generate"
    ```
*   **Production Considerations**: Conditional routers must handle unexpected LLM outputs with safe defaults (route to human transfer, not infinite loops). Cap retry edges with a `retry_count` in state.
*   **Interview Explanation (30 seconds)**: *"Conditional edges are routing functions that inspect state and pick the next node. After intent classification, we route to retrieve, tool call, or human transfer. After retrieval, we route to generate if chunks are relevant, or back to query rewrite if not — with a max retry cap. This branching is explicit in the graph definition, not buried in if/else spaghetti."*
*   **Common Mistakes**: Missing a default route in conditional edges, causing the graph to stall; or allowing unlimited retry loops that burn API credits.

### D. Checkpointing (Persistence)
*   **Why**: Long-running agent workflows (multi-turn voice calls, human-in-the-loop approvals) must survive server restarts, and you need to resume conversations from any point.
*   **What**: LangGraph's mechanism to persist graph state to a database (PostgreSQL, SQLite, Redis) after each node execution, keyed by `thread_id`.
*   **Where**: Configured at compile time: `graph.compile(checkpointer=PostgresSaver(conn))`.
*   **How**: Pass `config={"configurable": {"thread_id": "call-abc-123"}}` on every `invoke`/`stream` call. State is automatically saved after each node.
*   **Production Considerations**: Use PostgreSQL for production (not SQLite). Set TTL on old checkpoints. Checkpoint tables grow fast on high-volume voice platforms — archive or prune completed threads.
*   **Interview Explanation (30 seconds)**: *"Checkpointing persists graph state after every node execution, keyed by thread ID. On VoXgent, each voice call had a thread_id. If the server restarted mid-call, we resumed from the last checkpoint instead of losing conversation state. Checkpoints also enable human-in-the-loop — the graph pauses, a human acts, and execution resumes from the saved state."*
*   **Common Mistakes**: Running production graphs without a checkpointer, losing all state on process restart; or using in-memory checkpointers in multi-instance deployments.

### E. ToolNode
*   **Why**: When the LLM returns `tool_calls`, something must execute those tools, format results, and append them to message history — this is repetitive boilerplate.
*   **What**: A pre-built LangGraph node that takes an LLM response with `tool_calls`, executes the matching tools from a registry, and returns `ToolMessage` objects.
*   **Where**: Inserted in the graph after the LLM node when tool calling is enabled.
*   **How**:
    ```python
    from langgraph.prebuilt import ToolNode
    tools = [get_policy_info, update_crm, schedule_callback]
    tool_node = ToolNode(tools)
    graph.add_node("tools", tool_node)
    ```
*   **Production Considerations**: ToolNode executes whatever the LLM requests — enforce an **allowed tools list** per node/intent. Wrap each tool with timeout, input validation (Pydantic), and audit logging. Never expose destructive tools without confirmation.
*   **Interview Explanation (30 seconds)**: *"ToolNode is LangGraph's built-in executor for LLM tool calls. It matches tool_call IDs to registered tools, runs them, and appends ToolMessages to state. In production, we wrap ToolNode tools with Pydantic validation, per-tool timeouts, and an allowlist — the LLM only sees tools permitted for the current intent, not the entire API surface."*
*   **Common Mistakes**: Registering all 50 tools globally so the LLM can call any of them from any state; or executing tools without parameter validation.

### F. Human-in-the-Loop (Interrupt)
*   **Why**: Some actions require human approval before execution — refunds above a threshold, medical advice escalation, CRM writes with financial impact.
*   **What**: LangGraph's `interrupt()` mechanism pauses graph execution before a specified node, surfaces state to a human operator, and resumes after approval or rejection.
*   **Where**: Configured via `interrupt_before=["execute_refund"]` at compile time, or by calling `interrupt()` inside a node.
*   **How**:
    ```python
    graph = builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review"],
    )
    # First invoke pauses before human_review
    result = graph.invoke(state, config)
    # Human approves via admin UI
    graph.invoke(None, config)  # Resumes from checkpoint
    ```
*   **Production Considerations**: Build an admin UI or webhook that reads paused state, displays context, and calls `graph.invoke` with approval/rejection. Set SLA timeouts — auto-reject or auto-escalate if human does not respond within N minutes.
*   **Interview Explanation (30 seconds)**: *"Human-in-the-loop uses LangGraph interrupts to pause before sensitive nodes — like CRM writes or refund processing. The graph checkpoints, surfaces state to an operator dashboard, and resumes on approval. On VoXgent, human transfer was a conditional edge to an interrupt node that connected the caller to a live agent while preserving full conversation state."*
*   **Common Mistakes**: Using interrupts without checkpointing (state is lost on pause); or pausing on every tool call, destroying voice latency.

### G. ReAct Pattern (Reason + Act)
*   **Why**: Agents need to interleave reasoning ("I need the customer's policy number") with actions (calling a lookup tool) before producing a final answer.
*   **What**: **Re**asoning + **Act**ing — the LLM generates a thought, selects a tool, observes the result, and repeats until it can answer.
*   **Where**: Implemented as a loop in the graph: `LLM → (tool_calls?) → ToolNode → LLM → ... → END`.
*   **How**: Conditional edge after LLM node checks `state["messages"][-1].tool_calls` — if present, route to ToolNode; else route to END.
*   **Production Considerations**: **Always cap max iterations** (e.g., 5). Uncapped ReAct loops burn tokens and timeout voice calls. Log each reasoning step for audit.
*   **Interview Explanation (30 seconds)**: *"ReAct is a loop: the LLM reasons, calls a tool, observes the result, and repeats. In LangGraph, this is a conditional edge from the LLM node — if tool_calls exist, go to ToolNode and loop back; otherwise, end. In production, we cap at 3–5 iterations with a timeout. Free-form ReAct without caps is a demo pattern, not a production pattern."*
*   **Common Mistakes**: Unlimited ReAct loops; or using ReAct for simple FAQ retrieval where a single retrieve→generate path is faster and more predictable.

### H. Graph vs Chain — When to Use Which
*   **Why**: LangChain chains (LCEL) are simpler for linear flows. LangGraph adds complexity — justified only when the workflow has branches, loops, or persistent state.
*   **What**:
    *   **Chain (LCEL)**: `retriever | prompt | llm | parser` — fixed one-direction flow.
    *   **Graph (LangGraph)**: Nodes with conditional edges, loops, checkpointing, interrupts.
*   **Where**: Chain for FAQ bots, single-shot RAG, structured extraction. Graph for voice agents, multi-tool workflows, human handoff, retry loops.
*   **How**: Start with a chain. Move to a graph when you need: retrieval retry, tool + RAG branching, human transfer, or stateful multi-turn orchestration.
*   **Production Considerations**: LangGraph uses LangChain runnables inside nodes — they are complementary, not replacements. Do not use LangGraph for a single LLM call.
*   **Interview Explanation (30 seconds)**: *"LangChain chains are A→B→C — great for simple RAG Q&A. LangGraph is for when the path is not a straight line: retrieve, maybe retry, maybe call CRM, maybe transfer to human. On VoXgent, LangChain wired the retriever and prompt templates. LangGraph controlled the call flow — because voice agents need loops, branching, and checkpointed state. Rule of thumb: if you write more than two if/else branches in a chain, move to a graph."*
*   **Common Mistakes**: Using LangGraph for a single retrieve-and-answer pipeline (overkill); or using LangChain AgentExecutor for production voice (opaque, hard to debug, no iteration caps).

---

## 2. The Business Problem

Enterprise voice and chat agents must do more than answer questions from a knowledge base. They must:

1.  **Take Actions**: Update CRM records, schedule callbacks, send SMS confirmations — requiring tool calls with guardrails.
2.  **Handle Failure Gracefully**: Weak retrieval should trigger query rewrite, not hallucination. Tool failures should retry or escalate to humans.
3.  **Maintain State Across Turns**: A 10-minute voice call has dozens of turns. Losing state mid-call destroys user trust.
4.  **Meet Latency SLAs**: Voice platforms target sub-2-second response times. Uncontrolled agent loops blow latency budgets.

**LangChain chains** solve simple RAG. **LangGraph** solves production agent orchestration where the path depends on runtime conditions.

---

## 3. System Architecture

### VoXgent Voice Agent Graph

```
                    VOXGENT VOICE AGENT — LANGGRAPH FLOW

+------------+    Audio/Text     +------------------+    thread_id     +------------------+
|  Twilio /  | --------------> | FastAPI Voice    | --------------> | LangGraph        |
|  User      |                 | Gateway          |                  | Compiled Graph   |
+------------+                 +------------------+                  +------------------+
       ^                              ^                                      |
       | TTS Response                 | SSE Stream                           |
       |                              |                                      v
       |                       +------------------+              +------------------------+
       |                       | Response Cache   |              | 1. QUERY_REWRITE       |
       |                       | (Redis)          |              |    (multi-turn context)|
       |                       +------------------+              +------------------------+
       |                                                                  |
       |                                                                  v
       |                                                         +------------------------+
       |                                                         | 2. CLASSIFY_INTENT     |
       |                                                         |    (knowledge/action/  |
       |                                                         |     escalation)        |
       |                                                         +------------------------+
       |                                                                  |
       |                              +------------------+----------------+------------------+
       |                              |                  |                |                  |
       |                              v                  v                v                  v
       |                    +----------------+  +----------------+ +----------------+ +----------------+
       |                    | 3a. RETRIEVE   |  | 3b. TOOL_CALL  | | 3c. HUMAN      | | 3d. GENERATE   |
       |                    | (Pinecone RAG) |  | (CRM, SMS,     | | TRANSFER       | | (direct reply) |
       |                    +----------------+  |  Scheduling)   | | (interrupt)    | +----------------+
       |                              |         +----------------+ +----------------+          |
       |                              v                  |                |                  |
       |                    +----------------+           |                |                  |
       |                    | 4. GRADE       |           |                |                  |
       |                    | (relevant?)    |           |                |                  |
       |                    +----------------+           |                |                  |
       |                       |         |               |                |                  |
       |                  No   |         | Yes           |                |                  |
       |              (retry<3)|         |               |                |                  |
       |                       v         v               v                v                  v
       |              +----------+  +----------------------------------------+
       |              | REWRITE  |  | 5. GENERATE_RESPONSE                   |
       |              | (loop)   |  |    (grounded answer + citations)       |
       |              +----------+  +----------------------------------------+
       |                                      |
       |                                      v
       +--------------------------------------+
                          6. CHECKPOINT SAVE
                          (PostgreSQL per node)
```

### Data Flow Breakdown (VoXgent Call Example)

1.  **Ingress**: Caller asks *"I want to reschedule my appointment and check my copay."*
2.  **Query Rewrite**: Graph expands to standalone queries using call history: *"Reschedule appointment for patient ID 12345"* and *"What is the copay for dental plan?"*
3.  **Classify Intent**: Intent = `mixed` → route to retrieve (copay question) then tool call (scheduling).
4.  **Retrieve**: Pinecone hybrid search with `tenant_id` filter → top-5 policy chunks.
5.  **Grade**: Chunks are relevant → proceed to generate for copay answer.
6.  **Tool Call**: `schedule_appointment(patient_id, new_time)` → CRM API → success.
7.  **Generate**: LLM synthesizes: *"Your dental copay is $25 [1]. I've rescheduled your appointment to Thursday at 2 PM."*
8.  **Checkpoint**: State saved to PostgreSQL with `thread_id=call-xyz`.
9.  **Egress**: TTS streams response to caller via Twilio.

---

## 4. Implementation Notes (Python)

### Step A: Define State and Build the Graph

```python
from typing import TypedDict, Annotated, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    query: str
    rewritten_query: str
    intent: str
    retrieved_docs: list
    retry_count: int
    tenant_id: str

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [get_policy_info, update_crm, schedule_callback, transfer_to_human]
tool_node = ToolNode(tools)

def query_rewrite_node(state: AgentState) -> dict:
    # Expand multi-turn pronouns into standalone search query
    rewritten = rewrite_with_history(state["query"], state["messages"])
    return {"rewritten_query": rewritten}

def classify_intent_node(state: AgentState) -> dict:
    intent = classify(state["rewritten_query"])  # knowledge | action | escalation
    return {"intent": intent}

def retrieve_node(state: AgentState) -> dict:
    docs = hybrid_retrieve(
        state["rewritten_query"],
        tenant_id=state["tenant_id"],
        top_k=5,
    )
    return {"retrieved_docs": docs}

def grade_retrieval_node(state: AgentState) -> dict:
    # Returns state unchanged; routing happens in conditional edge
    return {}

def route_after_classify(state: AgentState) -> str:
    intent = state["intent"]
    if intent == "escalation":
        return "human_transfer"
    if intent == "action":
        return "agent"  # LLM with tools
    return "retrieve"

def route_after_grade(state: AgentState) -> str:
    if not state["retrieved_docs"]:
        if state["retry_count"] < 2:
            return "rewrite"
        return "refuse"
    return "generate"

def route_after_agent(state: AgentState) -> str:
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"
    return END

# Build graph
builder = StateGraph(AgentState)
builder.add_node("rewrite", query_rewrite_node)
builder.add_node("classify", classify_intent_node)
builder.add_node("retrieve", retrieve_node)
builder.add_node("grade", grade_retrieval_node)
builder.add_node("agent", llm.bind_tools(tools))
builder.add_node("tools", tool_node)
builder.add_node("generate", generate_grounded_response)
builder.add_node("refuse", refuse_response)
builder.add_node("human_transfer", human_handoff)

builder.add_edge(START, "rewrite")
builder.add_edge("rewrite", "classify")
builder.add_conditional_edges("classify", route_after_classify, {
    "retrieve": "retrieve",
    "agent": "agent",
    "human_transfer": "human_transfer",
})
builder.add_edge("retrieve", "grade")
builder.add_conditional_edges("grade", route_after_grade, {
    "rewrite": "rewrite",
    "generate": "generate",
    "refuse": "refuse",
})
builder.add_conditional_edges("agent", route_after_agent, {
    "tools": "tools",
    "END": END,
})
builder.add_edge("tools", "agent")  # ReAct loop back to LLM
builder.add_edge("generate", END)
builder.add_edge("refuse", END)
builder.add_edge("human_transfer", END)

graph = builder.compile(
    checkpointer=postgres_checkpointer,
    interrupt_before=["human_transfer"],
)
```

### Step B: Invoke with Thread ID and Timeout

```python
import asyncio

GRAPH_TIMEOUT_SECONDS = 8.0  # Voice SLA
MAX_REACT_ITERATIONS = 5

async def handle_voice_turn(call_id: str, tenant_id: str, user_text: str):
    config = {"configurable": {"thread_id": call_id}}

    try:
        result = await asyncio.wait_for(
            graph.ainvoke(
                {
                    "messages": [{"role": "user", "content": user_text}],
                    "query": user_text,
                    "tenant_id": tenant_id,
                    "retry_count": 0,
                },
                config=config,
            ),
            timeout=GRAPH_TIMEOUT_SECONDS,
        )
        return result["messages"][-1].content

    except asyncio.TimeoutError:
        return "I'm having trouble processing that. Let me connect you with a specialist."
```

### Step C: Testing Individual Nodes

```python
import pytest

@pytest.mark.asyncio
async def test_retrieve_node_returns_tenant_scoped_docs():
    state = {
        "rewritten_query": "dental copay amount",
        "tenant_id": "client_a",
        "messages": [],
        "retry_count": 0,
    }
    result = await retrieve_node(state)
    assert len(result["retrieved_docs"]) > 0
    assert all(d["metadata"]["tenant_id"] == "client_a" for d in result["retrieved_docs"])

def test_route_after_grade_retries_on_empty():
    state = {"retrieved_docs": [], "retry_count": 0}
    assert route_after_grade(state) == "rewrite"

def test_route_after_grade_refuses_at_max_retries():
    state = {"retrieved_docs": [], "retry_count": 2}
    assert route_after_grade(state) == "refuse"
```

---

## 5. Why LangChain AgentExecutor Fails at Scale

1.  **Opaque Control Flow**: AgentExecutor hides the loop. You cannot see which step failed in production logs.
2.  **No Iteration Caps**: Default executor can loop indefinitely, burning tokens and violating voice SLAs.
3.  **No Checkpointing**: Server restart mid-call loses all conversation state.
4.  **No Conditional Branching**: Human transfer, retrieval retry, and refuse-on-empty require custom hacks.
5.  **Hard to Test**: Cannot unit-test individual steps — only end-to-end agent runs.

---

## 6. The LangChain Abstraction (Inside Graph Nodes)

LangChain components live **inside** LangGraph nodes:

*   **`ChatOpenAI`**: LLM invocation within `agent` and `generate` nodes.
*   **`@tool` decorators**: Auto-generate tool schemas for ToolNode.
*   **Retrievers**: Pinecone retriever called inside `retrieve_node`.
*   **Prompt templates**: Used in `generate_node` for grounded response formatting.

```python
from langchain_core.prompts import ChatPromptTemplate

generate_prompt = ChatPromptTemplate.from_messages([
    ("system", "Answer from context only. Cite sources.\n\nContext:\n{context}"),
    ("placeholder", "{messages}"),
])

def generate_grounded_response(state: AgentState) -> dict:
    context = format_docs(state["retrieved_docs"])
    chain = generate_prompt | llm
    response = chain.invoke({"context": context, "messages": state["messages"]})
    return {"messages": [response]}
```

LangChain = building blocks. LangGraph = how they connect in production.

---

## 7. Testing Strategies

| Level | What to Test | How |
| :--- | :--- | :--- |
| **Unit** | Individual nodes | Pass mock state, assert state updates |
| **Router** | Conditional edges | Test all branches with edge-case state |
| **Integration** | Full graph path | Mock LLM/tools, invoke graph, assert final state |
| **E2E** | Real LLM + tools | Golden test cases with expected node traversal |
| **Load** | Timeout behavior | Simulate slow tools, assert fallback within SLA |

**Key practices:**
*   Mock external APIs (CRM, Pinecone) in unit/integration tests.
*   Use `graph.get_state(config)` to inspect intermediate state after partial runs.
*   Record production graph traversals (node sequence + timing) to ClickHouse for regression analysis.

---

## 8. Production Considerations (Enterprise Architecture)

1.  **Graph-Level Timeout**: Wrap `graph.ainvoke` in `asyncio.wait_for(timeout=8s)`. On timeout, route to human transfer — never hang a voice caller.
2.  **Per-Node Timeouts**: Each external call (LLM, Pinecone, CRM) gets its own timeout (e.g., LLM 3s, retrieval 1s, tool 2s).
3.  **Max ReAct Iterations**: Cap tool-call loops at 3–5. Track `iteration_count` in state.
4.  **Checkpoint Pruning**: Archive completed call checkpoints after 30 days. Monitor PostgreSQL table growth.
5.  **Structured Logging**: Log `{thread_id, node_name, duration_ms, state_keys}` after every node execution to ClickHouse.
6.  **Graceful Degradation**: If retrieval fails, skip to direct LLM with a refuse rule. If tools fail, inform user and offer human transfer.
7.  **Idempotent Tools**: CRM and scheduling tools should be safe to retry — use idempotency keys.

---

## 9. Interview Section

### Q1. LangChain vs LangGraph — when do you use each?

**Say this:**

> LangChain chains are A→B→C — great for simple RAG: retrieve, prompt, generate. LangGraph is for when the path branches: retrieve, maybe retry, maybe call a tool, maybe transfer to human. On VoXgent, LangChain wired the Pinecone retriever and prompt templates. LangGraph controlled the full call flow because voice agents need loops, conditional routing, and checkpointed state across a 10-minute call.

### Q2. What is LangGraph state and why does it matter?

**Say this:**

> State is a typed dictionary shared across all nodes — messages, retrieved docs, intent, retry count, tenant ID. Each node reads state and returns a partial update. The graph merges updates automatically. In production, I log state at every node boundary. When a call fails, I read the checkpoint and see exactly which node produced bad output — not trace nested callbacks.

### Q3. How do you prevent agent infinite loops?

**Say this:**

> Three controls: max ReAct iterations capped at 3–5 in state, conditional edges that route to refuse or human transfer when retry_count exceeds threshold, and a graph-level asyncio timeout of 8 seconds for voice. Uncapped AgentExecutor loops are a demo anti-pattern.

### Q4. Explain human-in-the-loop in LangGraph.

**Say this:**

> `interrupt_before` pauses the graph before a sensitive node — like CRM writes or refunds. The graph checkpoints state to PostgreSQL. An operator reviews context in an admin UI and approves or rejects. On approval, `graph.invoke(None, config)` resumes from the checkpoint. On VoXgent, human transfer was a conditional edge to an interrupt that connected the caller to a live agent while preserving conversation history.

### Q5. How do you test a LangGraph agent?

**Say this:**

> Unit-test each node in isolation with mock state. Test conditional routers with edge-case state — empty retrieval, max retries, unexpected intent. Integration tests mock the LLM and external APIs, invoke the full graph, and assert the node traversal path. Production node timing and traversal sequences are logged to ClickHouse for regression analysis.

### Q6. Walk me through the VoXgent voice agent graph.

**Say this:**

> Each call gets a thread_id. The graph starts with query rewrite for multi-turn context, then classifies intent — knowledge, action, or escalation. Knowledge queries go through Pinecone retrieval with tenant filter, grade relevance, and generate a grounded answer. Action intents route to the LLM with tools — CRM, scheduling, SMS. Escalation triggers human transfer via interrupt. Every node checkpoints to PostgreSQL. The whole graph runs under an 8-second timeout for voice SLA.

### 30-Second Elevator Pitch

*"LangGraph models production agents as explicit state machines — nodes for retrieve, classify, tool call, and generate, with conditional edges for branching and retry loops. Checkpointing survives restarts and enables human-in-the-loop. On VoXgent, it replaced opaque AgentExecutor loops with a testable, timeout-bounded graph that handled RAG, CRM tools, and human transfer in a single voice call flow."*

---
