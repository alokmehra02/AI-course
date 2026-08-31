# Lesson 7: MCP & Tool Calling (Siemens Interview Mode)

This document provides a detailed breakdown of the **Model Context Protocol (MCP)** and how it relates to LLM function calling, LangChain tools, and production agent architectures. We analyze the client-server model, tools/resources/prompts primitives, transports, security boundaries, building MCP servers for internal APIs, agent loops, and production deployment patterns.

---

## 1. Conceptual Breakdown of Concepts

For every fundamental concept below, we address **Why**, **What**, **Where**, **How**, **Production Considerations**, **Interview Explanation**, and **Common Mistakes**.

### A. What is MCP (Model Context Protocol)?
*   **Why**: Every LLM application needs to connect to external systems — CRMs, databases, file stores, internal APIs. Without a standard, each integration requires a custom adapter per tool per client (Cursor, Claude Desktop, custom agents).
*   **What**: An open protocol (JSON-RPC 2.0) that standardizes how AI applications (**clients**) discover and invoke capabilities exposed by external services (**servers**). MCP is to tool integration what USB-C is to hardware — one port, many devices.
*   **Where**: Sits between the agent runtime (Cursor, LangGraph, custom FastAPI) and backend services (internal APIs, databases, file systems).
*   **How**: The client connects to an MCP server, calls `tools/list` to discover available tools, and invokes them via `tools/call` with structured arguments.
*   **Production Considerations**: MCP is a **wire protocol**, not a security boundary. Authorization, rate limiting, and input validation remain the server's responsibility. Treat MCP servers like microservices with their own auth.
*   **Interview Explanation (30 seconds)**: *"MCP — Model Context Protocol — is an open JSON-RPC standard for connecting AI clients to external tools and data. Instead of writing a custom integration for every LLM client, you expose an MCP server once and any MCP-capable client can discover and call your tools. It's a protocol layer, not a framework — security and business logic live in the server."*
*   **Common Mistakes**: Treating MCP as a replacement for API authentication; or assuming MCP servers are inherently safe because they use a standard protocol.

### B. Client-Server Architecture
*   **Why**: Decoupling tool providers from agent logic allows independent deployment, versioning, and access control per service.
*   **What**:
    *   **MCP Client**: The AI application (Cursor IDE, LangGraph agent, Claude Desktop) that needs external capabilities.
    *   **MCP Server**: A process that exposes tools, resources, and prompts over the MCP protocol.
    *   **Transport**: The communication channel between client and server (stdio, SSE, streamable HTTP).
*   **Where**: Client runs in the agent runtime. Server runs as a separate process or remote service.
*   **How**: Client spawns server process (stdio) or connects to remote endpoint (HTTP/SSE). Handshake via `initialize` → `tools/list` → `tools/call`.
*   **Production Considerations**: Prefer HTTP/SSE transport for remote servers in production. stdio is fine for local dev (Cursor plugins). Run MCP servers behind API gateways with TLS and auth tokens.
*   **Interview Explanation (30 seconds)**: *"MCP follows a client-server model. The client — your agent or IDE — connects to one or more MCP servers. Each server exposes a catalog of tools. The client discovers tools at connect time via tools/list, then invokes them via tools/call with JSON arguments. One agent can connect to multiple servers — CRM server, database server, file server — each independently deployed."*
*   **Common Mistakes**: Running MCP servers without network isolation in production; or coupling server lifecycle to the client process in multi-tenant deployments.

### C. Tools, Resources, and Prompts
*   **Why**: LLM applications need three categories of external capability — actions (tools), data (resources), and reusable instructions (prompts).
*   **What**:
    *   **Tools**: Callable functions with JSON Schema input/output — e.g., `create_ticket`, `query_inventory`, `send_sms`.
    *   **Resources**: Readable data URIs — e.g., `file:///docs/policy.pdf`, `db://customers/schema` — fetched by the client and injected into context.
    *   **Prompts**: Pre-built prompt templates exposed by the server — e.g., `analyze-log` with parameters for log file and time range.
