from __future__ import annotations

from app.providers.base import TranslationProvider, TranslationResult

# Tag comes from the shared language table so mock and real providers accept
# exactly the same set -- a language that works in mock mode must work for real.
from app.capabilities import require_language


class MockTranslationProvider(TranslationProvider):
    """Deterministic stand-in for IndicTrans2/NLLB-200."""

    def translate(self, text: str, target_lang: str, src_lang: str = "en") -> TranslationResult:
        tag = require_language(target_lang).code.upper()
        return TranslationResult(
            text=f"[{tag}] {text}",
            src_lang=src_lang,
            target_lang=target_lang,
        )
