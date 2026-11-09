from typing import Optional, Dict
from backend.config import settings
from backend.llm.base import BaseLLMProvider
from backend.llm.gemini_provider import GeminiProvider
from backend.llm.local_nlp_provider import LocalNLPProvider

_cached_providers: Dict[str, BaseLLMProvider] = {}
_runtime_provider: Optional[str] = None

def set_active_provider(provider_name: str) -> str:
    """Switches the active LLM / NLP provider at runtime (e.g. 'local' or 'gemini')."""
    global _runtime_provider
    _runtime_provider = provider_name.lower().strip()
    return _runtime_provider

def get_active_provider_name() -> str:
    """Returns the name of the currently active provider."""
    return _runtime_provider or settings.LLM_PROVIDER.lower()

def get_llm_provider(provider_name: Optional[str] = None, model: Optional[str] = None) -> BaseLLMProvider:
    """
    Returns a persistent cached provider instance.
    Supports:
      - 'local' / 'self_learning': 100% offline self-learning NLP model.
      - 'gemini': Google Gemini LLM API provider.
    """
    provider = (provider_name or _runtime_provider or settings.LLM_PROVIDER).lower()
    model_name = model or settings.GEMINI_MODEL
    cache_key = f"{provider}::{model_name}"

    if cache_key not in _cached_providers:
        if provider in ("local", "self_learning", "nlp", "offline"):
            _cached_providers[cache_key] = LocalNLPProvider()
        else:
            _cached_providers[cache_key] = GeminiProvider(
                api_key=settings.GEMINI_API_KEY, 
                model=model_name
            )
    return _cached_providers[cache_key]
