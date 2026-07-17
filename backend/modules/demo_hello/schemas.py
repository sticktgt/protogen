from __future__ import annotations

from pydantic import BaseModel


class MessageUpdate(BaseModel):
    workspace_id: str
    message: str
