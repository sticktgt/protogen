from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.ui_schema.agent_tool_payloads import decode_json_argument


class CleanupCandidatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(min_length=1, description="Краткая категория проблемы на русском языке")
    message: str = Field(min_length=1, description="Проверяемое описание проблемы на русском языке")
    recommendation: str = Field(min_length=1, description="Рекомендация аналитику на русском языке")
    requirement_ids: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list, min_length=1)

    @field_validator("message", "recommendation")
    @classmethod
    def require_russian_text(cls, value: str, info) -> str:
        text = str(value or "").strip()
        if not re.search(r"[А-Яа-яЁё]", text):
            raise ValueError(f"{info.field_name} должно быть сформулировано на русском языке")
        return text

    @field_validator("requirement_ids", "targets", mode="before")
    @classmethod
    def normalize_string_list(cls, value: Any, info) -> Any:
        if value is None:
            return []
        decoded = decode_json_argument(value, label=info.field_name)
        return decoded


class CleanupReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, description="Краткий итог проверки на русском языке")
    cleanup_candidates: list[CleanupCandidatePayload] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def require_russian_summary(cls, value: str) -> str:
        text = str(value or "").strip()
        if not re.search(r"[А-Яа-яЁё]", text):
            raise ValueError("summary должен быть сформулирован на русском языке")
        return text

    @field_validator("cleanup_candidates", mode="before")
    @classmethod
    def normalize_candidates(cls, value: Any) -> Any:
        if value is None:
            return []
        return decode_json_argument(value, label="cleanup_candidates")
