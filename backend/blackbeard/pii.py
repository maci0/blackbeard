"""PII redaction via Microsoft Presidio.

Supports multiple recognizer backends:
- "default" -- Presidio's built-in regex + deny-list recognizers
- "presidio-nlp" -- requires spaCy model (en_core_web_lg)
- "litellm" -- uses LiteLLM proxy for LLM-based PII detection
"""

from __future__ import annotations

import json
import logging
from typing import Any, ClassVar

from presidio_analyzer import AnalyzerEngine, EntityRecognizer, RecognizerResult
from presidio_anonymizer import AnonymizerEngine

logger = logging.getLogger(__name__)

_analyzer: AnalyzerEngine | None = None
_anonymizer: AnonymizerEngine | None = None

# Default PII entity types to detect when none are specified.
DEFAULT_ENTITIES: list[str] = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "US_SSN",
    "IP_ADDRESS",
    "IBAN_CODE",
    "LOCATION",
]


def _get_analyzer(config: dict[str, Any] | None = None) -> AnalyzerEngine:
    """Return (or create) a singleton AnalyzerEngine.

    On the ``"litellm"`` backend the LLM recognizer is added to the
    registry so that it participates in every ``analyze()`` call.
    """
    global _analyzer
    if _analyzer is not None:
        return _analyzer

    _analyzer = AnalyzerEngine()

    if config:
        backend = config.get("backend", "default")
        if backend == "litellm":
            _add_llm_recognizer(_analyzer, config)

    return _analyzer


def _get_anonymizer() -> AnonymizerEngine:
    """Return (or create) a singleton AnonymizerEngine."""
    global _anonymizer
    if _anonymizer is not None:
        return _anonymizer

    _anonymizer = AnonymizerEngine()
    return _anonymizer


def _add_llm_recognizer(
    analyzer: AnalyzerEngine,
    config: dict[str, Any],
) -> None:
    """Register an :class:`LLMPIIRecognizer` on *analyzer*."""
    from blackbeard.config import settings

    model = config.get("model", "ollama/gliner-pii")
    proxy_url = config.get("proxy_url") or settings.litellm_proxy_url
    master_key = settings.litellm_master_key.get_secret_value()
    recognizer = LLMPIIRecognizer(
        model=model, proxy_url=proxy_url, master_key=master_key
    )
    analyzer.registry.add_recognizer(recognizer)
    logger.info(
        "LLM PII recognizer added: model=%s",
        model,
        extra={"event": "llm_pii_recognizer_added", "model": model},
    )


# ---------------------------------------------------------------------------
# LLM-based recognizer
# ---------------------------------------------------------------------------


