"""Record/replay analyzer harness for offline fusion tests (21-12, layer 3).

Makes the whole vision layer testable without API credits (21-RESEARCH.md §8
layer 3 / 21-VALIDATION.md Wave 0): real Claude structured-output responses
are recorded ONCE to ``tests/fixtures/replay/{sha256}.json`` and replayed
deterministically forever after.

- **Replay mode (default):** responses are looked up by the SHA256 of
  ``(model, pass_type, prompt text, image count)``. An unknown key raises
  ``KeyError`` — test determinism demands that a prompt drift is loud, never
  silently answered.
- **Record mode (developer-invoked ONLY):** activated by the
  ``REPLAY_RECORD=1`` environment variable (or an explicit
  ``record=True``); wraps the real ``analyze_drawing`` once and writes the
  fixture. Never active in CI (threat model: replay fixture poisoning —
  fixtures are repo-committed test data).

``ReplayAnalyzer`` is callable with the ``analyze_drawing`` signature, so it
plugs straight into the existing injection seam::

    pipeline = TakeoffPipeline(analyzer=ReplayAnalyzer("tests/fixtures/replay"))
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable, Optional

# Environment variable gating record mode. Fixtures are recorded by a
# developer running the suite with REPLAY_RECORD=1 and real API credentials;
# CI never sets it, so CI can never spend credits or rewrite fixtures.
REPLAY_RECORD_ENV = "REPLAY_RECORD"


class ReplayAnalyzer:
    """Record/replay stand-in for ``claude_analyzer.analyze_drawing``.

    Args:
        fixture_dir:   Directory holding ``{sha256}.json`` recorded responses
                       (canonically ``tests/fixtures/replay/``).
        record:        Force record mode (developer use). Record mode is also
                       enabled when the ``REPLAY_RECORD=1`` env var is set.
        real_analyzer: The real analyzer wrapped in record mode. Defaults to
                       ``claude_analyzer.analyze_drawing`` (imported lazily,
                       ONLY when a recording is actually made).
    """

    def __init__(
        self,
        fixture_dir,
        record: bool = False,
        real_analyzer: Optional[Callable] = None,
    ) -> None:
        self.fixture_dir = Path(fixture_dir)
        self.record = bool(record) or os.environ.get(REPLAY_RECORD_ENV) == "1"
        self._real = real_analyzer

    # ── Key derivation ────────────────────────────────────────────────────

    @staticmethod
    def request_key(model: str, pass_type: str, prompt_text: str, image_count: int) -> str:
        """SHA256 fixture key over ``(model, pass_type, prompt, image count)``."""
        payload = json.dumps(
            {
                "model": model,
                "pass_type": pass_type,
                "prompt": prompt_text,
                "image_count": int(image_count),
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def key_for(
        self,
        sheet_name: str = "",
        pass_type: str = "measure",
        model_override: Optional[str] = None,
        sheet_type: Optional[str] = None,
        user_hint: Optional[str] = None,
        output_schema: Optional[dict] = None,
        images: Optional[list] = None,
    ) -> str:
        """The fixture key a :meth:`__call__` with these arguments resolves to."""
        model = self._resolve_model(
            sheet_name, pass_type, sheet_type, model_override, output_schema
        )
        prompt = self._prompt_text(sheet_name, pass_type, sheet_type, user_hint)
        image_count = len(images) if images else 1
        return self.request_key(model, pass_type, prompt, image_count)

    def _resolve_model(
        self,
        sheet_name: str,
        pass_type: str,
        sheet_type: Optional[str],
        model_override: Optional[str],
        output_schema: Optional[dict],
    ) -> str:
        """Mirror analyze_drawing's model selection (deterministic per env).

        conftest pins the CLAUDE_MODEL_* env slugs, so this resolves to the
        same value at record time and at replay time under any test order.
        """
        if model_override:
            return model_override
        # NOTE: results from the lazy imports below are validated as real
        # non-empty strings — several test modules stub claude_analyzer /
        # sheet_pass_matrix with MagicMock in sys.modules, and a MagicMock
        # return value must degrade to the deterministic fallback, never
        # poison the SHA256 key derivation.
        if output_schema is not None:
            try:
                from bobbytailor.pipeline.sheet_pass_matrix import pick_model_for_pass

                routing_pass = "semantic" if pass_type == "symbol_gallery" else pass_type
                model = pick_model_for_pass(sheet_type or "", routing_pass, sheet_name)
                if isinstance(model, str) and model:
                    return model
            except Exception:  # noqa: BLE001 — routing unavailable → heuristic
                pass
        try:
            from bobbytailor.vision.claude_analyzer import _pick_model

            model = _pick_model(sheet_name, pass_type, sheet_type=sheet_type)
            if isinstance(model, str) and model:
                return model
        except Exception:  # noqa: BLE001 — analyzer unimportable (no API key)
            pass
        return "unrouted"

    @staticmethod
    def _prompt_text(
        sheet_name: str,
        pass_type: str,
        sheet_type: Optional[str],
        user_hint: Optional[str],
    ) -> str:
        """The exact user-message text the real analyzer would send."""
        try:
            from bobbytailor.vision.claude_analyzer import _build_user_message

            prompt = _build_user_message(sheet_name, pass_type, sheet_type, user_hint)
            if isinstance(prompt, str):  # guard against sys.modules mock stubs
                return prompt
        except Exception:  # noqa: BLE001 — fallback stays deterministic
            pass
        parts = []
        if sheet_name:
            parts.append("Sheet name: %s" % sheet_name)
        if user_hint:
            parts.append(user_hint)
        parts.append("Analyze this drawing and return the JSON.")
        return "\n\n".join(parts)

    # ── analyze_drawing-compatible call ───────────────────────────────────

    def __call__(
        self,
        screenshot_path: str,
        sheet_name: str = "",
        pass_type: str = "measure",
        model_override: Optional[str] = None,
        sheet_type: Optional[str] = None,
        user_hint: Optional[str] = None,
        output_schema: Optional[dict] = None,
        images: Optional[list] = None,
    ) -> dict:
        key = self.key_for(
            sheet_name=sheet_name,
            pass_type=pass_type,
            model_override=model_override,
            sheet_type=sheet_type,
            user_hint=user_hint,
            output_schema=output_schema,
            images=images,
        )
        fixture_path = self.fixture_dir / ("%s.json" % key)

        if self.record:
            real = self._real
            if real is None:
                from bobbytailor.vision.claude_analyzer import analyze_drawing as real  # lazy — record only

            response = real(
                screenshot_path,
                sheet_name=sheet_name,
                pass_type=pass_type,
                model_override=model_override,
                sheet_type=sheet_type,
                user_hint=user_hint,
                output_schema=output_schema,
                images=images,
            )
            self.fixture_dir.mkdir(parents=True, exist_ok=True)
            fixture_path.write_text(
                json.dumps(
                    {
                        "request": {
                            "model": self._resolve_model(
                                sheet_name, pass_type, sheet_type, model_override, output_schema
                            ),
                            "pass_type": pass_type,
                            "sheet_name": sheet_name,
                            "sheet_type": sheet_type,
                            "prompt": self._prompt_text(
                                sheet_name, pass_type, sheet_type, user_hint
                            ),
                            "image_count": len(images) if images else 1,
                        },
                        "response": response,
                    },
                    indent=2,
                    sort_keys=False,
                    default=str,
                ),
                encoding="utf-8",
            )
            return response

        if not fixture_path.exists():
            raise KeyError(
                "ReplayAnalyzer: no recorded fixture for request "
                "(pass_type=%r, sheet_name=%r, key=%s) in %s — run once with "
                "%s=1 and real credentials to record it."
                % (pass_type, sheet_name, key, self.fixture_dir, REPLAY_RECORD_ENV)
            )
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "response" in data:
            return data["response"]
        return data