*   **Where**: Registered on the MCP server and discovered by the client at connection time.
*   **How**: Server implements handlers for `tools/list`, `tools/call`, `resources/list`, `resources/read`, `prompts/list`, `prompts/get`.
*   **Production Considerations**: Tools are the highest-risk primitive — they execute side effects. Resources are read-only but may expose sensitive data. Apply RBAC per tool, not per server.
*   **Interview Explanation (30 seconds)**: *"MCP exposes three primitives. Tools are callable actions with JSON schemas — like function calling but standardized. Resources are readable data URIs the client can fetch for context injection. Prompts are reusable templates with parameters. In practice, tools get 90% of production attention because they execute side effects and need strict auth."*
*   **Common Mistakes**: Exposing write tools without per-tool authorization; or using resources to serve large files without size limits, blowing up the agent's context window.

### D. Transports (stdio, SSE, Streamable HTTP)
*   **Why**: Different deployment contexts require different communication channels — local IDE plugins vs remote cloud services.
*   **What**:
    *   **stdio**: Client spawns server as child process, communicates via stdin/stdout. Used by Cursor, Claude Desktop.
    *   **SSE (Server-Sent Events)**: HTTP-based, server pushes events to client. Good for remote servers.
    *   **Streamable HTTP**: Bidirectional HTTP transport (newer spec). Better for production remote deployments.
*   **Where**: Configured in the MCP client connection settings.
*   **How**: stdio: `"command": "python", "args": ["server.py"]`. SSE: `"url": "https://mcp.internal.company.com/sse"`.
*   **Production Considerations**: stdio is dev-only for local tools. Production uses HTTP/SSE behind TLS with API key or OAuth authentication. Set connection timeouts and health checks on remote servers.
*   **Interview Explanation (30 seconds)**: *"MCP supports multiple transports. stdio spawns the server as a child process — how Cursor runs local MCP plugins. For production, use SSE or streamable HTTP to connect to remote MCP servers behind your API gateway with TLS and auth tokens. stdio doesn't scale to multi-tenant cloud deployments."*
*   **Common Mistakes**: Deploying stdio-based servers in containerized production (process management nightmare); or not setting HTTP timeouts on remote MCP connections.

### E. MCP vs Function Calling (OpenAI Tools API)
*   **Why**: Both solve "LLM invokes external capabilities" but at different layers of the stack.
*   **What**:
    *   **Function Calling**: Provider-specific API feature. You pass tool JSON schemas in the LLM request payload. The model returns `tool_calls` in its response. Your app executes them.
    *   **MCP**: Protocol-level standard. Tools are discovered from MCP servers at runtime. Any MCP client can use any MCP server.
*   **Where**: Function calling operates at the LLM API boundary. MCP operates at the tool integration boundary — between the agent and backend services.
*   **How**: They compose: MCP client discovers tools → converts to function calling schemas → passes to LLM → LLM returns tool_calls → MCP client routes back to the correct MCP server.
*   **Production Considerations**: Function calling is how the LLM *decides* to call a tool. MCP is how your system *provides and executes* tools. You typically use both together.
*   **Interview Explanation (30 seconds)**: *"Function calling is the LLM API feature — the model outputs structured tool_calls with arguments. MCP is the integration protocol — how tools are discovered, described, and executed across clients. They compose: the MCP client discovers tools from servers, converts them to function calling schemas for the LLM, and routes execution back to the correct MCP server. Function calling is the decision layer; MCP is the plumbing layer."*
*   **Common Mistakes**: Thinking MCP replaces function calling (they solve different problems); or implementing function calling without a tool registry, leading to duplicated schemas across agents.

### F. MCP vs LangChain Tools
*   **Why**: LangChain `@tool` decorators solve tool definition within a Python process. MCP solves tool exposure across process and language boundaries.
*   **What**:
    *   **LangChain Tools**: Python functions decorated with `@tool`, registered in-process, auto-generate JSON schemas, executed by `ToolNode` or agent executor.
    *   **MCP Tools**: JSON-RPC endpoints on a separate server, language-agnostic, discovered at runtime.
