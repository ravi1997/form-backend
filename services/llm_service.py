from __future__ import annotations

import re
import json
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from enum import Enum

from logger.unified_logger import app_logger, error_logger
from services.ai_service import AIService
from services.ai_provider import BaseAIProvider
from services.llm_model_registry_service import LLMModelRegistryService
from services.llm_usage_tracking_service import LLMUsageTrackingService
from services.llm_prompt_template_service import LLMPromptTemplateService


class LLMProvider(Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    LOCAL = "local"


class LLMModel:
    """LLM model configuration."""
    
    def __init__(
        self,
        provider: LLMProvider,
        model_id: str,
        name: str,
        max_tokens: int = 4096,
        cost_per_1k_tokens: float = 0.0,
        supports_streaming: bool = False,
        supports_json: bool = False,
        version: str = "1.0"
    ):
        self.provider = provider
        self.model_id = model_id
        self.name = name
        self.max_tokens = max_tokens
        self.cost_per_1k_tokens = cost_per_1k_tokens
        self.supports_streaming = supports_streaming
        self.supports_json = supports_json
        self.version = version


class LLMService:
    """Unified LLM façade with provider abstraction and usage tracking."""

    EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    PHONE_RE = re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b")
    ID_RE = re.compile(r"\b(?:MRN|PID|Patient ID|patient id)\s*[:#-]?\s*[\w-]+\b", re.I)

    def __init__(self):
        self.model_registry = LLMModelRegistryService()
        self.usage_tracker = LLMUsageTrackingService()
        self.template_service = LLMPromptTemplateService()
        
        # Initialize default models
        self._default_models = {
            LLMProvider.OPENAI: LLMModel(
                provider=LLMProvider.OPENAI,
                model_id="gpt-4",
                name="GPT-4",
                max_tokens=8192,
                cost_per_1k_tokens=0.03,
                supports_streaming=True,
                supports_json=True
            ),
            LLMProvider.ANTHROPIC: LLMModel(
                provider=LLMProvider.ANTHROPIC,
                model_id="claude-3-sonnet-20240229",
                name="Claude 3 Sonnet",
                max_tokens=200000,
                cost_per_1k_tokens=0.015,
                supports_streaming=True,
                supports_json=True
            ),
            LLMProvider.OLLAMA: LLMModel(
                provider=LLMProvider.OLLAMA,
                model_id="llama3",
                name="Llama 3",
                max_tokens=4096,
                cost_per_1k_tokens=0.0,
                supports_streaming=True,
                supports_json=False
            )
        }

    @classmethod
    def scrub_pii(cls, text: str) -> str:
        """Remove PII from text."""
        if not text:
            return text
        scrubbed = cls.EMAIL_RE.sub("[email]", text)
        scrubbed = cls.PHONE_RE.sub("[phone]", scrubbed)
        scrubbed = cls.ID_RE.sub("[identifier]", scrubbed)
        return scrubbed

    def get_provider_client(self, provider: LLMProvider, model: LLMModel) -> BaseAIProvider:
        """Get provider client for the specified provider and model."""
        if provider == LLMProvider.OPENAI:
            return OpenAIProvider(model)
        elif provider == LLMProvider.ANTHROPIC:
            return AnthropicProvider(model)
        elif provider == LLMProvider.OLLAMA:
            from services.ai_provider import OllamaProvider
            return OllamaProvider()
        else:
            from services.ai_provider import LocalHeuristicProvider
            return LocalHeuristicProvider()

    async def generate_completion(
        self,
        prompt: str,
        provider: LLMProvider = LLMProvider.OPENAI,
        model_id: str = None,
        temperature: float = 0.7,
        max_tokens: int = None,
        context: str = None,
        template_id: str = None,
        template_vars: Dict[str, Any] = None,
        user_id: str = None,
        organization_id: str = None
    ) -> Dict[str, Any]:
        """Generate LLM completion with usage tracking."""
        try:
            app_logger.info(f"LLMService: Generating completion with {provider.value}")
            
            # Get model
            if model_id:
                model = self.model_registry.get_model(model_id)
            else:
                model = self._default_models.get(provider, self._default_models[LLMProvider.OPENAI])
            
            # Apply template if specified
            if template_id:
                template = self.template_service.get_template(template_id)
                prompt = self.template_service.apply_template(template, prompt, template_vars or {})
            
            # Scrub PII
            safe_prompt = self.scrub_pii(prompt)
            safe_context = self.scrub_pii(context) if context else None
            
            # Get provider client
            client = self.get_provider_client(provider, model)
            
            # Generate completion
            start_time = datetime.utcnow()
            response = await client.generate_completion(
                prompt=safe_prompt,
                context=safe_context,
                temperature=temperature,
                max_tokens=max_tokens or model.max_tokens
            )
            end_time = datetime.utcnow()
            
            # Track usage
            if user_id and organization_id:
                await self.usage_tracker.track_usage(
                    user_id=user_id,
                    organization_id=organization_id,
                    provider=provider.value,
                    model_id=model.model_id,
                    prompt_tokens=response.get("prompt_tokens", 0),
                    completion_tokens=response.get("completion_tokens", 0),
                    cost=self._calculate_cost(
                        provider, 
                        response.get("prompt_tokens", 0),
                        response.get("completion_tokens", 0)
                    )
                )
            
            return {
                "content": response.get("content", ""),
                "model": model.model_id,
                "provider": provider.value,
                "usage": {
                    "prompt_tokens": response.get("prompt_tokens", 0),
                    "completion_tokens": response.get("completion_tokens", 0),
                    "total_tokens": response.get("total_tokens", 0)
                },
                "cost": self._calculate_cost(
                    provider,
                    response.get("prompt_tokens", 0),
                    response.get("completion_tokens", 0)
                )
            }
            
        except Exception as e:
            error_logger.error(f"LLMService: Completion generation failed: {str(e)}", exc_info=True)
            raise

    async def generate_form(
        self,
        prompt: str,
        current_form: dict[str, Any] | None = None,
        provider: LLMProvider = LLMProvider.OPENAI,
        user_id: str = None,
        organization_id: str = None
    ) -> Dict[str, Any]:
        """Generate form structure from natural language description."""
        app_logger.info("LLMService: Generating form from prompt")
        
        # Use form generation template
        template_vars = {"current_form": json.dumps(current_form or {}, indent=2)}
        
        response = await self.generate_completion(
            prompt=prompt,
            provider=provider,
            template_id="form_generation",
            template_vars=template_vars,
            user_id=user_id,
            organization_id=organization_id
        )
        
        # Parse form structure from response
        try:
            form_structure = json.loads(response["content"])
            return {
                "form_structure": form_structure,
                "original_prompt": prompt,
                "provider": provider.value,
                "usage": response["usage"],
                "cost": response["cost"]
            }
        except json.JSONDecodeError:
            # Fallback to AI service if JSON parsing fails
            safe_prompt = self.scrub_pii(prompt)
            safe_form = current_form or {}
            return AIService.generate_form(safe_prompt, safe_form)

    async def analyze_form_responses(
        self,
        responses: List[Dict[str, Any]],
        analysis_prompt: str,
        provider: LLMProvider = LLMProvider.OPENAI,
        user_id: str = None,
        organization_id: str = None
    ) -> Dict[str, Any]:
        """Analyze form responses using LLM."""
        app_logger.info("LLMService: Analyzing form responses")
        
        # Prepare responses data
        responses_text = json.dumps(responses, indent=2)
        
        # Use analysis template
        template_vars = {"responses": responses_text}
        
        response = await self.generate_completion(
            prompt=analysis_prompt,
            provider=provider,
            template_id="response_analysis",
            template_vars=template_vars,
            user_id=user_id,
            organization_id=organization_id
        )
        
        return {
            "analysis": response["content"],
            "responses_count": len(responses),
            "provider": provider.value,
            "usage": response["usage"],
            "cost": response["cost"]
        }

    async def suggest_dashboard_filters(
        self,
        natural_language_query: str,
        dashboard_context: Dict[str, Any],
        provider: LLMProvider = LLMProvider.OPENAI,
        user_id: str = None,
        organization_id: str = None
    ) -> Dict[str, Any]:
        """Convert natural language query to dashboard filters."""
        app_logger.info("LLMService: Converting natural language to dashboard filters")
        
        # Use dashboard query template
        template_vars = {"dashboard_context": json.dumps(dashboard_context, indent=2)}
        
        response = await self.generate_completion(
            prompt=natural_language_query,
            provider=provider,
            template_id="dashboard_query",
            template_vars=template_vars,
            user_id=user_id,
            organization_id=organization_id
        )
        
        # Parse filters from response
        try:
            filters = json.loads(response["content"])
            return {
                "filters": filters,
                "original_query": natural_language_query,
                "provider": provider.value,
                "usage": response["usage"],
                "cost": response["cost"]
            }
        except json.JSONDecodeError:
            return {
                "filters": [],
                "original_query": natural_language_query,
                "provider": provider.value,
                "usage": response["usage"],
                "cost": response["cost"],
                "error": "Failed to parse filters from response"
            }

    async def get_form_suggestions(
        self,
        current_form: dict[str, Any],
        provider: LLMProvider = LLMProvider.OPENAI,
        user_id: str = None,
        organization_id: str = None
    ) -> Dict[str, Any]:
        """Get AI suggestions for form improvements."""
        app_logger.info("LLMService: Getting form suggestions")
        
        # Use form suggestions template
        template_vars = {"current_form": json.dumps(current_form, indent=2)}
        
        response = await self.generate_completion(
            prompt="Analyze this form and suggest improvements",
            provider=provider,
            template_id="form_suggestions",
            template_vars=template_vars,
            user_id=user_id,
            organization_id=organization_id
        )
        
        return {
            "suggestions": response["content"],
            "provider": provider.value,
            "usage": response["usage"],
            "cost": response["cost"]
        }

    def _calculate_cost(
        self,
        provider: LLMProvider,
        prompt_tokens: int,
        completion_tokens: int
    ) -> float:
        """Calculate cost for token usage."""
        model = self._default_models.get(provider, self._default_models[LLMProvider.OPENAI])
        total_tokens = prompt_tokens + completion_tokens
        return (total_tokens / 1000) * model.cost_per_1k_tokens

    # Legacy method compatibility
    @classmethod
    def generate_form(cls, prompt: str, current_form: dict[str, Any] | None = None):
        """Legacy method - use async version instead."""
        app_logger.info("LLMService: generating form from prompt (legacy)")
        safe_prompt = cls.scrub_pii(prompt)
        safe_form = current_form or {}
        return AIService.generate_form(safe_prompt, safe_form)

    @classmethod
    def generate_text(cls, prompt: str, context: str | None = None):
        """Legacy method - use async version instead."""
        app_logger.info("LLMService: generating text from prompt (legacy)")
        safe_prompt = cls.scrub_pii(prompt)
        safe_context = cls.scrub_pii(context) if context else None
        provider = AIService.provider()
        if safe_context:
            return provider.summarize(safe_prompt, safe_context)
        return provider.summarize(safe_prompt)

    @classmethod
    def suggest_for_form(cls, current_form: dict[str, Any]):
        """Legacy method - use async version instead."""
        return AIService.get_suggestions(current_form)

    @classmethod
    def validate_form(cls, form_data: dict[str, Any]):
        """Legacy method - use async version instead."""
        return AIService.analyze_form(form_data)


class OpenAIProvider(BaseAIProvider):
    """OpenAI API provider implementation."""
    
    def __init__(self, model: LLMModel):
        self.model = model
        self.api_key = None  # Will be loaded from config
        self.base_url = "https://api.openai.com/v1"
    
    async def generate_completion(
        self,
        prompt: str,
        context: str = None,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> Dict[str, Any]:
        """Generate completion using OpenAI API."""
        import aiohttp
        import os
        
        if not self.api_key:
            self.api_key = os.getenv("OPENAI_API_KEY")
        
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        messages = [{"role": "user", "content": prompt}]
        if context:
            messages.insert(0, {"role": "system", "content": context})
        
        payload = {
            "model": self.model.model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"OpenAI API error: {response.status} - {error_text}")
                
                data = await response.json()
                choice = data["choices"][0]
                message = choice["message"]
                usage = data.get("usage", {})
                
                return {
                    "content": message["content"],
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0)
                }


class AnthropicProvider(BaseAIProvider):
    """Anthropic Claude API provider implementation."""
    
    def __init__(self, model: LLMModel):
        self.model = model
        self.api_key = None  # Will be loaded from config
        self.base_url = "https://api.anthropic.com"
    
    async def generate_completion(
        self,
        prompt: str,
        context: str = None,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> Dict[str, Any]:
        """Generate completion using Anthropic API."""
        import aiohttp
        import os
        
        if not self.api_key:
            self.api_key = os.getenv("ANTHROPIC_API_KEY")
        
        if not self.api_key:
            raise ValueError("Anthropic API key not configured")
        
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        # Combine context and prompt
        if context:
            full_prompt = f"{context}\n\n{prompt}"
        else:
            full_prompt = prompt
        
        payload = {
            "model": self.model.model_id,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": full_prompt}]
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Anthropic API error: {response.status} - {error_text}")
                
                data = await response.json()
                content = data["content"][0]["text"]
                usage = data.get("usage", {})
                
                return {
                    "content": content,
                    "prompt_tokens": usage.get("input_tokens", 0),
                    "completion_tokens": usage.get("output_tokens", 0),
                    "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                }
