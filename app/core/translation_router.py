from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import request, error


@dataclass(slots=True)
class TranslationConfig:
    provider: str
    base_url: str | None
    api_key: str | None
    model_name: str
    extra_headers: dict[str, str] | None = None


class TranslationRouter:
    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def translate(self, text: str, target_lang: str, cfg: TranslationConfig) -> str:
        if not text.strip() or cfg.provider == "none":
            return text
        cache_key = f"{cfg.provider}|{cfg.model_name}|{target_lang}|{text}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        out = self._translate_openai_compatible(text, target_lang, cfg)
        self._cache[cache_key] = out
        return out

    def test_connection(self, cfg: TranslationConfig) -> tuple[bool, str]:
        try:
            self._translate_openai_compatible("hello", "zh", cfg)
            return True, "OK"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def _translate_openai_compatible(self, text: str, target_lang: str, cfg: TranslationConfig) -> str:
        base = (cfg.base_url or "").rstrip("/")
        if not base:
            raise RuntimeError("API base URL is required.")
        endpoint = base + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if cfg.api_key:
            headers["Authorization"] = f"Bearer {cfg.api_key}"
        if cfg.extra_headers:
            headers.update(cfg.extra_headers)

        payload: dict[str, Any] = {
            "model": cfg.model_name,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": f"Translate subtitle text into {target_lang}. No explanation."},
                {"role": "user", "content": text},
            ],
        }

        req = request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=120) as resp:  # noqa: S310
                body = json.loads(resp.read().decode("utf-8", errors="replace"))
        except error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {message}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Connection failed: {exc}") from exc

        choices = body.get("choices", [])
        if not choices:
            raise RuntimeError("No choices returned from provider.")
        content = str(choices[0].get("message", {}).get("content", "")).strip()
        if not content:
            raise RuntimeError("Empty translation content.")
        return content