*   **Where**: LangChain tools live inside your Python agent. MCP tools live on external server processes.
*   **How**: LangChain: `@tool def get_weather(city: str) -> str`. MCP: server exposes `get_weather` via `tools/list` and handles `tools/call`.
*   **Production Considerations**: Use LangChain tools for in-process logic (formatting, validation). Use MCP for cross-service integrations (CRM, EMR, internal APIs owned by other teams). LangGraph can consume both — LangChain tools in ToolNode, MCP tools via an MCP client adapter.
*   **Interview Explanation (30 seconds)**: *"LangChain tools are in-process Python functions — fast, simple, great for formatting and validation logic. MCP tools are out-of-process, language-agnostic, and discoverable at runtime — great when the CRM API is owned by another team or written in Go. In production, I use LangChain tools for agent-internal logic and MCP for cross-service boundaries. LangGraph's ToolNode handles LangChain tools; an MCP client adapter bridges MCP tools into the same agent loop."*
*   **Common Mistakes**: Wrapping every internal function as an MCP server (unnecessary network overhead); or using only LangChain tools when integrations span multiple services and teams.

### G. Security
*   **Why**: MCP tools execute real side effects — database writes, API calls, file access. A compromised or misconfigured server is a production incident.
*   **What**: Defense-in-depth for MCP deployments:
    1.  **Authentication**: API keys or OAuth on every MCP server connection.
    2.  **Authorization**: Per-tool RBAC — not every agent sees every tool.
    3.  **Input Validation**: Pydantic schemas on the server, not just JSON Schema descriptions.
    4.  **Network Isolation**: MCP servers in private VPC, not public internet.
    5.  **Audit Logging**: Log every `tools/call` with caller identity, arguments, and result.
    6.  **Allowlisting**: Agent config specifies which MCP servers and tools are permitted.
*   **Where**: Enforced on the MCP server, at the API gateway, and in the agent's tool allowlist.
*   **How**: MCP server validates auth token on `initialize`. Each `tools/call` checks caller permissions against tool-level ACLs. Agent config: `allowed_tools: ["crm.create_ticket", "crm.get_contact"]`.
*   **Production Considerations**: Never trust client-supplied identity metadata. The MCP server must validate the caller's credentials independently. Third-party MCP servers (community plugins) should run in sandboxed environments.
*   **Interview Explanation (30 seconds)**: *"MCP is a protocol, not a security boundary. Every MCP server needs its own auth — API keys or OAuth. Tools get per-tool RBAC, Pydantic input validation, and audit logging. Agents allowlist which servers and tools they can access. Third-party MCP servers run sandboxed. The server validates the caller's identity — never trust client-supplied metadata."*
*   **Common Mistakes**: Running MCP servers without authentication because "it's internal"; or giving agents access to all tools on all connected servers.

### H. Building an MCP Server for an Internal API
*   **Why**: Your company has internal REST APIs (CRM, inventory, scheduling). Exposing them as MCP tools lets any MCP-capable agent (Cursor, custom LangGraph, Claude Desktop) use them without custom integration code per client.
*   **What**: A lightweight server process that wraps internal API endpoints as MCP tools with JSON Schema descriptions.
*   **Where**: Deployed as a sidecar or microservice, accessible via HTTP/SSE transport.
*   **How**: Use the MCP SDK (Python `mcp` package or TypeScript `@modelcontextprotocol/sdk`):
    ```python
    from mcp.server import Server
    from mcp.server.stdio import stdio_server

    server = Server("crm-mcp")

    @server.tool()
    async def get_contact(contact_id: str) -> str:
        """Retrieve a CRM contact by ID."""
        response = await crm_client.get(f"/contacts/{contact_id}")
        return response.json()

    @server.tool()
    async def create_ticket(subject: str, priority: str, contact_id: str) -> str:
        """Create a support ticket in the CRM."""
        response = await crm_client.post("/tickets", json={
            "subject": subject, "priority": priority, "contact_id": contact_id,
        })
        return f"Ticket {response.json()['id']} created."
    ```
