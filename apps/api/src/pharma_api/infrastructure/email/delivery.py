from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from pharma_api.core.config import Settings, get_settings


@dataclass(frozen=True, slots=True)
class EmailMessage:
    recipient: str
    subject: str
    template: str
    variables: dict[str, str]


def deliver_development_email(message: EmailMessage, settings: Settings | None = None) -> Path:
    config = settings or get_settings()
    spool = config.email_spool_directory
    spool.mkdir(parents=True, exist_ok=True)
    target = spool / f"{uuid4()}.json"
    target.write_text(json.dumps(asdict(message), ensure_ascii=False, indent=2), encoding="utf-8")
    return target
