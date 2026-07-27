"""Manual provider — no API call.

Used when research is run by pasting a prompt into an external LLM and uploading
the result. `send()` is intentionally unsupported; the runner routes manual
campaigns through the ingest parser instead.
"""

from __future__ import annotations

from .base import BaseProvider, ProviderResponse


class ManualProvider(BaseProvider):
    def __init__(self, name: str = "manual"):
        self.name = name
        self.web_search = False

    def send(self, prompt: str, web_search: bool | None = None) -> ProviderResponse:
        raise NotImplementedError(
            "ManualProvider does not auto-send. Run the prompt in your LLM and "
            "upload the result via the ingest step."
        )
