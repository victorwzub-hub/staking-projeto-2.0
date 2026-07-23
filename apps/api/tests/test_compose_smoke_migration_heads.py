from __future__ import annotations

import re
from pathlib import Path

_SCRIPT = Path(__file__).parents[3] / "scripts" / "smoke-test-compose.sh"
_REVISION_LITERAL = re.compile(r"\b\d{8}_\d{4}\b")


def _migration_gate() -> str:
    source = _SCRIPT.read_text(encoding="utf-8")
    start = source.index("# Verify migrations can be executed repeatedly under the advisory lock.")
    end = source.index("# Prove the worker consumes a real Redis-backed Dramatiq task.")
    return source[start:end]


def test_compose_smoke_discovers_packaged_alembic_heads_dynamically() -> None:
    gate = _migration_gate()

    assert 'Config("/app/alembic.ini")' in gate
    assert "ScriptDirectory.from_config(config).get_heads()" in gate
    assert "SELECT version_num FROM alembic_version ORDER BY version_num" in gate
    assert _REVISION_LITERAL.search(gate) is None


def test_compose_smoke_compares_normalized_revision_sets() -> None:
    source = _SCRIPT.read_text(encoding="utf-8")
    gate = _migration_gate()

    assert "normalize_revision_set()" in source
    assert "LC_ALL=C sort -u" in source
    assert '[[ "$database_migration_heads" == "$expected_migration_heads" ]]' in gate
    assert "Alembic head mismatch." in gate
