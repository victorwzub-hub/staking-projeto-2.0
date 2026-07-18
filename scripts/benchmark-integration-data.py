#!/usr/bin/env python3
"""Generate a deterministic, streaming ERP landing file and report generator capacity."""

from __future__ import annotations

import argparse
import json
import tracemalloc
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from time import perf_counter

ENTITIES = ("product", "supplier", "sale", "purchase", "stock", "price")


def _payload(entity: str, index: int, occurred_at: datetime) -> dict[str, object]:
    product_code = f"product-{index % 50_000 + 1:08d}"
    common: dict[str, object] = {"occurred_at": occurred_at.isoformat()}
    if entity == "product":
        return {
            **common,
            "sku": f"product-{index + 1:08d}",
            "name": f"Produto sintético {index + 1}",
            "ean": f"789{index + 1:010d}"[-13:],
            "brand": f"Marca {index % 100 + 1}",
            "manufacturer": f"Fabricante {index % 50 + 1}",
            "category": "Medicamentos/Sintético",
            "unit": "UN",
        }
    if entity == "supplier":
        return {
            **common,
            "supplier_code": f"supplier-{index + 1:08d}",
            "name": f"Fornecedor sintético {index + 1}",
            "tax_id_hash": sha256(f"supplier:{index}".encode()).hexdigest(),
        }
    if entity == "sale":
        return {
            **common,
            "sale_number": f"sale-{index + 1:08d}",
            "channel": "store",
            "gross_total": "10.00",
            "discount_total": "0.00",
            "net_total": "10.00",
            "items": [
                {
                    "line": 1,
                    "product_code": product_code,
                    "quantity": "1",
                    "unit_price": "10.00",
                    "unit_cost": "7.00",
                    "net_total": "10.00",
                }
            ],
            "payments": [{"method": "cash", "amount": "10.00"}],
        }
    if entity == "purchase":
        return {
            **common,
            "purchase_number": f"purchase-{index + 1:08d}",
            "supplier_code": f"supplier-{index % 10_000 + 1:08d}",
            "status": "received",
            "items": [
                {
                    "line": 1,
                    "product_code": product_code,
                    "quantity": "5",
                    "unit_cost": "7.00",
                    "net_total": "35.00",
                }
            ],
        }
    if entity == "stock":
        return {
            **common,
            "product_code": product_code,
            "on_hand": "20",
            "reserved": "1",
            "in_transit": "2",
            "movement_type": "inventory",
            "movement_quantity": "1",
        }
    return {
        **common,
        "product_code": product_code,
        "price": "15.00",
        "reference_price": "16.00",
        "reference_cost": "8.00",
        "valid_from": occurred_at.isoformat(),
    }


def generate(path: Path, records: int, entity: str) -> dict[str, float | int | str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    tracemalloc.start()
    started = perf_counter()
    digest = sha256()
    base_at = datetime(2026, 7, 17, 12, tzinfo=UTC)
    with path.open("wb") as output:
        for index in range(records):
            current_entity = entity if entity != "all" else ENTITIES[index % len(ENTITIES)]
            occurred_at = base_at + timedelta(seconds=index)
            document = {
                "entity_type": current_entity,
                "external_id": f"{current_entity}-{index + 1:08d}",
                "source_version": "benchmark-1",
                "occurred_at": occurred_at.isoformat(),
                "page": index // 1_000 + 1,
                "sequence": index + 1,
                "payload": _payload(current_entity, index, occurred_at),
            }
            line = (json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
            digest.update(line)
            output.write(line)
    duration = perf_counter() - started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    size = path.stat().st_size
    return {
        "path": str(path),
        "records": records,
        "bytes": size,
        "sha256": digest.hexdigest(),
        "duration_seconds": round(duration, 3),
        "records_per_second": round(records / duration, 2),
        "mib_per_second": round(size / 1_048_576 / duration, 2),
        "peak_memory_mib": round(peak_bytes / 1_048_576, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=100_000)
    parser.add_argument("--entity", choices=(*ENTITIES, "all"), default="all")
    parser.add_argument("--output", type=Path, default=Path(".local/bench/phase2b.ndjson"))
    args = parser.parse_args()
    if args.records < 1:
        parser.error("--records must be positive")
    print(json.dumps(generate(args.output, args.records, args.entity), indent=2))


if __name__ == "__main__":
    main()
