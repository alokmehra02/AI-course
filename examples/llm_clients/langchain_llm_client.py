from typing import Generator
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

class LangChainLLMClient:
    """
    An LLM client that leverages LangChain's unified ChatOpenAI wrapper.
    This replaces manual HTTP request building, response parsing, and manual stream decoding.
    """
    
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        # We initialize the ChatOpenAI client.
        # Behind the scenes, LangChain sets up connection pooling and default header configurations.
        self.api_key = api_key
        self.base_url = base_url

    def generate_chat_completion(self, model: str, prompt: str, temperature: float = 0.7) -> str:
        """
        Sends the message using LangChain's .invoke() interface.
        """
        # ChatOpenAI encapsulates all the configuration and credentials needed for the request.
        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            openai_api_key=self.api_key,
            openai_api_base=self.base_url
        )
        
        # We wrap our plain string prompt in a HumanMessage object, 
        # which is LangChain's representation of a message sent by a user.
        messages = [HumanMessage(content=prompt)]
        
        # invoke() makes the synchronous POST call, performs any needed error retries,
        # and returns a structured AIMessage object containing the text content.
        response = llm.invoke(messages)
        return response.content

    def stream_chat_completion(self, model: str, prompt: str, temperature: float = 0.7) -> Generator[str, None, None]:
        """
        Streams the response token-by-token using LangChain's .stream() interface.
        """
        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            openai_api_key=self.api_key,
            openai_api_base=self.base_url
        )
        
        messages = [HumanMessage(content=prompt)]
        
        # stream() returns a generator yielding AIMessageChunk tokens.
        # LangChain handles the SSE parsing loop behind the scenes.
        for chunk in llm.stream(messages):
            yield chunk.content
