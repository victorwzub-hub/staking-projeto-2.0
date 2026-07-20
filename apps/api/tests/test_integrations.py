from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from pharma_api.application.integrations.connectors import (
    DeterministicERPConnector,
    ExtractionRequest,
)
from pharma_api.application.integrations.quality import QualityContext, QualityEngine
from pharma_api.application.integrations.service import sanitize_connector_configuration
from pharma_api.core.errors import AppError
from pharma_api.domain.integrations.state_machine import (
    ProcessingState,
    allowed_transitions,
    assert_transition,
)
from pharma_api.infrastructure.object_storage import (
    FilesystemObjectStorage,
    ObjectAlreadyExistsError,
    validate_object_key,
)
from pharma_api.main import create_app


def test_processing_state_machine_rejects_skips_and_terminal_restarts() -> None:
    assert ProcessingState.CONNECTING in allowed_transitions(ProcessingState.QUEUED)
    assert_transition(ProcessingState.QUEUED, ProcessingState.CONNECTING)
    assert_transition(ProcessingState.LOADING, ProcessingState.COMPLETED)
    with pytest.raises(ValueError, match="Invalid processing transition"):
        assert_transition(ProcessingState.CREATED, ProcessingState.LOADING)
    with pytest.raises(ValueError, match="Invalid processing transition"):
        assert_transition(ProcessingState.COMPLETED, ProcessingState.QUEUED)


def test_deterministic_connector_repeats_exact_envelopes() -> None:
    connector = DeterministicERPConnector()
    request = ExtractionRequest(
        tenant_id=str(uuid4()),
        company_id=str(uuid4()),
        branch_id=str(uuid4()),
        entities=("product", "sale"),
        mode="incremental",
        start_at=None,
        end_at=datetime(2026, 7, 17, 12, tzinfo=UTC),
        page_size=2,
        timeout_seconds=30,
        configuration={"records": 3, "seed": "repeatable"},
    )
    first = list(connector.extract(request))
    second = list(connector.extract(request))
    assert first == second
    assert len(first) == 6
    assert [item.page for item in first] == [1, 1, 2, 2, 3, 3]
    assert len({item.content_hash for item in first}) == 6


def test_quality_engine_blocks_structural_errors_without_executing_code() -> None:
    findings = QualityEngine().evaluate_record(
        "sale",
        "sale-1",
        {
            "sale_number": "sale-1",
            "occurred_at": "not-a-date",
            "net_total": "10.00",
            "items": [],
            "payments": [{"method": "cash", "amount": "8.00"}],
        },
        QualityContext(branch_exists=True),
    )
    finding_types = {finding.rule_type.value for finding in findings}
    assert {"invalid_date", "sale_without_item", "payment_mismatch"} <= finding_types
    assert any(finding.blocks_loading for finding in findings)


def test_connector_configuration_rejects_inline_secrets_and_unsupported_values() -> None:
    assert sanitize_connector_configuration({"records": 5, "nested": {"seed": "safe"}}) == {
        "records": 5,
        "nested": {"seed": "safe"},
    }
    with pytest.raises(AppError) as secret_error:
        sanitize_connector_configuration({"api_token": "do-not-store"})
    assert secret_error.value.code == "inline_secret_forbidden"
    with pytest.raises(AppError) as type_error:
        sanitize_connector_configuration({"callback": object()})
    assert type_error.value.code == "invalid_configuration"


def test_filesystem_landing_is_immutable_streamable_and_path_safe(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(tmp_path, "landing")
    source = tmp_path / "source.ndjson"
    source.write_bytes(b'{"id":1}\n')
    stored = storage.put_file(
        source,
        key="tenant/source/hash/payload.ndjson",
        content_type="application/x-ndjson",
        metadata={"sha256": "abc"},
    )
    assert stored.size_bytes == source.stat().st_size
    assert b"".join(storage.iter_object(stored.key, chunk_size=3)) == source.read_bytes()
    with pytest.raises(ObjectAlreadyExistsError):
        storage.put_file(
            source,
            key=stored.key,
            content_type=stored.content_type,
            metadata={},
        )
    for unsafe in ("../secret", "/absolute", r"tenant\escape"):
        with pytest.raises(ValueError, match="Unsafe object key"):
            validate_object_key(unsafe)


def test_openapi_publishes_operational_integration_contracts() -> None:
    schema = create_app().openapi()
    paths = schema["paths"]
    required = {
        "/api/v1/integrations/connectors",
        "/api/v1/integrations/sources",
        "/api/v1/integrations/sources/{source_id}/sync",
        "/api/v1/integrations/sources/{source_id}/upload",
        "/api/v1/integrations/batches",
        "/api/v1/integrations/batches/{batch_id}/quality",
        "/api/v1/integrations/batches/{batch_id}/lineage",
        "/api/v1/integrations/canonical/products",
    }
    assert required <= set(paths)
    upload = paths["/api/v1/integrations/sources/{source_id}/upload"]["post"]
    assert "multipart/form-data" in upload["requestBody"]["content"]
