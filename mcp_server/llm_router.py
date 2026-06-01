"""
LLM Router Module

Handles multi-provider LLM routing for the Vectra QA framework.
Supports: OpenAI, Anthropic, Google, Local (Ollama/LM Studio), MiniMax, Kimi

Usage:
    from llm_router import LLMRouter

    router = LLMRouter()
    response = router.complete(
        model="minimax/minimax-text-01",
        messages=[{"role": "user", "content": "Test this login form"}]
    )
"""

import os
import json
import hashlib
import threading
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""

    content: str
    model: str
    provider: str
    usage: Dict[str, int]
    raw_response: Any


class LLMCache:
    """
    LLM response cache with PostgreSQL persistence.

    Uses in-memory LRU cache for performance with PostgreSQL as durable store.
    Concurrent-safe via ACID transactions. Replaces JSON file cache.
    """

    def __init__(self, ttl_seconds: int = 3600, persist_path: Optional[str] = None):
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self.db: Any = None
        self._use_postgres = self._init_postgres()
        # Keep file fallback for backward compatibility
        self.persist_path = Path(persist_path) if persist_path else None
        if not self._use_postgres and self.persist_path:
            self._load_from_disk()

    def _init_postgres(self) -> bool:
        """Initialize PostgreSQL connection if available."""
        try:
            from mcp_server.db import get_db_manager_sync

            self.db = get_db_manager_sync()
            return bool(self.db._initialized)
        except Exception as e:
            logger.warning("db_init_failed", error=str(e))
            return False

    def _generate_key(
        self, model: str, messages: List[Dict], temperature: float, max_tokens: int
    ) -> str:
        """Generate cache key from request parameters."""
        cache_data = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        cache_json = json.dumps(cache_data, sort_keys=True)
        return hashlib.sha256(cache_json.encode()).hexdigest()

    def get(
        self, model: str, messages: List[Dict], temperature: float, max_tokens: int
    ) -> Optional[LLMResponse]:
        """Get cached response if available and not expired."""
        key = self._generate_key(model, messages, temperature, max_tokens)

        # Check memory cache first
        with self._lock:
            entry = self._memory_cache.get(key)
            if entry and time.time() - entry["timestamp"] <= self.ttl_seconds:
                return LLMResponse(
                    content=entry["content"],
                    model=entry["model"],
                    provider=entry["provider"],
                    usage=entry["usage"],
                    raw_response=None,
                )

        # Check PostgreSQL
        if self._use_postgres:
            try:
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Async context - can't block, skip DB read for now
                    pass
                else:
                    row = loop.run_until_complete(
                        self.db.fetchone(
                            "SELECT content, model, provider, usage_tokens, created_at FROM llm_cache WHERE hash_key = %s AND expires_at > NOW()",
                            (key,),
                        )
                    )
                    if row:
                        entry = {
                            "content": row["content"],
                            "model": row["model"],
                            "provider": row["provider"],
                            "usage": {"total_tokens": row.get("usage_tokens", 0)},
                            "timestamp": (
                                row["created_at"].timestamp()
                                if hasattr(row["created_at"], "timestamp")
                                else time.time()
                            ),
                        }
                        with self._lock:
                            self._memory_cache[key] = entry
                        return LLMResponse(
                            content=entry["content"],
                            model=entry["model"],
                            provider=entry["provider"],
                            usage=entry["usage"],
                            raw_response=None,
                        )
            except Exception as e:
                logger.warning("cache_read_failed", error=str(e), source="postgresql")

        return None

    def set(
        self,
        model: str,
        messages: List[Dict],
        temperature: float,
        max_tokens: int,
        response: LLMResponse,
    ) -> None:
        """Cache a response."""
        key = self._generate_key(model, messages, temperature, max_tokens)
        now = time.time()
        expires = datetime.fromtimestamp(now + self.ttl_seconds, timezone.utc)

        entry = {
            "content": response.content,
            "model": response.model,
            "provider": response.provider,
            "usage": response.usage,
            "timestamp": now,
        }
        with self._lock:
            self._memory_cache[key] = entry

        # Persist to PostgreSQL
        if self._use_postgres:
            try:
                import asyncio

                loop = asyncio.get_event_loop()
                if not loop.is_running():
                    loop.run_until_complete(
                        self.db.execute(
                            """
                            INSERT INTO llm_cache (hash_key, model, content, provider, usage_tokens, expires_at)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (hash_key) DO UPDATE SET
                                content = EXCLUDED.content,
                                provider = EXCLUDED.provider,
                                usage_tokens = EXCLUDED.usage_tokens,
                                expires_at = EXCLUDED.expires_at
                            """,
                            (
                                key,
                                model,
                                response.content,
                                response.provider,
                                response.usage.get("total_tokens", 0),
                                expires,
                            ),
                        )
                    )
            except Exception as e:
                logger.warning("cache_write_failed", error=str(e), source="postgresql")

        # Fallback to disk
        if not self._use_postgres and self.persist_path:
            self._save_to_disk()

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._memory_cache.clear()
        if self._use_postgres:
            try:
                import asyncio

                loop = asyncio.get_event_loop()
                if not loop.is_running():
                    loop.run_until_complete(self.db.execute("DELETE FROM llm_cache"))
            except Exception as e:
                logger.warning("cache_clear_failed", error=str(e), source="postgresql")
        if self.persist_path and self.persist_path.exists():
            self.persist_path.unlink()

    def _save_to_disk(self) -> None:
        """Persist cache to disk (legacy fallback)."""
        if not self.persist_path:
            return
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.persist_path, "w") as f:
                with self._lock:
                    json.dump(self._memory_cache, f)
        except Exception as e:
            logger.warning("cache_disk_save_failed", error=str(e))

    def _load_from_disk(self) -> None:
        """Load cache from disk (legacy fallback)."""
        if not self.persist_path or not self.persist_path.exists():
            return
        try:
            with open(self.persist_path, "r") as f:
                data = json.load(f)
            with self._lock:
                self._memory_cache = data
                now = time.time()
                expired_keys = [
                    k
                    for k, v in self._memory_cache.items()
                    if now - v["timestamp"] > self.ttl_seconds
                ]
                for k in expired_keys:
                    del self._memory_cache[k]
        except Exception as e:
            logger.warning("cache_disk_load_failed", error=str(e))


