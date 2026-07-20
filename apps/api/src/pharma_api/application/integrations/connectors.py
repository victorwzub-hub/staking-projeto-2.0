from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid5


class ConnectorCapability(StrEnum):
    CONNECTION_TEST = "connection_test"
    DISCOVERY = "discovery"
    FULL_SYNC = "full_sync"
    INCREMENTAL_SYNC = "incremental_sync"
    PAGINATION = "pagination"
    CHECKPOINT = "checkpoint"
    COOPERATIVE_CANCEL = "cooperative_cancel"


class ConnectorErrorClass(StrEnum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    TRANSIENT = "transient"
    INVALID_RESPONSE = "invalid_response"
    CONFIGURATION = "configuration"
    CANCELLED = "cancelled"
    PERMANENT = "permanent"


class ConnectorError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        classification: ConnectorErrorClass,
        retryable: bool = False,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.classification = classification
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True, slots=True)
class ConnectorDescriptor:
    key: str
    name: str
    version: str
    schema_version: str
    capabilities: frozenset[ConnectorCapability]
    authentication_types: tuple[str, ...]
    supported_entities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConnectionTestResult:
    healthy: bool
    latency_ms: int
    message: str
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class DiscoveredResource:
    key: str
    label: str
    schema_version: str
    incremental: bool


@dataclass(frozen=True, slots=True)
class ConnectorCheckpoint:
    cursor: str | None = None
    page: int = 0
    source_version: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractionRequest:
    tenant_id: str
    company_id: str
    branch_id: str | None
    entities: tuple[str, ...]
    mode: str = "full"
    start_at: datetime | None = None
    end_at: datetime | None = None
    checkpoint: ConnectorCheckpoint | None = None
    page_size: int = 500
    timeout_seconds: int = 60
    configuration: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConnectorEnvelope:
    entity_type: str
    external_id: str
    source_version: str
    occurred_at: datetime
    payload: Mapping[str, Any]
    page: int
    sequence: int
    content_hash: str

    @classmethod
    def create(
        cls,
        *,
        entity_type: str,
        external_id: str,
        source_version: str,
        occurred_at: datetime,
        payload: Mapping[str, Any],
        page: int,
        sequence: int,
    ) -> ConnectorEnvelope:
        canonical = repr(sorted(payload.items())).encode()
        return cls(
            entity_type=entity_type,
            external_id=external_id,
            source_version=source_version,
            occurred_at=occurred_at,
            payload=payload,
            page=page,
            sequence=sequence,
            content_hash=sha256(canonical).hexdigest(),
        )


class Connector(Protocol):
    descriptor: ConnectorDescriptor

    def test_connection(self, configuration: Mapping[str, Any]) -> ConnectionTestResult: ...

    def discover(self, configuration: Mapping[str, Any]) -> tuple[DiscoveredResource, ...]: ...

    def extract(self, request: ExtractionRequest) -> Iterable[ConnectorEnvelope]: ...

    def cancel(self, execution_id: str) -> None: ...


_SIMULATOR_ENTITIES = ("product", "supplier", "sale", "purchase", "stock", "price")