*   **Production Considerations**: Add auth middleware, rate limiting, and request logging. Map internal API errors to MCP error responses. Version the server alongside the internal API.
*   **Interview Explanation (30 seconds)**: *"To expose an internal API as MCP, I write a thin server using the MCP SDK that wraps REST endpoints as tools with docstrings for descriptions and type hints for schemas. The server handles auth, validates inputs with Pydantic, and maps API errors to MCP error responses. Deploy behind the API gateway with TLS. Any MCP client — Cursor, LangGraph, Claude Desktop — discovers and calls these tools without custom integration."*
*   **Common Mistakes**: Passing raw internal API responses to the LLM without sanitization (may contain PII or internal error stack traces); or not versioning the MCP server when the underlying API changes.

### I. Agent Loop with Tools (MCP + Function Calling)
*   **Why**: The LLM must autonomously decide when to call tools, execute them, observe results, and iterate until it can answer.
*   **What**: The standard agent loop: LLM → tool_calls? → execute tools → append results → LLM → ... → final answer.
*   **Where**: Orchestrated by LangGraph, a manual Python loop, or an MCP-aware agent runtime.
*   **How**:
    1.  MCP client connects to servers, calls `tools/list`.
    2.  Convert MCP tool schemas to OpenAI function calling format.
    3.  Pass tools to LLM in the chat completion request.
    4.  LLM returns `tool_calls` with function name and arguments.
    5.  Agent routes execution to the correct MCP server via `tools/call`.
    6.  Append `ToolMessage` with result to conversation.
    7.  Repeat until LLM returns text (no more tool_calls).
*   **Production Considerations**: Cap iterations at 3–5. Set per-tool timeouts. Log every tool invocation. Validate arguments server-side before execution.
*   **Interview Explanation (30 seconds)**: *"The agent loop composes MCP and function calling. The MCP client discovers tools from connected servers and converts them to function calling schemas for the LLM. The model decides which tool to call. The agent routes execution back to the correct MCP server, appends the result, and loops. In LangGraph, this is the ReAct pattern — LLM node, conditional edge to ToolNode, loop back. Capped at 5 iterations with per-tool timeouts."*
*   **Common Mistakes**: Uncapped loops; or executing tool calls without routing to the correct MCP server when multiple servers expose similarly named tools.

### J. Production Patterns
*   **Why**: MCP in production requires operational patterns beyond the protocol spec.
*   **What**: Proven deployment patterns:
    1.  **Tool Gateway**: Single MCP gateway that proxies to multiple backend MCP servers with unified auth.
    2.  **Tool Allowlist per Agent**: Agent config specifies permitted tools — not all tools from all servers.
    3.  **Circuit Breaker**: If an MCP server is down, skip its tools and degrade gracefully.
    4.  **Schema Versioning**: Tool schemas versioned alongside API changes; clients re-discover on reconnect.
    5.  **Observability**: Trace every `tools/call` with OpenTelemetry — latency, error rate, caller identity.
*   **Where**: Infrastructure layer around MCP servers and agent runtime.
*   **How**: Deploy MCP servers as Kubernetes services. Agent connects via HTTP/SSE through API gateway. ClickHouse logs all tool invocations.
*   **Production Considerations**: Start with 2–3 high-value MCP servers (CRM, scheduling, knowledge base). Do not MCP-wrap every internal endpoint on day one.
*   **Interview Explanation (30 seconds)**: *"Production MCP means a tool gateway with unified auth, per-agent tool allowlists, circuit breakers on failing servers, and OpenTelemetry tracing on every tools/call. Start with high-value servers — CRM, scheduling — not every internal endpoint. Log invocations to ClickHouse for audit and debugging. Version tool schemas alongside API changes."*
*   **Common Mistakes**: Connecting agents to all available MCP servers without allowlisting; or skipping observability because "MCP is just dev tooling."

---

## 2. The Business Problem

Enterprise AI agents must interact with dozens of internal systems — CRM, ERP, scheduling, EMR, inventory. Before MCP:

1.  **Integration Sprawl**: Every agent (Cursor, custom bot, Claude Desktop) needed a custom adapter for every backend API. 5 agents × 10 APIs = 50 integration points.
2.  **No Discovery**: Tools were hardcoded in agent config. Adding a new API required redeploying every agent.
3.  **Security Gaps**: Ad-hoc tool integrations lacked consistent auth, audit logging, and input validation.
4.  **Team Boundaries**: The CRM team owned the CRM API but had no standard way to expose it to AI agents without writing custom code for each consumer.