class LLMRouter:
    """
    Routes LLM requests to the appropriate provider based on model identifier.

    Model format: provider/model-name
    Examples:
        - openai/gpt-4o
        - anthropic/claude-3-5-sonnet-20241022
        - minimax/minimax-text-01
        - kimi/kimi-k2
        - local/llama3.1:70b
    """

    def __init__(self, cache_enabled: bool = True):
        self.clients: Dict[str, Any] = {}
        self._init_clients()

        # Initialize cache if enabled
        self.cache = None
        if cache_enabled and os.getenv("VECTRA_LLM_CACHE", "true").lower() == "true":
            cache_path = os.getenv("VECTRA_LLM_CACHE_PATH", "/app/obsidian_vault/.llm_cache.json")
            ttl = int(os.getenv("VECTRA_LLM_CACHE_TTL", "3600"))
            self.cache = LLMCache(ttl_seconds=ttl, persist_path=cache_path)
            print(f"LLM cache enabled (TTL: {ttl}s, path: {cache_path})")

    def _init_clients(self):
        """Initialize provider clients lazily."""
        # OpenAI-compatible clients (OpenAI, MiniMax, Kimi, Local)
        try:
            from openai import OpenAI

            # OpenAI
            if os.getenv("OPENAI_API_KEY"):
                self.clients["openai"] = OpenAI(
                    api_key=os.getenv("OPENAI_API_KEY"), base_url="https://api.openai.com/v1"
                )

            # MiniMax (OpenAI-compatible)
            if os.getenv("MINIMAX_API_KEY"):
                self.clients["minimax"] = OpenAI(
                    api_key=os.getenv("MINIMAX_API_KEY"),
                    base_url=os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1"),
                )

            # Kimi/Moonshot (OpenAI-compatible)
            if os.getenv("KIMI_API_KEY"):
                self.clients["kimi"] = OpenAI(
                    api_key=os.getenv("KIMI_API_KEY"),
                    base_url=os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1"),
                )

            # Local LLM (Ollama, LM Studio, etc.)
            if os.getenv("LOCAL_LLM_BASE_URL"):
                self.clients["local"] = OpenAI(
                    api_key="not-needed", base_url=os.getenv("LOCAL_LLM_BASE_URL")
                )

        except ImportError:
            print("Warning: openai package not installed. OpenAI-compatible providers unavailable.")

        # Anthropic (separate SDK)
        try:
            import anthropic

            if os.getenv("ANTHROPIC_API_KEY"):
                self.clients["anthropic"] = anthropic.Anthropic(
                    api_key=os.getenv("ANTHROPIC_API_KEY")
                )
        except ImportError:
            print("Warning: anthropic package not installed. Anthropic provider unavailable.")

        # Google (separate SDK)
        try:
            from google import genai

            if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
                self.clients["google"] = genai.Client(
                    api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
                )
        except ImportError:
            print("Warning: google-genai package not installed. Google provider unavailable.")

    def _parse_model(self, model: str) -> tuple:
        """Parse provider/model-name format."""
        if "/" in model:
            provider, model_name = model.split("/", 1)
            return provider, model_name
        else:
            # Default to openai if no provider specified
            return "openai", model

    def complete(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse:
        """
        Send a completion request to the specified model.

        Args:
            model: Provider/model-name (e.g., "minimax/minimax-text-01")
            messages: List of message dicts with "role" and "content"
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMResponse with standardized fields
        """
        # Check cache first
        if hasattr(self, "cache") and self.cache:
            cached = self.cache.get(model, messages, temperature, max_tokens)
            if cached:
                print(f"LLM cache hit for {model}")
                # Track cache hit (zero cost)
                try:
                    from mcp_server.cost_tracker import get_cost_tracker

                    tracker = get_cost_tracker()
                    tracker.track_usage(
                        model=model,
                        input_tokens=0,
                        output_tokens=0,
                        provider="cache",
                        cache_hit=True,
                    )
                except Exception as e:
                    logger.warning("cache_cost_tracking_failed", error=str(e))
                return cached

        provider, model_name = self._parse_model(model)

        if provider not in self.clients:
            raise ValueError(
                f"Provider '{provider}' not initialized. Check your .env configuration."
            )

        # Route to appropriate provider
        if provider in ["openai", "minimax", "kimi", "local"]:
            response = self._openai_complete(
                provider, model_name, messages, temperature, max_tokens, **kwargs
            )
        elif provider == "anthropic":
            response = self._anthropic_complete(
                model_name, messages, temperature, max_tokens, **kwargs
            )
        elif provider == "google":
            response = self._google_complete(
                model_name, messages, temperature, max_tokens, **kwargs
            )
        else:
            raise ValueError(f"Unknown provider: {provider}")

        # Cache the response
        if hasattr(self, "cache") and self.cache:
            self.cache.set(model, messages, temperature, max_tokens, response)

        # Track cost
        try:
            from mcp_server.cost_tracker import get_cost_tracker

            tracker = get_cost_tracker()
            usage = response.usage
            tracker.track_usage(
                model=model,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                provider=provider,
            )
        except Exception as e:
            logger.debug("cost_tracking_failed", error=str(e))

        return response

    def _openai_complete(
        self,
        provider: str,
        model: str,
        messages: List[Dict],
        temperature: float,
        max_tokens: int,
        **kwargs,
    ) -> LLMResponse:
        """Handle OpenAI-compatible API calls (OpenAI, MiniMax, Kimi, Local)."""
        client = self.clients[provider]

        response = client.chat.completions.create(
            model=model, messages=messages, temperature=temperature, max_tokens=max_tokens, **kwargs
        )

        return LLMResponse(
            content=response.choices[0].message.content,
            model=model,
            provider=provider,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            raw_response=response,
        )

    def _anthropic_complete(
        self, model: str, messages: List[Dict], temperature: float, max_tokens: int, **kwargs
    ) -> LLMResponse:
        """Handle Anthropic API calls."""
        client = self.clients["anthropic"]

        # Convert messages to Anthropic format
        system_msg = None
        anthropic_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                anthropic_messages.append({"role": msg["role"], "content": msg["content"]})

        response = client.messages.create(
            model=model,
            system=system_msg,
            messages=anthropic_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        return LLMResponse(
            content=response.content[0].text,
            model=model,
            provider="anthropic",
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            },
            raw_response=response,
        )

    def _google_complete(
        self, model: str, messages: List[Dict], temperature: float, max_tokens: int, **kwargs
    ) -> LLMResponse:
        """Handle Google Gemini API calls."""
        from google.genai import types

        client = self.clients["google"]
        prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        return LLMResponse(
            content=response.text,
            model=model,
            provider="google",
            usage={
                "prompt_tokens": getattr(response.usage_metadata, 'prompt_token_count', 0) or 0,
                "completion_tokens": getattr(response.usage_metadata, 'candidates_token_count', 0) or 0,
                "total_tokens": getattr(response.usage_metadata, 'total_token_count', 0) or 0,
            },
            raw_response=response,
        )

    def get_available_models(self) -> Dict[str, List[str]]:
        """Get list of available models per provider."""
        models = {}

        if "openai" in self.clients:
            models["openai"] = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]
        if "anthropic" in self.clients:
            models["anthropic"] = ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"]
        if "google" in self.clients:
            models["google"] = ["gemini-2.5-pro", "gemini-2.0-flash"]
        if "minimax" in self.clients:
            models["minimax"] = ["minimax-text-01", "abab6.5s-chat"]
        if "kimi" in self.clients:
            models["kimi"] = ["kimi-k2", "kimi-k1.5"]
        if "local" in self.clients:
            models["local"] = [os.getenv("LOCAL_LLM_MODEL", "llama3.1:70b")]

        return models


# Global router instance
llm_router = LLMRouter()


def get_llm_response(agent_role: str, prompt: str, context: Optional[str] = None) -> str:
    """
    Convenience function to get an LLM response for a specific agent role.

    Args:
        agent_role: The role of the agent (orchestrator, ui_explorer, data_validator)
        prompt: The prompt to send
        context: Optional system context

    Returns:
        The generated text response
    """
    # Map agent roles to their configured models
    model_map = {
        "orchestrator": os.getenv("ORCHESTRATOR_MODEL", "openai/gpt-4o"),
        "ui_explorer": os.getenv("UI_EXPLORER_MODEL", "anthropic/claude-3-5-sonnet-20241022"),
        "data_validator": os.getenv("DATA_VALIDATOR_MODEL", "openai/gpt-4o"),
    }

    model = model_map.get(agent_role, "openai/gpt-4o")

    messages = []
    if context:
        messages.append({"role": "system", "content": context})
    messages.append({"role": "user", "content": prompt})

    try:
        response = llm_router.complete(model=model, messages=messages)
        return response.content
    except Exception as e:
        return f"Error calling LLM: {str(e)}"
