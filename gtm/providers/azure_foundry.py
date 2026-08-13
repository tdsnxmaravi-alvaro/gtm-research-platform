"""Azure AI Foundry provider (OpenAI v1 `responses` API).

Talks to a Foundry project's OpenAI-compatible endpoint
(`https://<project>.services.ai.azure.com/openai/v1`) using the `responses`
API and a Bearer key. When the deployment supports the `web_search` tool, it
browses and cites source URLs — so it can act as a full research ensemble member
alongside LARA. Kept requests-based (no extra SDK dependency).
"""

from __future__ import annotations

import requests

from .base import BaseProvider, ProviderResponse, extract_urls

_SYSTEM = ("Follow the user's instructions exactly. Cite a source URL for every "
           "factual claim. If a claim is unverifiable, mark it UNVERIFIED. Never "
           "invent facts.")


class AzureFoundryProvider(BaseProvider):
    def __init__(self, name: str, endpoint: str, api_key: str, deployment: str,
                 web_search: bool = False, timeout: int = 300):
        self.name = name
        # endpoint already ends with /openai/v1 for Foundry projects.
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.deployment = deployment
        self.web_search = web_search
        self.timeout = timeout

    def send(self, prompt: str, web_search: bool | None = None) -> ProviderResponse:
        use_search = self.web_search if web_search is None else web_search
        body: dict = {
            "model": self.deployment,
            "instructions": _SYSTEM,
            "input": prompt,
        }
        if use_search:
            body["tools"] = [{"type": "web_search"}]
        resp = requests.post(
            f"{self.endpoint}/responses",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            json=body,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        text = _extract_text(data)
        sources = extract_urls(text) + _annotation_urls(data)
        # de-dup while preserving order
        seen: list[str] = []
        for u in sources:
            if u not in seen:
                seen.append(u)
        return ProviderResponse(text=text, sources=seen, raw=data)


def _extract_text(data: dict) -> str:
    """Pull the assistant text out of a `responses` payload (SDK-free parsing)."""
    # SDK convenience field, present on some gateways.
    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"]
    parts: list[str] = []
    for item in data.get("output") or []:
        if item.get("type") != "message":
            continue
        for c in item.get("content") or []:
            if c.get("type") in ("output_text", "text") and c.get("text"):
                parts.append(c["text"])
    if parts:
        return "\n".join(parts)
    return str(data)


def _annotation_urls(data: dict) -> list[str]:
    """URLs surfaced by the web_search tool as message annotations."""
    urls: list[str] = []
    for item in data.get("output") or []:
        for c in item.get("content") or []:
            for a in c.get("annotations") or []:
                u = a.get("url")
                if u:
                    urls.append(u)
    return urls