**MCP** standardizes tool exposure so each backend team ships one MCP server, and every agent client discovers and uses it through a uniform protocol.

---

## 3. System Architecture

```
                    MCP PRODUCTION ARCHITECTURE

+------------+         +------------------+         +------------------+
| Cursor IDE |         |                  |         | CRM MCP Server   |
| (MCP Client)| -----> |   MCP Gateway    | ------> | tools:           |
+------------+         |   (Auth + Route) |         |  - get_contact   |
                       |                  |         |  - create_ticket |
+------------+         |  - TLS           |         +------------------+
| LangGraph  | ------> |  - API Key Auth  |                |
| Agent      |         |  - Tool Allowlist|                | REST
| (MCP Client)|        |  - Rate Limit    |                v
+------------+         |  - Audit Log     |         +------------------+
                       |                  | ------> | Scheduling MCP   |
+------------+         |                  |         | Server           |
| Claude     | ------> |                  |         | tools:           |
| Desktop    |         +------------------+         |  - book_appt     |
+------------+                |                     |  - cancel_appt   |
                              |                            |
                              v                            v
                       +------------------+         +------------------+
                       | ClickHouse       |         | Internal APIs    |
                       | Audit Logs       |         | (CRM, Calendar,  |
                       | (tools/call log) |         |  EMR, Inventory) |
                       +------------------+         +------------------+


              AGENT LOOP (MCP + Function Calling)

+------------+    1. tools/list     +------------------+
| LangGraph  | -------------------> | MCP Gateway      |
| Agent      | <------------------- | (discovers tools)|
+------------+    tool schemas      +------------------+
      |                                      ^
      | 2. Pass tools to LLM                 |
      v                                      |
+------------+    3. tool_calls     +------------------+
| LLM Gateway| -------------------> | Agent Router     |
| (GPT-4o)   |                     | (match call to   |
+------------+                     |  MCP server)     |
      ^                            +------------------+
      | 6. ToolMessage result              |
      |                                      | 4. tools/call
      |                                      v
      |                             +------------------+
      +-----------------------------| MCP Server       |
         5. Append result            | (execute + auth) |
                                    +------------------+
```

### Data Flow Breakdown

1.  **Discovery**: Agent connects to MCP Gateway → `tools/list` returns all available tools from connected servers with JSON schemas.
2.  **Schema Conversion**: Agent converts MCP tool definitions to OpenAI function calling format.
3.  **LLM Decision**: User asks *"Create a ticket for customer John about billing issue."* → LLM returns `tool_calls: [{name: "create_ticket", args: {...}}]`.
4.  **Routing**: Agent matches `create_ticket` to the CRM MCP Server.
5.  **Execution**: Agent calls `tools/call` on CRM server → server validates auth, inputs, calls internal CRM API.
6.  **Result Loop**: Tool result appended as `ToolMessage` → LLM generates: *"I've created ticket #4521 for John regarding the billing issue."*
7.  **Audit**: Full invocation logged to ClickHouse with caller, tool, args, result, latency.

---

## 4. Implementation Notes (Python)

### Step A: MCP Server for Internal CRM API

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
from pydantic import BaseModel, Field
import httpx

server = Server("crm-mcp")
crm = httpx.AsyncClient(base_url="https://crm.internal/api", headers={"Authorization": "Bearer ..."})

class CreateTicketInput(BaseModel):
    subject: str = Field(description="Ticket subject line")
    priority: str = Field(description="low | medium | high | critical")
    contact_id: str = Field(description="CRM contact ID")

@server.tool()
async def get_contact(contact_id: str) -> str:
    """Retrieve a CRM contact by ID. Returns name, email, and account status."""
    resp = await crm.get(f"/contacts/{contact_id}")
    resp.raise_for_status()
    data = resp.json()
    return f"Contact: {data['name']}, Email: {data['email']}, Status: {data['status']}"

