import logging
from typing import AsyncGenerator
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger("LangChainLLMEngine")

# =====================================================================
# 1. Structured Output Schema (Pydantic)
# =====================================================================
class FinancialAnalysis(BaseModel):
    ticker: str = Field(..., description="The stock ticker symbol.")
    current_price: float = Field(..., description="The current market price of the stock.")
    recommendation: str = Field(..., description="Investment action: BUY, SELL, or HOLD.")
    justification: str = Field(..., description="The data-driven reason behind the recommendation.")

# =====================================================================
# 2. Tool Implementation using LangChain's decorator
# =====================================================================
@tool
async def get_stock_price_tool(ticker: str) -> float:
    """Fetch the current real-time stock price for a given ticker symbol."""
    logger.info(f"Executing LangChain tool 'get_stock_price_tool' for ticker: {ticker}")
    prices = {"AAPL": 175.50, "MSFT": 420.25, "GOOGL": 150.75}
    return prices.get(ticker.upper(), 100.0)

# =====================================================================
# 3. LangChain LLM Client Engine
# =====================================================================
class LangChainLLMEngine:
    """
    An LLM client engine using LangChain's abstractions to replace 
    raw HTTP calls, payload serialization, and manual JSON verification.
    """

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.base_url = base_url

    async def call_chat_completions(
        self,
        prompt: str,
        model: str = "gpt-4o",
        temperature: float = 0.7
    ) -> str:
        """
        Equivalent chat completion using invoke.
        """
        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            openai_api_key=self.api_key,
            openai_api_base=self.base_url
        )
        messages = [HumanMessage(content=prompt)]
        response = await llm.ainvoke(messages)
        return response.content

    async def call_chat_stream(
        self,
        prompt: str,
        model: str = "gpt-4o",
        temperature: float = 0.7
    ) -> AsyncGenerator[str, None]:
        """
        Equivalent streaming utilizing .astream().
        """
        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            openai_api_key=self.api_key,
            openai_api_base=self.base_url
        )
        messages = [HumanMessage(content=prompt)]
        async for chunk in llm.astream(messages):
            yield chunk.content

    async def execute_agent_loop(self, user_prompt: str, model: str = "gpt-4o") -> FinancialAnalysis:
        """
        Runs the equivalent flow using LangChain tool binding and structured output helpers.
        NOTE: LangChain does NOT automatically execute the tools and loop back
        without a custom runner or agent executor. We still write the loop logic here
        to demonstrate the limits of raw LangChain (before moving to LangGraph).
        """
        # Initialize LLM bound with our tool definitions.
        llm = ChatOpenAI(
            model=model,
            openai_api_key=self.api_key,
            openai_api_base=self.base_url,
            temperature=0.7
        )
        
        # Bind tools to the model.
        # This replaces manual formatting of STOCK_PRICE_TOOL_SCHEMA and parameters.
        llm_with_tools = llm.bind_tools([get_stock_price_tool])
        
        messages = [
            SystemMessage(content="You are a financial analyst. Provide stock recommendations."),
            HumanMessage(content=user_prompt)
        ]

        # Call model to get tool call instructions.
        response = await llm_with_tools.ainvoke(messages)
        messages.append(response)

        if response.tool_calls:
            for tool_call in response.tool_calls:
                # Find and execute the matched tool
                if tool_call["name"] == "get_stock_price_tool":
                    # Execute tool function asynchronously
                    tool_result = await get_stock_price_tool.ainvoke(tool_call["args"])
                    
                    # Construct and append ToolMessage.
                    # This replaces the manual role="tool" payload formatting.
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": tool_call["name"],
                        "content": str(tool_result)
                    })
            
            # Request structured output.
            # with_structured_output binds a Pydantic schema and configures the LLM response_format/tool parameters.
            structured_llm = llm.with_structured_output(FinancialAnalysis)
            final_result = await structured_llm.ainvoke(messages)
            
            # The output is parsed directly into our FinancialAnalysis Pydantic object by LangChain.
            return final_result
        else:
            raise RuntimeError("Model did not request tool call execution.")