class LLMPIIRecognizer(EntityRecognizer):
    """Custom Presidio recognizer that detects PII via the LiteLLM proxy.

    The recognizer sends the text to a local or remote model (e.g.
    ``ollama/gliner-pii``) and parses structured JSON from the response
    into :class:`RecognizerResult` objects.
    """

    ENTITIES: ClassVar[list[str]] = [
        "PERSON",
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "LOCATION",
        "CREDIT_CARD",
        "US_SSN",
        "IP_ADDRESS",
    ]

    def __init__(
        self,
        model: str = "ollama/gliner-pii",
        proxy_url: str | None = None,
        master_key: str | None = None,
    ) -> None:
        self._model = model
        self._proxy_url = proxy_url
        self._master_key = master_key
        super().__init__(
            supported_entities=self.ENTITIES,
            name="LLM_PII",
            supported_language="en",
        )

    # EntityRecognizer protocol -------------------------------------------------

    def load(self) -> None:
        """No-op -- nothing to pre-load."""

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts: Any = None,
        regex_flags: int | None = None,
    ) -> list[RecognizerResult]:
        """Call the LLM to identify PII entities in *text*."""
        from blackbeard.http_client import get_sync_client

        proxy_url = self._proxy_url
        master_key = self._master_key

        if not proxy_url or not master_key:
            from blackbeard.config import settings

            proxy_url = proxy_url or settings.litellm_proxy_url
            master_key = master_key or settings.litellm_master_key.get_secret_value()

        prompt = (
            "Identify all PII (personally identifiable information) in the "
            "following text.  Return ONLY a JSON array of objects, each with "
            "'entity_type', 'start', 'end', 'score' fields.  "
            "Entity types: PERSON, EMAIL_ADDRESS, PHONE_NUMBER, LOCATION, "
            "CREDIT_CARD, US_SSN, IP_ADDRESS.\n\nText: " + text
        )

        try:
            client = get_sync_client("pii-llm", timeout=10)
            resp = client.post(
                f"{proxy_url}/v1/chat/completions",
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                },
                headers={
                    "Authorization": f"Bearer {master_key}",
                },
            )
            if resp.status_code != 200:
                logger.warning(
                    "LLM PII recognizer got HTTP %d from proxy",
                    resp.status_code,
                    extra={
                        "event": "llm_pii_http_error",
                        "status_code": resp.status_code,
                        "model": self._model,
                    },
                )
                return []

            content = resp.json()["choices"][0]["message"]["content"]
            items = json.loads(content)
            if not isinstance(items, list):
                return []

            # SECURITY: Validate each item returned by the LLM.
            # The LLM is an untrusted data source -- it could return
            # out-of-bounds positions (causing incorrect redaction or
            # crashes), disallowed entity types, or negative indices.
            text_len = len(text)
            allowed_types = frozenset(self.ENTITIES)
            results: list[RecognizerResult] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                entity_type = item.get("entity_type", "")
                start = item.get("start")
                end = item.get("end")
                score = item.get("score", 0.85)

                # Validate entity type is in the allowed set
                if entity_type not in allowed_types:
                    continue

                # Validate positions are integers within text bounds
                if not isinstance(start, int) or not isinstance(end, int):
                    continue
                if start < 0 or end < 0 or start >= end or end > text_len:
                    continue

                # Clamp score to [0, 1]
                try:
                    clamped_score = max(0.0, min(1.0, float(score)))
                except (TypeError, ValueError):
                    clamped_score = 0.85

                results.append(
                    RecognizerResult(
                        entity_type=entity_type,
                        start=start,
                        end=end,
                        score=clamped_score,
                    )
                )
            return results

        except Exception:
            logger.warning(
                "LLM PII recognizer failed -- returning empty results",
                exc_info=True,
                extra={"event": "llm_pii_recognizer_error", "model": self._model},
            )
            return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def redact_text(
    text: str,
    entities: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> str:
    """Redact PII from *text*.

    Args:
        text: Input text to redact.
        entities: PII entity types to detect (default: :data:`DEFAULT_ENTITIES`).
        config: PII configuration dict (from AgentPolicy or Crew spec).

    Returns:
        Text with PII replaced by ``<ENTITY_TYPE>`` placeholders.
    """
    if not text:
        return text

    analyzer = _get_analyzer(config)
    anonymizer = _get_anonymizer()

    target_entities = entities or DEFAULT_ENTITIES
    results = analyzer.analyze(text=text, entities=target_entities, language="en")

    if not results:
        return text

    anonymized = anonymizer.anonymize(text=text, analyzer_results=results)
    return anonymized.text


def redact_dict(
    data: dict[str, Any],
    entities: list[str] | None = None,
    config: dict[str, Any] | None = None,
    max_depth: int = 5,
) -> dict[str, Any]:
    """Recursively redact PII from string values in *data*.

    Non-string leaves (ints, floats, bools, None) are left untouched.
    Recursion stops at *max_depth* to prevent runaway traversal.
    """
    return _redact_value(data, entities=entities, config=config, depth=0, max_depth=max_depth)  # type: ignore[return-value]


def _redact_value(
    value: Any,
    *,
    entities: list[str] | None,
    config: dict[str, Any] | None,
    depth: int,
    max_depth: int,
) -> Any:
    """Walk a JSON-like structure, redacting all string leaves."""
    if depth >= max_depth:
        return value

    if isinstance(value, str):
        return redact_text(value, entities=entities, config=config)

    def recurse(v: Any) -> Any:
        return _redact_value(
            v, entities=entities, config=config, depth=depth + 1, max_depth=max_depth
        )

    if isinstance(value, dict):
        return {k: recurse(v) for k, v in value.items()}

    if isinstance(value, list):
        return [recurse(item) for item in value]

    return value


def reset_engines() -> None:
    """Reset singleton engines (useful for testing)."""
    global _analyzer, _anonymizer
    _analyzer = None
    _anonymizer = None
