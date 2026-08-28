from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# Define the shape of our state. The state is the single source of truth 
# that is passed between nodes and modified during graph execution.
class State(TypedDict):
    prompt: str
    response: str
    model: str
    api_key: str
    base_url: str

# Define the node function. A node is a standard Python function that 
# accepts the current state and returns a dictionary of keys to update.
def call_model_node(state: State) -> dict:
    """
    Graph node that executes the LLM completion.
    """
    # Instantiate the LangChain chat model.
    llm = ChatOpenAI(
        model=state["model"],
        openai_api_key=state["api_key"],
        openai_api_base=state["base_url"],
        temperature=0.7
    )
    
    # Call the model.
    response = llm.invoke([HumanMessage(content=state["prompt"])])
    
    # Return a dictionary containing the key(s) to update in the global State.
    return {"response": response.content}

class LangGraphLLMClient:
    """
    An LLM client wrapper that uses LangGraph to orchestrate a single LLM invocation.
    Even though a single call is simple, this sets up the structural graph patterns.
    """
    
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.base_url = base_url
        
        # Build the graph.
        workflow = StateGraph(State)
        
        # Add the nodes.
        workflow.add_node("call_model", call_model_node)
        
        # Add the edges (flow control).
        workflow.add_edge(START, "call_model")
        workflow.add_edge("call_model", END)
        
        # Compile the workflow into a runnable application.
        self.app = workflow.compile()

    def generate_chat_completion(self, model: str, prompt: str) -> str:
        """
        Executes the graph by passing initial state values.
        """
        initial_state = {
            "prompt": prompt,
            "model": model,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "response": ""
        }
        
        # Running the graph returns the final state after processing all nodes.
        final_state = self.app.invoke(initial_state)
        return final_state["response"]
