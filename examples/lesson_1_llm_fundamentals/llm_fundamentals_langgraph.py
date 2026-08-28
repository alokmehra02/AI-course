import logging
from typing import TypedDict, Annotated, Optional, Literal
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

logger = logging.getLogger("LangGraphLLMEngine")

# =====================================================================
# 1. Shared State Schema
# =====================================================================
class FinancialAnalysis(BaseModel):
    ticker: str = Field(..., description="The stock ticker symbol.")
    current_price: float = Field(..., description="The current market price of the stock.")
    recommendation: str = Field(..., description="Investment action: BUY, SELL, or HOLD.")
    justification: str = Field(..., description="The data-driven reason behind the recommendation.")

class AgentState(TypedDict):
    # add_messages is a reducer function. It appends new messages to the 
    # message history instead of overwriting the entire list.
    messages: Annotated[list, add_messages]
    # Holds the parsed Pydantic object upon successful pipeline completion.
    final_analysis: Optional[FinancialAnalysis]
    # Parameters needed to invoke the LLM
    model: str
    api_key: str
    base_url: str

# =====================================================================
# 2. Tool Definition
# =====================================================================
@tool
async def get_stock_price_tool(ticker: str) -> float:
    """Fetch the current real-time stock price for a given ticker symbol."""
    logger.info(f"Executing LangGraph tool 'get_stock_price_tool' for ticker: {ticker}")
    prices = {"AAPL": 175.50, "MSFT": 420.25, "GOOGL": 150.75}
    return prices.get(ticker.upper(), 100.0)

# =====================================================================
# 3. Graph Nodes
# =====================================================================
async def call_model_node(state: AgentState) -> dict:
    """
    Node that invokes the ChatOpenAI model bound with tools.
    """
    llm = ChatOpenAI(
        model=state["model"],
        openai_api_key=state["api_key"],
        openai_api_base=state["base_url"],
        temperature=0.7
    ).bind_tools([get_stock_price_tool])
    
    # Run the model
    response = await llm.ainvoke(state["messages"])
    
    # We return the new message, which the add_messages reducer will append.
    return {"messages": [response]}

async def execute_tools_node(state: AgentState) -> dict:
    """
    Node that executes tool calls in parallel and returns their results.
    """
    last_message = state["messages"][-1]
    tool_messages = []
    
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        for tool_call in last_message.tool_calls:
            if tool_call["name"] == "get_stock_price_tool":
                result = await get_stock_price_tool.ainvoke(tool_call["args"])
                tool_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": tool_call["name"],
                    "content": str(result)
                })
    return {"messages": tool_messages}

async def generate_structured_output_node(state: AgentState) -> dict:
    """
    Final node that forces structured output serialization.
    """
    llm = ChatOpenAI(
        model=state["model"],
        openai_api_key=state["api_key"],
        openai_api_base=state["base_url"],
        temperature=0.7
    ).with_structured_output(FinancialAnalysis)
    
    analysis = await llm.ainvoke(state["messages"])
    return {"final_analysis": analysis}

# =====================================================================
# 4. Conditional Edge router
# =====================================================================
def should_continue(state: AgentState) -> Literal["execute_tools", "generate_structured_output"]:
    """
    Router determining whether we need to call tools or proceed to structured output.
    """
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "execute_tools"
    return "generate_structured_output"

# =====================================================================
# 5. Graph Assembly Client
# =====================================================================
class LangGraphLLMEngine:
    """
    An orchestrator that builds and runs a compiled StateGraph.
    This replaces manual looping, control routing, and conditional evaluation.
    """
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.base_url = base_url
        
        # Instantiate StateGraph with our State structure
        builder = StateGraph(AgentState)
        
        # Add the nodes to the graph
        builder.add_node("call_model", call_model_node)
        builder.add_node("execute_tools", execute_tools_node)
        builder.add_node("generate_structured_output", generate_structured_output_node)
        
        # Connect nodes with control edges
        builder.add_edge(START, "call_model")
        
        # Add conditional routing from call_model
        builder.add_conditional_edges(
            "call_model",
            should_continue,
            {
                "execute_tools": "execute_tools",
                "generate_structured_output": "generate_structured_output"
            }
        )
        
        # Loop tool output back into the model to evaluate the tool results
        builder.add_edge("execute_tools", "call_model")
        
        # Connect output node to END
        builder.add_edge("generate_structured_output", END)
        
        # Compile graph into an executable application
        self.app = builder.compile()

    async def execute_agent_loop(self, user_prompt: str, model: str = "gpt-4o") -> FinancialAnalysis:
        initial_state = {
            "messages": [
                SystemMessage(content="You are a financial analyst. Provide stock recommendations."),
                HumanMessage(content=user_prompt)
            ],
            "final_analysis": None,
            "model": model,
            "api_key": self.api_key,
            "base_url": self.base_url
        }
        
        # Run graph
        final_state = await self.app.ainvoke(initial_state)
        return final_state["final_analysis"]