class DeterministicERPConnector:
    descriptor = ConnectorDescriptor(
        key="deterministic-erp",
        name="ERP determinístico de referência",
        version="1.0.0",
        schema_version="2026-07",
        capabilities=frozenset(ConnectorCapability),
        authentication_types=("none",),
        supported_entities=_SIMULATOR_ENTITIES,
    )

    def __init__(self) -> None:
        self._cancelled: set[str] = set()

    def test_connection(self, configuration: Mapping[str, Any]) -> ConnectionTestResult:
        latency = max(1, min(int(configuration.get("latency_ms", 12)), 5_000))
        if configuration.get("simulate_unavailable") is True:
            raise ConnectorError(
                "The deterministic ERP is configured as unavailable",
                classification=ConnectorErrorClass.TRANSIENT,
                retryable=True,
            )
        return ConnectionTestResult(True, latency, "Connection established")

    def discover(self, configuration: Mapping[str, Any]) -> tuple[DiscoveredResource, ...]:
        del configuration
        return tuple(
            DiscoveredResource(entity, entity.title(), self.descriptor.schema_version, True)
            for entity in _SIMULATOR_ENTITIES
        )

    def extract(self, request: ExtractionRequest) -> Iterator[ConnectorEnvelope]:
        selected = request.entities or _SIMULATOR_ENTITIES
        unsupported = set(selected) - set(_SIMULATOR_ENTITIES)
        if unsupported:
            raise ConnectorError(
                f"Unsupported entities: {', '.join(sorted(unsupported))}",
                classification=ConnectorErrorClass.CONFIGURATION,
            )
        records_per_entity = max(1, min(int(request.configuration.get("records", 5)), 10_000))
        seed = str(request.configuration.get("seed", "pharma-2b"))
        base_at = request.end_at or datetime(2026, 7, 17, 12, tzinfo=UTC)
        sequence = 0
        for entity in selected:
            for index in range(records_per_entity):
                sequence += 1
                external_id = f"{entity}-{index + 1:06d}"
                occurred_at = base_at - timedelta(minutes=records_per_entity - index)
                payload = self._payload(entity, index, seed, occurred_at)
                yield ConnectorEnvelope.create(
                    entity_type=entity,
                    external_id=external_id,
                    source_version="1",
                    occurred_at=occurred_at,
                    payload=payload,
                    page=(sequence - 1) // request.page_size + 1,
                    sequence=sequence,
                )

    def cancel(self, execution_id: str) -> None:
        self._cancelled.add(execution_id)

    @staticmethod
    def _payload(entity: str, index: int, seed: str, occurred_at: datetime) -> dict[str, Any]:
        product_number = index % 5 + 1
        product_id = f"product-{product_number:06d}"
        supplier_id = f"supplier-{index % 3 + 1:06d}"
        stable_customer = uuid5(NAMESPACE_URL, f"{seed}:customer:{index % 11}").hex
        common = {"source_seed": seed, "occurred_at": occurred_at.isoformat()}
        if entity == "product":
            return {
                **common,
                "sku": product_id,
                "name": f"Produto referência {index + 1}",
                "ean": f"789{index + 1:010d}"[-13:],
                "brand": f"Marca {index % 4 + 1}",
                "manufacturer": f"Fabricante {index % 3 + 1}",
                "category": "Medicamentos/Referência",
                "unit": "UN",
                "presentation": "caixa",
                "commercial_status": "active",
            }
        if entity == "supplier":
            return {
                **common,
                "supplier_code": f"supplier-{index + 1:06d}",
                "name": f"Fornecedor referência {index + 1}",
                "tax_id_hash": sha256(f"{seed}:supplier:{index}".encode()).hexdigest(),
                "lead_time_days": index % 7 + 1,
                "minimum_order": "100.00",
            }
        if entity == "sale":
            quantity = index % 3 + 1
            unit_price = 10 + index
            total = quantity * unit_price
            return {
                **common,
                "sale_number": f"sale-{index + 1:06d}",
                "channel": "store",
                "customer_key": stable_customer,
                "gross_total": str(total),
                "discount_total": "0.00",
                "net_total": str(total),
                "items": [
                    {
                        "line": 1,
                        "product_code": product_id,
                        "quantity": str(quantity),
                        "unit_price": str(unit_price),
                        "net_total": str(total),
                        "unit_cost": str(max(unit_price - 3, 0)),
                    }
                ],
                "payments": [{"method": "cash", "amount": str(total)}],
            }
        if entity == "purchase":
            quantity = index % 5 + 2
            unit_cost = 7 + index
            return {
                **common,
                "purchase_number": f"purchase-{index + 1:06d}",
                "supplier_code": supplier_id,
                "status": "received",
                "freight_total": "0.00",
                "tax_total": "0.00",
                "items": [
                    {
                        "line": 1,
                        "product_code": product_id,
                        "quantity": str(quantity),
                        "unit_cost": str(unit_cost),
                        "net_total": str(quantity * unit_cost),
                    }
                ],
            }
        if entity == "stock":
            return {
                **common,
                "product_code": product_id,
                "on_hand": str(20 + index),
                "reserved": str(index % 2),
                "in_transit": str(index % 4),
                "movement_type": "receipt",
                "movement_quantity": str(index % 5 + 1),
                "lot_number": f"LOT-{index % 7 + 1:03d}",
                "expires_on": (occurred_at + timedelta(days=365)).date().isoformat(),
            }
        return {
            **common,
            "product_code": product_id,
            "price": str(15 + index),
            "reference_price": str(16 + index),
            "reference_cost": str(8 + index),
            "valid_from": occurred_at.isoformat(),
            "promotion": index % 4 == 0,
            "discount_type": "percentage" if index % 4 == 0 else None,
            "discount_value": "5.00" if index % 4 == 0 else None,
        }


class FileUploadConnector:
    descriptor = ConnectorDescriptor(
        key="file-upload",
        name="Importação de arquivo",
        version="1.0.0",
        schema_version="2026-07",
        capabilities=frozenset(
            {ConnectorCapability.CONNECTION_TEST, ConnectorCapability.CHECKPOINT}
        ),
        authentication_types=("none",),
        supported_entities=_SIMULATOR_ENTITIES,
    )

    def test_connection(self, configuration: Mapping[str, Any]) -> ConnectionTestResult:
        del configuration
        return ConnectionTestResult(True, 1, "Upload channel ready")

    def discover(self, configuration: Mapping[str, Any]) -> tuple[DiscoveredResource, ...]:
        del configuration
        return tuple(
            DiscoveredResource(entity, entity.title(), self.descriptor.schema_version, False)
            for entity in _SIMULATOR_ENTITIES
        )

    def extract(self, request: ExtractionRequest) -> Iterable[ConnectorEnvelope]:
        del request
        raise ConnectorError(
            "File payloads must enter through the immutable upload endpoint",
            classification=ConnectorErrorClass.CONFIGURATION,
        )

    def cancel(self, execution_id: str) -> None:
        del execution_id


class ConnectorRegistry:
    def __init__(self, connectors: Iterable[Connector] | None = None) -> None:
        instances = tuple(connectors or (DeterministicERPConnector(), FileUploadConnector()))
        self._connectors = {connector.descriptor.key: connector for connector in instances}
        if len(self._connectors) != len(instances):
            raise ValueError("Connector keys must be unique")

    def get(self, key: str) -> Connector:
        try:
            return self._connectors[key]
        except KeyError as exc:
            raise ConnectorError(
                f"Unknown connector: {key}",
                classification=ConnectorErrorClass.CONFIGURATION,
            ) from exc

    def descriptors(self) -> tuple[ConnectorDescriptor, ...]:
        return tuple(
            sorted(
                (connector.descriptor for connector in self._connectors.values()),
                key=lambda descriptor: descriptor.key,
            )
        )


connector_registry = ConnectorRegistry()
