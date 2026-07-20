#!/usr/bin/env python3
"""Generate the committed OpenAPI contract from the FastAPI application."""

from __future__ import annotations

import json
from pathlib import Path

from pharma_api.main import create_app

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "openapi" / "phase2-openapi.json"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = create_app().openapi()
    OUTPUT.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {OUTPUT.relative_to(ROOT)} with {len(document.get('paths', {}))} paths.")


if __name__ == "__main__":
    main()
