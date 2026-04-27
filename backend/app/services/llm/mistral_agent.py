"""
CFIS Mistral Agent
==================
Handles API calls to Mistral AI endpoints for the multi-agent routing array.
"""

from typing import Optional
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.core.config import get_settings

settings = get_settings()
log = structlog.get_logger("cfis.mistral")

class MistralAgent:
    def __init__(self, api_key: str):
        try:
            try:
                from mistralai.client import MistralClient
            except ImportError:
                from mistralai import MistralClient  # type: ignore
            self.client = MistralClient(api_key=api_key)
            self.is_ready = True
        except ImportError:
            log.warning("mistral_client_not_installed", message="pip install mistralai")
            self.is_ready = False
            self.client = None
        except Exception as e:
            log.error("mistral_init_error", error=str(e))
            self.is_ready = False
            self.client = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    def call(self, prompt: str, model_name: str = "mistral-small-latest") -> Optional[str]:
        if not self.is_ready:
            raise RuntimeError("Mistral client not initialized properly.")
            
        response = self.client.chat(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=2048,
        )
        return response.choices[0].message.content
