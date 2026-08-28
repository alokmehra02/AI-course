import json
import logging
import asyncio
from typing import Dict, Any, List, Generator, AsyncGenerator, Optional
import httpx
from pydantic import BaseModel, Field, ValidationError

# Configure robust logging for production observability.
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ManualLLMEngine")

# =====================================================================
# 1. Structured Output Schema (Pydantic)
# =====================================================================
class FinancialAnalysis(BaseModel):
    """
    Pydantic schema enforcing structured model output.
    Used to guarantee response format and field type safety.
    """
    ticker: str = Field(..., description="The stock ticker symbol.")
    current_price: float = Field(..., description="The current market price of the stock.")
    recommendation: str = Field(..., description="Investment action: BUY, SELL, or HOLD.")
    justification: str = Field(..., description="The data-driven reason behind the recommendation.")

# =====================================================================
# 2. Mock Tool Implementation
# =====================================================================
async def get_stock_price(ticker: str) -> float:
    """
    Mock external API call. In production, this would make an outbound HTTP 
    request to a service like Bloomberg or Yahoo Finance.
    """
    logger.info(f"Executing external tool 'get_stock_price' for ticker: {ticker}")
    # Simulating standard network I/O latency
    await asyncio.sleep(0.5)
    prices = {"AAPL": 175.50, "MSFT": 420.25, "GOOGL": 150.75}
    return prices.get(ticker.upper(), 100.0)

# Declare the schema of our tool in the format required by the OpenAI/Anthropic gateway.
STOCK_PRICE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_stock_price",
        "description": "Fetch the current real-time stock price for a given ticker symbol.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "The stock ticker symbol (e.g., AAPL, MSFT)."
                }
            },
            "required": ["ticker"]
        }
    }
}

# =====================================================================
# 3. Manual LLM Client Engine
# =====================================================================
class ManualLLMEngine:
    """
    A production-ready, frameworkless async client to interface with LLM endpoints.
    Handles streaming, function calling loop resolution, and Pydantic validation.
    """
    
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        if not api_key:
            raise ValueError("API Key is required to initialize ManualLLMEngine")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        # We reuse an HTTP client session to support connection pooling and keep-alives,
        # which is crucial for reducing TCP handshake overhead in production.
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=httpx.Timeout(30.0, read=60.0)
        )

    async def close(self) -> None:
        """Gracefully release the HTTP connection pool resources."""
        await self.client.aclose()

    async def call_chat_completions(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o",
        temperature: float = 0.7,
        top_p: float = 0.9,
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes a raw, synchronous POST request to the LLM completion gateway.
        """
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p
        }
        if tools:
            payload["tools"] = tools
        if response_format:
            payload["response_format"] = response_format

        try:
            logger.info(f"Dispatching API request to {url} with model {model}")
            response = await self.client.post(url, json=payload)
            
            # Explicit check for non-2xx status codes to throw specialized exceptions.
            if response.status_code != 200:
                raise RuntimeError(f"LLM API Error (HTTP {response.status_code}): {response.text}")
                
            return response.json()
        except httpx.RequestError as exc:
            logger.error(f"Network transport error occurred: {exc}")
            raise RuntimeError(f"Failed to connect to LLM gateway: {exc}")

    async def call_chat_stream(
        self,
        messages: List[Dict[str, Any]],
        model: str = "gpt-4o",
        temperature: float = 0.7
    ) -> AsyncGenerator[str, None]:
        """
        Streams completions token-by-token using raw HTTP SSE stream processing.
        """
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True
        }

        try:
            logger.info("Initializing server-sent events stream connection.")
            async with self.client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise RuntimeError(f"Streaming failed (HTTP {response.status_code}): {error_text.decode('utf-8')}")

                # Read the response chunks line-by-line.
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    
                    if line == "data: [DONE]":
                        break
                    
                    if line.startswith("data: "):
                        json_str = line[len("data: "):]
                        try:
                            chunk = json.loads(json_str)
                            delta = chunk["choices"][0]["delta"]
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                        except (json.JSONDecodeError, KeyError, IndexError):
                            # Skip malformed SSE lines or ping packets.
                            continue
        except httpx.RequestError as exc:
            logger.error(f"Streaming network error: {exc}")
            raise RuntimeError(f"Streaming connection lost: {exc}")

    async def execute_agent_loop(self, user_prompt: str, model: str = "gpt-4o") -> FinancialAnalysis:
        """
        Runs a frameworkless execution loop for function calling and structured outputs.
        1. Sends prompt with tool schemas.
        2. Detects if tool calls are requested.
        3. Invokes tool locally.
        4. Submits tool results back to LLM.
        5. Forces model to reply in structured JSON and parses response into Pydantic.
        """
        # Step 1: Initialize conversation history
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": "You are a financial analyst. Provide stock recommendations in JSON format fitting the requested schema."},
            {"role": "user", "content": user_prompt}
        ]

        # Step 2: First LLM invocation, providing the stock price tool
        first_resp = await self.call_chat_completions(
            messages=messages,
            model=model,
            tools=[STOCK_PRICE_TOOL_SCHEMA]
        )

        choice = first_resp["choices"][0]
        message_data = choice["message"]
        messages.append(message_data)  # Append assistant response (which contains tool calls)

        # Step 3: Handle function calling requests
        if "tool_calls" in message_data and message_data["tool_calls"]:
            for tool_call in message_data["tool_calls"]:
                tool_id = tool_call["id"]
                fn_name = tool_call["function"]["name"]
                fn_args = json.loads(tool_call["function"]["arguments"])

                logger.info(f"LLM requested tool call: {fn_name} with arguments: {fn_args}")

                # Resolve and run the appropriate tool
                if fn_name == "get_stock_price":
                    price = await get_stock_price(fn_args.get("ticker", ""))
                    # Append the tool execution result back to the context
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": fn_name,
                        "content": json.dumps({"price": price})
                    })
                else:
                    raise ValueError(f"Unknown tool request: {fn_name}")

            # Step 4: Final LLM invocation, prompting structured JSON matching the Pydantic schema
            final_resp = await self.call_chat_completions(
                messages=messages,
                model=model,
                # Enforce JSON response format at the API gateway layer
                response_format={"type": "json_object"}
            )
            
            final_text = final_resp["choices"][0]["message"]["content"]
            logger.info(f"Raw JSON output received from model: {final_text}")

            # Step 5: Pydantic Validation
            try:
                data = json.loads(final_text)
                analysis = FinancialAnalysis(**data)
                return analysis
            except (json.JSONDecodeError, ValidationError) as e:
                logger.error(f"Model output failed validation: {e}")
                raise RuntimeError(f"Model generated invalid output structure: {e}")
        else:
            raise RuntimeError("Model failed to request tool execution as expected.")
