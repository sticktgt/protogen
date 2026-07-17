from __future__ import annotations

from pydantic import BaseModel


class NoteSaveRequest(BaseModel):
    workspace_id: str
    note: str