@server.tool()
async def create_ticket(subject: str, priority: str, contact_id: str) -> str:
    """Create a support ticket in the CRM system."""
    validated = CreateTicketInput(subject=subject, priority=priority, contact_id=contact_id)
    resp = await crm.post("/tickets", json=validated.model_dump())
    resp.raise_for_status()
    ticket_id = resp.json()["id"]
    return f"Ticket #{ticket_id} created with priority {validated.priority}."

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### Step B: Agent Loop with MCP Tool Discovery

```python
from openai import AsyncOpenAI

client = AsyncOpenAI()
MAX_ITERATIONS = 5

async def discover_mcp_tools(mcp_client) -> list[dict]:
    """Fetch tools from MCP servers and convert to OpenAI function calling format."""
    mcp_tools = await mcp_client.list_tools()
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            },
        }
        for tool in mcp_tools
    ]

async def execute_mcp_tool(mcp_client, tool_name: str, arguments: dict) -> str:
    """Route tool execution to the correct MCP server."""
    result = await mcp_client.call_tool(tool_name, arguments)
    return result.content[0].text

async def agent_loop(user_query: str, mcp_client, allowed_tools: list[str]):
    tools = await discover_mcp_tools(mcp_client)
    tools = [t for t in tools if t["function"]["name"] in allowed_tools]

    messages = [
        {"role": "system", "content": "You are a support agent. Use tools when needed."},
        {"role": "user", "content": user_query},
    ]

    for iteration in range(MAX_ITERATIONS):
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            temperature=0.0,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            return msg.content

        messages.append(msg)
        for tool_call in msg.tool_calls:
            result = await execute_mcp_tool(
                mcp_client,
                tool_call.function.name,
                json.loads(tool_call.function.arguments),
            )
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

    return "I wasn't able to complete this request. Please try again or contact support."
```

### Step C: MCP Client Configuration (Cursor / Agent)

```json
{
  "mcpServers": {
    "crm": {
      "command": "python",
      "args": ["crm_mcp_server.py"],
      "env": {
        "CRM_API_KEY": "${CRM_API_KEY}"
      }
    },
    "scheduling": {
      "url": "https://mcp.internal.company.com/scheduling/sse",
      "headers": {
        "Authorization": "Bearer ${MCP_GATEWAY_TOKEN}"
      }
    }
  }
}
```

---

## 5. Why Ad-Hoc Tool Integration Fails at Scale

1.  **Schema Duplication**: Every agent redefines the same CRM tool schemas with slight inconsistencies.
2.  **No Discovery**: Adding a new API requires updating every agent's config and redeploying.
3.  **Inconsistent Security**: Some integrations validate inputs; others pass raw LLM output to APIs.
4.  **No Audit Trail**: Tool invocations are scattered across logs with no unified format.
5.  **Cross-Language Barriers**: Python agents cannot easily call Go or Java internal services without HTTP wrappers.

---

## 6. MCP vs LangChain Tools — When to Use Which

| Scenario | LangChain `@tool` | MCP Server |
| :--- | :--- | :--- |
| In-process formatting/validation | ✅ Best fit | Overkill |
| Cross-team API owned by another service | Awkward (HTTP wrapper) | ✅ Best fit |
| Cursor IDE integration | N/A | ✅ Required |
| LangGraph ToolNode | ✅ Native support | Via MCP client adapter |
| Multi-language backend | Python only | ✅ Language-agnostic |
| Runtime tool discovery | Hardcoded at startup | ✅ `tools/list` at connect |

**Rule of thumb**: LangChain tools for agent-internal logic. MCP for cross-service boundaries and IDE integrations.

---

## 7. The LangGraph Integration

LangGraph consumes MCP tools via an adapter that bridges MCP discovery into ToolNode:

```python
from langgraph.prebuilt import ToolNode

# LangChain tools (in-process)
@tool
def format_response(text: str) -> str:
    """Format the final response for voice output."""
    return text[:500]

# MCP tools (out-of-process) — discovered at startup
mcp_tools = await mcp_client.to_langchain_tools()
all_tools = [format_response] + mcp_tools

tool_node = ToolNode(all_tools)
```

