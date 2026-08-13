"""Build a provider instance from an LLMProvider config (secrets from env vars)."""

from __future__ import annotations

import os

from ..config.schema import LLMProvider, ProviderType
from .base import BaseProvider
from .lara import LaraProvider
from .azure_openai import AzureOpenAIProvider
from .azure_foundry import AzureFoundryProvider
from .manual import ManualProvider


def _env(name: str | None, default_name: str | None = None) -> str | None:
    """Read an env var by the config-supplied name, else a default name."""
    if name and os.getenv(name):
        return os.getenv(name)
    if default_name:
        return os.getenv(default_name)
    return None


def build_provider(cfg: LLMProvider, load_env: bool = True) -> BaseProvider:
    """Instantiate a provider, resolving secrets from environment variables."""
    if load_env:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

    if cfg.type == ProviderType.manual:
        return ManualProvider(name=cfg.name)

    if cfg.type == ProviderType.lara:
        api_url = _env(cfg.endpoint_env, "LARA_API_URL")
        api_key = _env(cfg.api_key_env, "LARA_RESEARCH_API_KEY") or os.getenv("LARA_API_KEY")
        assistant = _env(cfg.assistant_id_env, "LARA_RESEARCH_ASSISTANT_ID")
        missing = [k for k, v in (("api_url", api_url), ("api_key", api_key),
                                  ("assistant_id", assistant)) if not v]
        if missing:
            raise ValueError(f"LARA provider '{cfg.name}' missing env values: {missing}")
        return LaraProvider(cfg.name, api_url, api_key, assistant, web_search=cfg.web_search)

    if cfg.type == ProviderType.azure_openai:
        endpoint = cfg.endpoint_url or _env(cfg.endpoint_env, "AZURE_OPENAI_ENDPOINT")
        api_key = _env(cfg.api_key_env, "AZURE_OPENAI_API_KEY")
        deployment = cfg.model or os.getenv("AZURE_OPENAI_DEPLOYMENT")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
        missing = [k for k, v in (("endpoint", endpoint), ("api_key", api_key),
                                  ("deployment", deployment)) if not v]
        if missing:
            raise ValueError(f"Azure provider '{cfg.name}' missing env values: {missing}")
        return AzureOpenAIProvider(cfg.name, endpoint, api_key, deployment,
                                   api_version=api_version, web_search=cfg.web_search)

    if cfg.type == ProviderType.azure_foundry:
        endpoint = cfg.endpoint_url or _env(cfg.endpoint_env, "AZURE_FOUNDRY_ENDPOINT")
        api_key = _env(cfg.api_key_env, "AZURE_FOUNDRY_API_KEY")
        deployment = cfg.model or os.getenv("AZURE_FOUNDRY_DEPLOYMENT")
        missing = [k for k, v in (("endpoint", endpoint), ("api_key", api_key),
                                  ("deployment", deployment)) if not v]
        if missing:
            raise ValueError(f"Azure Foundry provider '{cfg.name}' missing env values: {missing}")
        return AzureFoundryProvider(cfg.name, endpoint, api_key, deployment,
                                    web_search=cfg.web_search)

    raise ValueError(f"Unknown provider type: {cfg.type}")
