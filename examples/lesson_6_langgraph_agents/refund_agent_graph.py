"""
Lesson 6 — LangGraph refund agent (simplified production pattern).

Nodes: retrieve_policy → check_eligibility → auto_refund | human_approval → end
Demonstrates: StateGraph, conditional edges, ToolNode pattern, max steps.

Requires: OPENAI_API_KEY, pip install langgraph langchain-openai
"""
from __future__ import annotations

import os
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    order_id: str
    amount: float
    eligible: bool
    needs_human: bool
    refunded: bool


# Mock tools — replace with real CRM/payment APIs
def fetch_order(order_id: str) -> dict:
    return {"order_id": order_id, "amount": 45.0, "status": "delivered", "days_since": 5}


def refund_order(order_id: str, amount: float) -> dict:
    return {"order_id": order_id, "refunded": amount, "status": "success"}


REFUND_POLICY = """
Refunds allowed within 30 days for delivered orders under $100 automatically.
Above $100 or outside 30 days requires human approval.
"""


def retrieve_policy(state: AgentState) -> AgentState:
    return {
        **state,
        "messages": state["messages"]
        + [SystemMessage(content=f"Refund policy:\n{REFUND_POLICY}")],
    }


def check_eligibility(state: AgentState) -> AgentState:
    order = fetch_order(state["order_id"])
    amount = order["amount"]
    days = order["days_since"]
    eligible = days <= 30 and amount <= 100
    needs_human = not eligible and days <= 30
    return {**state, "amount": amount, "eligible": eligible, "needs_human": needs_human}


def route_after_check(state: AgentState) -> Literal["auto_refund", "human_approval", "reject"]:
    if state["eligible"]:
        return "auto_refund"
    if state["needs_human"]:
        return "human_approval"
    return "reject"


def auto_refund(state: AgentState) -> AgentState:
    result = refund_order(state["order_id"], state["amount"])
    return {
        **state,
        "refunded": True,
        "messages": state["messages"] + [AIMessage(content=f"Refund processed: {result}")],
    }


def human_approval(state: AgentState) -> AgentState:
    # In production: interrupt() and wait for human via LangGraph checkpoint
    return {
        **state,
        "messages": state["messages"]
        + [AIMessage(content="Escalated to human agent for approval.")],
    }


def reject(state: AgentState) -> AgentState:
    return {
        **state,
        "messages": state["messages"]
        + [AIMessage(content="Order is not eligible for refund per policy.")],
    }


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("retrieve_policy", retrieve_policy)
    g.add_node("check_eligibility", check_eligibility)
    g.add_node("auto_refund", auto_refund)
    g.add_node("human_approval", human_approval)
    g.add_node("reject", reject)
    g.set_entry_point("retrieve_policy")
    g.add_edge("retrieve_policy", "check_eligibility")
    g.add_conditional_edges("check_eligibility", route_after_check)
    g.add_edge("auto_refund", END)
    g.add_edge("human_approval", END)
    g.add_edge("reject", END)
    return g.compile()


if __name__ == "__main__":
    graph = build_graph()
    initial: AgentState = {
        "messages": [HumanMessage(content="I want a refund for order ORD-123")],
        "order_id": "ORD-123",
        "amount": 0.0,
        "eligible": False,
        "needs_human": False,
        "refunded": False,
    }
    final = graph.invoke(initial)
    print(final["messages"][-1].content)
