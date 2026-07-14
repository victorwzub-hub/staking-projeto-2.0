from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ServiceResponse(BaseModel):
    service: str
    version: str
    status: Literal["ok"] = "ok"
    documentation_url: str | None
    health_url: str
