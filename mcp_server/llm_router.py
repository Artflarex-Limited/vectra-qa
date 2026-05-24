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
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""
    content: str
    model: str
    provider: str
    usage: Dict[str, int]
    raw_response: Any


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
    
    def __init__(self):
        self.clients = {}
        self._init_clients()
    
    def _init_clients(self):
        """Initialize provider clients lazily."""
        # OpenAI-compatible clients (OpenAI, MiniMax, Kimi, Local)
        try:
            from openai import OpenAI
            
            # OpenAI
            if os.getenv("OPENAI_API_KEY"):
                self.clients["openai"] = OpenAI(
                    api_key=os.getenv("OPENAI_API_KEY"),
                    base_url="https://api.openai.com/v1"
                )
            
            # MiniMax (OpenAI-compatible)
            if os.getenv("MINIMAX_API_KEY"):
                self.clients["minimax"] = OpenAI(
                    api_key=os.getenv("MINIMAX_API_KEY"),
                    base_url=os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
                )
            
            # Kimi/Moonshot (OpenAI-compatible)
            if os.getenv("KIMI_API_KEY"):
                self.clients["kimi"] = OpenAI(
                    api_key=os.getenv("KIMI_API_KEY"),
                    base_url=os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
                )
            
            # Local LLM (Ollama, LM Studio, etc.)
            if os.getenv("LOCAL_LLM_BASE_URL"):
                self.clients["local"] = OpenAI(
                    api_key="not-needed",
                    base_url=os.getenv("LOCAL_LLM_BASE_URL")
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
            import google.generativeai as genai
            if os.getenv("GOOGLE_API_KEY"):
                genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
                self.clients["google"] = genai
        except ImportError:
            print("Warning: google-generativeai package not installed. Google provider unavailable.")
    
    def _parse_model(self, model: str) -> tuple:
        """Parse provider/model-name format."""
        if "/" in model:
            provider, model_name = model.split("/", 1)
            return provider, model_name
        else:
            # Default to openai if no provider specified
            return "openai", model
    
    def complete(self, model: str, messages: List[Dict[str, str]], 
                 temperature: float = 0.7, max_tokens: int = 4096,
                 **kwargs) -> LLMResponse:
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
        provider, model_name = self._parse_model(model)
        
        if provider not in self.clients:
            raise ValueError(f"Provider '{provider}' not initialized. Check your .env configuration.")
        
        # Route to appropriate provider
        if provider in ["openai", "minimax", "kimi", "local"]:
            return self._openai_complete(provider, model_name, messages, temperature, max_tokens, **kwargs)
        elif provider == "anthropic":
            return self._anthropic_complete(model_name, messages, temperature, max_tokens, **kwargs)
        elif provider == "google":
            return self._google_complete(model_name, messages, temperature, max_tokens, **kwargs)
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    def _openai_complete(self, provider: str, model: str, messages: List[Dict],
                        temperature: float, max_tokens: int, **kwargs) -> LLMResponse:
        """Handle OpenAI-compatible API calls (OpenAI, MiniMax, Kimi, Local)."""
        client = self.clients[provider]
        
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        return LLMResponse(
            content=response.choices[0].message.content,
            model=model,
            provider=provider,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            },
            raw_response=response
        )
    
    def _anthropic_complete(self, model: str, messages: List[Dict],
                           temperature: float, max_tokens: int, **kwargs) -> LLMResponse:
        """Handle Anthropic API calls."""
        client = self.clients["anthropic"]
        
        # Convert messages to Anthropic format
        system_msg = None
        anthropic_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        response = client.messages.create(
            model=model,
            system=system_msg,
            messages=anthropic_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        return LLMResponse(
            content=response.content[0].text,
            model=model,
            provider="anthropic",
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens
            },
            raw_response=response
        )
    
    def _google_complete(self, model: str, messages: List[Dict],
                        temperature: float, max_tokens: int, **kwargs) -> LLMResponse:
        """Handle Google Gemini API calls."""
        client = self.clients["google"]
        
        # Get model instance
        model_instance = client.GenerativeModel(model)
        
        # Convert messages to Gemini format (simple string concatenation for now)
        prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
        
        response = model_instance.generate_content(
            prompt,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }
        )
        
        return LLMResponse(
            content=response.text,
            model=model,
            provider="google",
            usage={
                "prompt_tokens": 0,  # Google doesn't always return token counts
                "completion_tokens": 0,
                "total_tokens": 0
            },
            raw_response=response
        )
    
    def get_available_models(self) -> Dict[str, List[str]]:
        """Get list of available models per provider."""
        models = {}
        
        if "openai" in self.clients:
            models["openai"] = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]
        if "anthropic" in self.clients:
            models["anthropic"] = ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"]
        if "google" in self.clients:
            models["google"] = ["gemini-1.5-pro", "gemini-1.5-flash"]
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
        "data_validator": os.getenv("DATA_VALIDATOR_MODEL", "openai/gpt-4o")
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