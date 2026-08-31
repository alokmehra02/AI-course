"""
Lesson 7 — Agent tool loop (function calling pattern).

This demonstrates the same loop MCP enables: LLM → tool call → execute → feed result → repeat.
For native MCP, use the `mcp` Python SDK to connect to an MCP server; this file shows
the underlying pattern without requiring an MCP server process.

Requires: OPENAI_API_KEY
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": "Search internal knowledge base for company policies",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]


def execute_tool(name: str, args: dict[str, Any]) -> str:
    if name == "get_weather":
        return json.dumps({"city": args["city"], "temp_c": 28, "condition": "sunny"})
    if name == "search_kb":
        return json.dumps(
            {"query": args["query"], "snippet": "Refund policy: 30 days for orders under $100."}
        )
    return json.dumps({"error": f"Unknown tool {name}"})


async def chat_with_tools(user_message: str, max_rounds: int = 5) -> str:
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": "You are a helpful assistant. Use tools when needed. Max 3 tool calls.",
        },
        {"role": "user", "content": user_message},
    ]
    async with httpx.AsyncClient() as client:
        for _ in range(max_rounds):
            payload = {
                "model": "gpt-4o-mini",
                "messages": messages,
                "tools": TOOLS,
                "tool_choice": "auto",
            }
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                json=payload,
                timeout=60.0,
            )
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            messages.append(msg)
            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                return msg.get("content", "")
            for tc in tool_calls:
                fn = tc["function"]
                result = execute_tool(fn["name"], json.loads(fn["arguments"]))
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    }
                )
    return "Max tool rounds exceeded"


if __name__ == "__main__":
    answer = asyncio.run(
        chat_with_tools("What's the weather in Mumbai and what's our refund policy?")
    )
    print(answer)
