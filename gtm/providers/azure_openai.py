"""Azure OpenAI provider.

Chat-completions call to an Azure OpenAI deployment. Plain deployments do NOT
browse the web; set web_search=True only when the deployment has grounding/Bing.
Best used for deterministic tasks (scoring, dedup, formatting) unless grounded.
"""

from __future__ import annotations

import requests

from .base import BaseProvider, ProviderResponse, extract_urls


class AzureOpenAIProvider(BaseProvider):
    def __init__(self, name: str, endpoint: str, api_key: str, deployment: str,
                 api_version: str = "2024-08-01-preview", web_search: bool = False,
                 timeout: int = 300):
        self.name = name
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.deployment = deployment
        self.api_version = api_version
        self.web_search = web_search
        self.timeout = timeout

    def send(self, prompt: str, web_search: bool | None = None) -> ProviderResponse:
        url = (f"{self.endpoint}/openai/deployments/{self.deployment}"
               f"/chat/completions?api-version={self.api_version}")
        resp = requests.post(
            url,
            headers={"api-key": self.api_key, "Content-Type": "application/json"},
            json={
                "messages": [
                    {"role": "system", "content": "Follow the user's instructions exactly. "
                                                  "Cite a source URL for every factual claim. "
                                                  "If a claim is unverifiable, mark it UNVERIFIED. "
                                                  "Never invent facts."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        text = ""
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            text = str(data)
        return ProviderResponse(text=text, sources=extract_urls(text), raw=data)
