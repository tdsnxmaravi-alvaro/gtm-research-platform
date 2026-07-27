"""LARA provider — TD SYNNEX internal AI with built-in web search.

Sends the built prompt as the user message to a thin generalist LARA assistant
(research or enrichment), so the instructions live in our prompt-builder, not in
the agent config.
"""

from __future__ import annotations

import base64
import json
import re

import requests

from .base import BaseProvider, ProviderResponse, extract_urls

# LARA streams tool activity markers like [[LARA_TOOL_ACTIVITY:<base64-json>]]
_TOOL_ACTIVITY_RE = re.compile(r"\[\[LARA_TOOL_ACTIVITY:([A-Za-z0-9+/=_-]+)\]\]")


def _sources_from_tool_activity(text: str) -> list[str]:
    """Decode LARA web-search/website tool markers to recover visited URLs."""
    urls: list[str] = []
    for token in _TOOL_ACTIVITY_RE.findall(text or ""):
        try:
            pad = token + "=" * (-len(token) % 4)
            data = json.loads(base64.b64decode(pad).decode("utf-8", "ignore"))
        except (ValueError, json.JSONDecodeError):
            continue
        url = data.get("url")
        if url and url not in urls:
            urls.append(url)
    return urls


class LaraProvider(BaseProvider):
    def __init__(self, name: str, api_url: str, api_key: str, assistant_id: str,
                 timeout: int = 300, web_search: bool = True):
        self.name = name
        self.api_url = api_url
        self.api_key = api_key
        self.assistant_id = assistant_id
        self.timeout = timeout
        self.web_search = web_search

    def send(self, prompt: str, web_search: bool | None = None) -> ProviderResponse:
        resp = requests.post(
            self.api_url,
            headers={
                "accept": "application/json",
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            json={
                "assistantId": self.assistant_id,
                "prompt": prompt,
                "responseFormat": "markdown",
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        text = ""
        for key in ("response", "content", "message", "answer", "text", "result"):
            if data.get(key):
                text = str(data[key])
                break
        else:
            text = str(data)

        sources = _sources_from_tool_activity(text) + [
            u for u in extract_urls(text) if u not in _sources_from_tool_activity(text)
        ]
        return ProviderResponse(text=text, sources=sources, raw=data)