The graph structure is identical whether tools are LangChain or MCP — the difference is where execution happens (in-process vs remote server).

---

## 8. Production Considerations (Enterprise Architecture)

1.  **Tool Gateway**: Deploy a single authenticated gateway that proxies to backend MCP servers. Agents connect to the gateway, not individual servers.
2.  **Per-Agent Allowlist**: Agent config specifies `allowed_tools: ["crm.get_contact", "scheduling.book_appt"]` — never expose all tools to all agents.
3.  **Auth on Every Call**: MCP server validates caller credentials on `initialize` and every `tools/call`. Never trust client-supplied identity.
4.  **Input Validation**: Pydantic validation on the server, not just JSON Schema descriptions. Reject malformed arguments before they reach internal APIs.
5.  **Audit Logging**: Log every `tools/call` to ClickHouse: `{caller, tool_name, arguments, result, latency_ms, timestamp}`.
6.  **Circuit Breaker**: If an MCP server fails health checks, remove its tools from discovery until recovery.
7.  **Sandboxed Third-Party Servers**: Community MCP plugins run in isolated containers with restricted network access.
8.  **Iteration Caps**: Agent loops capped at 3–5 tool calls with per-tool timeouts (2s) and graph-level timeout (8s for voice).

---

## 9. Interview Section

### Q1. What is MCP and why would you use it?

**Say this:**

> MCP — Model Context Protocol — is an open JSON-RPC standard for connecting AI clients to external tools and data. Instead of writing a custom CRM integration for every agent, the CRM team exposes one MCP server and any MCP-capable client — Cursor, LangGraph, Claude Desktop — discovers and calls those tools. It's the plumbing layer between agents and backend services.

### Q2. MCP vs function calling — what's the difference?

**Say this:**

> Function calling is the LLM API feature — the model outputs structured tool_calls. MCP is the integration protocol — how tools are discovered, described, and executed. They compose: the MCP client discovers tools, converts them to function calling schemas, the LLM decides which to call, and the agent routes execution back to the correct MCP server. Function calling is the decision layer; MCP is the plumbing.

### Q3. MCP vs LangChain tools?

**Say this:**

> LangChain tools are in-process Python functions — fast, simple, great for formatting and validation inside the agent. MCP tools are out-of-process, language-agnostic, discoverable at runtime — great for cross-team APIs. On VoXgent, LangChain tools handled in-agent logic. MCP would be the right choice for exposing our CRM or EMR APIs to multiple agent consumers without rewriting integrations.

### Q4. How do you secure MCP in production?

**Say this:**

> MCP is a protocol, not a security boundary. Every server gets API key or OAuth auth. Tools have per-tool RBAC. Inputs are validated with Pydantic on the server. Agents allowlist which tools they can access. Third-party MCP servers run sandboxed. Every tools/call is audit-logged to ClickHouse with caller identity, arguments, and latency.

### Q5. Walk me through the agent loop with MCP tools.

**Say this:**

> Agent connects to MCP servers and calls tools/list to discover available tools. Schemas are converted to function calling format and passed to the LLM. The model returns tool_calls with arguments. The agent routes execution to the correct MCP server via tools/call. Results are appended as ToolMessages and the loop continues until the model returns a final answer. Capped at 5 iterations with per-tool timeouts. In LangGraph, this is the ReAct pattern — LLM node, conditional edge to ToolNode, loop back.

### Q6. When would you NOT use MCP?

**Say this:**

> For a single LLM call with no tools. For in-process logic that doesn't cross service boundaries — use LangChain @tool instead. When you have three internal tools and one client, a direct function calling implementation is simpler than standing up MCP servers. MCP pays off when multiple agents consume the same tools or when backend APIs are owned by different teams.

### 30-Second Elevator Pitch

*"MCP standardizes how AI agents discover and invoke external tools via JSON-RPC. Function calling is how the LLM decides to call a tool; MCP is how tools are exposed and executed across clients and services. In production: auth on every server, per-tool RBAC, agent allowlists, audit logging, and iteration caps. Use LangChain tools for in-process logic, MCP for cross-service boundaries."*

---
