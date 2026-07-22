from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class KnowledgeBase:
    def __init__(self, data_path: Path | None = None) -> None:
        default_path = Path(__file__).resolve().parent.parent / "data" / "data_agent_context.json"
        self.data_path = data_path or default_path
        self._context: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        with self.data_path.open(encoding="utf-8") as handle:
            return json.load(handle)

    @property
    def context(self) -> dict[str, Any]:
        return self._context

    def summary(self) -> dict[str, Any]:
        return {
            "source": self._context["source"],
            "live_connection": False,
            "tables": self._context["tables"],
            "terminology": self._context["terminology"],
            "data_quality_warnings": self._context["data_quality_warnings"],
            "usage_note": self._context["usage_note"],
        }

    def prompt_context(self) -> str:
        return json.dumps(self._context, ensure_ascii=False, indent=2)

