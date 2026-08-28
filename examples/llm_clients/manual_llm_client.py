import json
import urllib.request
import urllib.error
from typing import Dict, Any, Generator

class ManualLLMClient:
    """
    A bare-bones HTTP client for calling OpenAI-compatible LLM APIs.
    We avoid using the official openai SDK or requests library to show the raw HTTP protocol.
    """
    
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        # The API key is sent in the HTTP Authorization header to authenticate the client.
        self.api_key = api_key
        # The base URL defines where the gateway server is located.
        self.base_url = base_url.rstrip("/")

    def generate_chat_completion(self, model: str, prompt: str, temperature: float = 0.7) -> Dict[str, Any]:
        """
        Sends a POST request to /chat/completions and returns the full JSON response.
        """
        url = f"{self.base_url}/chat/completions"
        
        # We construct the exact payload expected by the completions endpoint.
        # This structure is standard across OpenAI and many compatible providers.
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature
        }
        
        # Serialize the Python dictionary into a JSON string and encode to bytes.
        data = json.dumps(payload).encode("utf-8")
        
        # Set up headers. Content-Type and Authorization are mandatory.
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # Build the HTTP request object.
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        try:
            # Open the socket and perform the request.
            with urllib.request.urlopen(req) as response:
                # Read the complete response body from the buffer.
                raw_response = response.read().decode("utf-8")
                # Deserialize the JSON string back into a Python dictionary.
                return json.loads(raw_response)
        except urllib.error.HTTPError as e:
            # Handle HTTP errors (e.g., 401 Unauthorized, 429 Rate Limited, 500 Internal Error)
            error_info = e.read().decode("utf-8")
            raise RuntimeError(f"LLM API Error (HTTP {e.code}): {error_info}")

    def stream_chat_completion(self, model: str, prompt: str, temperature: float = 0.7) -> Generator[str, None, None]:
        """
        Sends a POST request with stream=True and yields tokens as they arrive using SSE.
        """
        url = f"{self.base_url}/chat/completions"
        
        # Activating streaming changes how the server transmits the response.
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "stream": True
        }
        
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        try:
            with urllib.request.urlopen(req) as response:
                # Read line-by-line from the response stream
                for line in response:
                    # SSE lines are prefixed with 'data: ' and end with a newline
                    decoded_line = line.decode("utf-8").strip()
                    
                    if not decoded_line:
                        continue
                    
                    # SSE protocol specifies 'data: [DONE]' to signify completion
                    if decoded_line == "data: [DONE]":
                        break
                    
                    if decoded_line.startswith("data: "):
                        # Extract the JSON payload after the prefix
                        json_str = decoded_line[len("data: "):]
                        try:
                            chunk = json.loads(json_str)
                            # In streaming responses, the delta field contains the new token
                            delta = chunk["choices"][0]["delta"]
                            if "content" in delta:
                                yield delta["content"]
                        except json.JSONDecodeError:
                            # Safely handle malformed chunks or comments
                            continue
        except urllib.error.HTTPError as e:
            error_info = e.read().decode("utf-8")
            raise RuntimeError(f"LLM API Error (HTTP {e.code}): {error_info}")
