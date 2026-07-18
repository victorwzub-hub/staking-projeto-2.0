from __future__ import annotations

# ruff: noqa: E501, S608 -- static, parameterized warehouse SQL is kept readable as SQL.
import json
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from pharma_api.application.audit.service import AuditRecord, append_audit_event
from pharma_api.domain.analytics.kpis import KPI_CATALOG
from pharma_api.infrastructure.db.models.analytics import (
    AnalyticsDailyAggregate,
    AnalyticsDataVersion,
    AnalyticsFact,
    AnalyticsKpiDefinitionVersion,
    AnalyticsLineage,
    AnalyticsRefreshJob,
)

TRANSFORMATION_VERSION = "2c.1"

DIMENSION_SOURCE_SQL = """
SELECT 'tenant' AS dimension_type,t.id::text AS natural_key,NULL::text AS source_record_id,
  NULL::text AS parent_natural_key,t.name AS label,jsonb_build_object('slug',t.slug,'status',t.status) AS attributes,t.updated_at AS source_updated_at
FROM tenants t WHERE t.id=:tenant_id
UNION ALL SELECT 'economic_group',g.id::text,g.id::text,NULL,g.name,jsonb_build_object('status',g.status),g.updated_at
FROM economic_groups g WHERE g.tenant_id=:tenant_id
UNION ALL SELECT 'company',c.id::text,c.id::text,c.economic_group_id::text,c.trade_name,
  jsonb_build_object('legal_name',c.legal_name,'slug',c.slug,'status',c.status),c.updated_at
FROM companies c WHERE c.tenant_id=:tenant_id
UNION ALL SELECT 'branch',b.id::text,b.id::text,b.company_id::text,b.name,
  jsonb_build_object('slug',b.slug,'status',b.status),b.updated_at
FROM branches b WHERE b.tenant_id=:tenant_id
UNION ALL SELECT 'brand',b.id::text,b.id::text,NULL,b.name,'{}'::jsonb,b.updated_at
FROM canonical_brands b WHERE b.tenant_id=:tenant_id
UNION ALL SELECT 'manufacturer',m.id::text,m.id::text,NULL,m.name,'{}'::jsonb,m.updated_at
FROM canonical_manufacturers m WHERE m.tenant_id=:tenant_id
UNION ALL SELECT 'category',c.id::text,c.id::text,c.parent_id::text,c.name,
  jsonb_build_object('level',c.level),c.updated_at
FROM canonical_categories c WHERE c.tenant_id=:tenant_id
UNION ALL SELECT 'category_hierarchy',c.id::text,c.id::text,c.parent_id::text,c.name,
  jsonb_build_object('level',c.level),c.updated_at
FROM canonical_categories c WHERE c.tenant_id=:tenant_id
UNION ALL SELECT 'product',p.id::text,p.id::text,p.category_id::text,p.name,
  jsonb_build_object('sku',p.sku,'brand_id',p.brand_id,'manufacturer_id',p.manufacturer_id,
    'commercial_classification',p.commercial_classification,'status',p.commercial_status),p.updated_at
FROM canonical_products p WHERE p.tenant_id=:tenant_id
UNION ALL SELECT 'product_identifier',i.id::text,i.id::text,i.product_id::text,i.identifier_value,
  jsonb_build_object('identifier_type',i.identifier_type,'primary',i.primary),i.updated_at
FROM canonical_product_identifiers i WHERE i.tenant_id=:tenant_id
UNION ALL SELECT 'commercial_classification',p.commercial_classification,NULL,NULL,p.commercial_classification,
  '{}'::jsonb,max(p.updated_at) FROM canonical_products p
WHERE p.tenant_id=:tenant_id AND p.commercial_classification IS NOT NULL GROUP BY p.commercial_classification
UNION ALL SELECT 'supplier',s.id::text,s.id::text,NULL,s.name,
  jsonb_build_object('status',s.status,'company_id',s.company_id),s.updated_at
FROM canonical_suppliers s WHERE s.tenant_id=:tenant_id
UNION ALL SELECT 'channel',s.channel,NULL,NULL,s.channel,'{}'::jsonb,max(s.updated_at)
FROM canonical_sales s WHERE s.tenant_id=:tenant_id GROUP BY s.channel
UNION ALL SELECT 'sale_origin',s.channel,NULL,NULL,s.channel,'{}'::jsonb,max(s.updated_at)
FROM canonical_sales s WHERE s.tenant_id=:tenant_id GROUP BY s.channel
UNION ALL SELECT 'payment_method',p.method,NULL,NULL,p.method,'{}'::jsonb,max(p.updated_at)
FROM canonical_sale_payments p WHERE p.tenant_id=:tenant_id GROUP BY p.method
UNION ALL SELECT 'movement_type',m.movement_type,NULL,NULL,m.movement_type,'{}'::jsonb,max(m.occurred_at)
FROM canonical_inventory_movements m WHERE m.tenant_id=:tenant_id GROUP BY m.movement_type
UNION ALL SELECT 'promotion',p.id::text,p.id::text,NULL,p.name,
  jsonb_build_object('discount_type',p.discount_type,'discount_value',p.discount_value,'active',p.active),p.updated_at
FROM canonical_promotions p WHERE p.tenant_id=:tenant_id
UNION ALL SELECT 'price_band',band,NULL,NULL,band,'{}'::jsonb,max(updated_at) FROM (
  SELECT CASE WHEN price<10 THEN '0-9.99' WHEN price<25 THEN '10-24.99' WHEN price<50 THEN '25-49.99'
    WHEN price<100 THEN '50-99.99' ELSE '100+' END AS band,updated_at
  FROM canonical_product_prices WHERE tenant_id=:tenant_id
) bands GROUP BY band
UNION ALL SELECT 'date',day::date::text,NULL,NULL,to_char(day,'YYYY-MM-DD'),
  jsonb_build_object('year',extract(year from day),'quarter',extract(quarter from day),'month',extract(month from day),
    'week',extract(week from day),'day_of_week',extract(isodow from day),'is_weekend',extract(isodow from day) IN (6,7)),
  :loaded_at FROM generate_series(cast(:window_start as timestamptz),cast(:window_end as timestamptz)-interval '1 day',interval '1 day') day
UNION ALL SELECT 'hour',hour::text,NULL,NULL,lpad(hour::text,2,'0')||chr(58)||'00',
  jsonb_build_object('hour',hour),:loaded_at FROM generate_series(0,23) hour
"""


def _fact_uuid(key_sql: str) -> str:
    digest = f"md5({key_sql})"
    return (
        f"(substr({digest},1,8)||'-'||substr({digest},9,4)||'-'||substr({digest},13,4)||'-'||"
        f"substr({digest},17,4)||'-'||substr({digest},21,12))::uuid"
    )


_COLUMNS = """
id,tenant_id,fact_type,grain_key,occurred_at,date_value,hour_value,company_id,branch_id,
product_id,category_id,supplier_id,channel,payment_method,movement_type,promotion_id,batch_id,
canonical_table,canonical_record_id,canonical_version,measures,dimension_snapshot,
source_updated_at,loaded_at,data_version
"""


def _insert_fact(select_sql: str) -> str:
    return f"""
        INSERT INTO analytics_facts ({_COLUMNS})
        {select_sql}
        ON CONFLICT (tenant_id,fact_type,grain_key) DO UPDATE SET
          occurred_at=EXCLUDED.occurred_at,date_value=EXCLUDED.date_value,
          hour_value=EXCLUDED.hour_value,company_id=EXCLUDED.company_id,
          branch_id=EXCLUDED.branch_id,product_id=EXCLUDED.product_id,
          category_id=EXCLUDED.category_id,supplier_id=EXCLUDED.supplier_id,
          channel=EXCLUDED.channel,payment_method=EXCLUDED.payment_method,
          movement_type=EXCLUDED.movement_type,promotion_id=EXCLUDED.promotion_id,
          batch_id=EXCLUDED.batch_id,canonical_version=EXCLUDED.canonical_version,
          measures=EXCLUDED.measures,dimension_snapshot=EXCLUDED.dimension_snapshot,
          source_updated_at=EXCLUDED.source_updated_at,loaded_at=EXCLUDED.loaded_at,
          data_version=EXCLUDED.data_version
    """


FACT_LOADERS: tuple[tuple[str, str], ...] = (
    (
        "sale",
        _insert_fact(
            f"""SELECT {_fact_uuid("'sale:'||s.tenant_id::text||':'||s.id::text||':'||s.occurred_at::text")},
            s.tenant_id,'sale',s.id::text||':'||s.occurred_at::text,s.occurred_at,s.occurred_at::date,
            extract(hour from s.occurred_at)::int,s.company_id,s.branch_id,NULL,NULL,NULL,s.channel,NULL,NULL,NULL,s.batch_id,
            'canonical_sales',s.id::text,s.version::text,
            jsonb_build_object('gross_revenue',s.gross_total,'net_revenue',s.net_total,'sale_count',1,
              'completed_sales',CASE WHEN s.status='completed' THEN 1 ELSE 0 END,
              'cancelled_sales',CASE WHEN s.status='cancelled' THEN 1 ELSE 0 END,
              'discount_amount',s.discount_total,'discounted_sales',CASE WHEN s.discount_total>0 THEN 1 ELSE 0 END,
              'sales_tax',s.tax_total,'scoped_net_revenue',s.net_total,'network_net_revenue',s.net_total),
            jsonb_build_object('channel',s.channel,'status',s.status),s.updated_at,:loaded_at,:data_version
            FROM canonical_sales s WHERE s.tenant_id=:tenant_id AND s.occurred_at>=:window_start AND s.occurred_at<:window_end"""
        ),
    ),
    (
        "sale_item",
        _insert_fact(
            f"""SELECT {_fact_uuid("'sale-item:'||i.tenant_id::text||':'||i.id::text")},
            i.tenant_id,'sale_item',i.id::text,i.sale_occurred_at,i.sale_occurred_at::date,
            extract(hour from i.sale_occurred_at)::int,s.company_id,s.branch_id,i.product_id,p.category_id,NULL,s.channel,NULL,NULL,NULL,s.batch_id,
            'canonical_sale_items',i.id::text,'1',
            jsonb_build_object('units_sold',abs(i.quantity),'item_count',1,
              'product_gross_revenue',i.gross_total,'product_net_revenue',i.net_total,
              'product_discount_amount',i.discount_total,'product_sales_tax',i.tax_total,
              'cogs',abs(i.quantity)*coalesce(i.unit_cost,0),'gross_profit',i.net_total-(abs(i.quantity)*coalesce(i.unit_cost,0)),
              'product_gross_profit',i.net_total-(abs(i.quantity)*coalesce(i.unit_cost,0)),
              'negative_margin_products',CASE WHEN i.net_total-(abs(i.quantity)*coalesce(i.unit_cost,0))<0 THEN 1 ELSE 0 END),
            jsonb_build_object('product_name',p.name,'sku',p.sku),i.updated_at,:loaded_at,:data_version
            FROM canonical_sale_items i JOIN canonical_sales s ON s.tenant_id=i.tenant_id AND s.id=i.sale_id AND s.occurred_at=i.sale_occurred_at
            JOIN canonical_products p ON p.tenant_id=i.tenant_id AND p.id=i.product_id
            WHERE i.tenant_id=:tenant_id AND i.sale_occurred_at>=:window_start AND i.sale_occurred_at<:window_end"""
        ),
    ),
    (
        "payment",
        _insert_fact(
            f"""SELECT {_fact_uuid("'payment:'||p.tenant_id::text||':'||p.id::text")},
            p.tenant_id,'payment',p.id::text,p.sale_occurred_at,p.sale_occurred_at::date,
            extract(hour from p.sale_occurred_at)::int,s.company_id,s.branch_id,NULL,NULL,NULL,s.channel,p.method,NULL,NULL,s.batch_id,
            'canonical_sale_payments',p.id::text,'1',jsonb_build_object('payment_count',1,'payment_amount',p.amount),
            jsonb_build_object('installments',p.installments),p.updated_at,:loaded_at,:data_version
            FROM canonical_sale_payments p JOIN canonical_sales s ON s.tenant_id=p.tenant_id AND s.id=p.sale_id AND s.occurred_at=p.sale_occurred_at
            WHERE p.tenant_id=:tenant_id AND p.sale_occurred_at>=:window_start AND p.sale_occurred_at<:window_end"""
        ),
    ),
    (
        "return",
        _insert_fact(
            f"""SELECT {_fact_uuid("'return:'||a.tenant_id::text||':'||a.id::text")},
            a.tenant_id,'return',a.id::text,a.occurred_at,a.occurred_at::date,extract(hour from a.occurred_at)::int,
            s.company_id,s.branch_id,NULL,NULL,NULL,s.channel,NULL,a.adjustment_type,NULL,s.batch_id,
            'canonical_sale_adjustments',a.id::text,'1',
            jsonb_build_object('return_amount',CASE WHEN a.adjustment_type='return' THEN abs(a.amount) ELSE 0 END,
              'return_count',CASE WHEN a.adjustment_type='return' THEN 1 ELSE 0 END),
            jsonb_build_object('reason',a.reason),a.updated_at,:loaded_at,:data_version
            FROM canonical_sale_adjustments a JOIN canonical_sales s ON s.tenant_id=a.tenant_id AND s.id=a.sale_id AND s.occurred_at=a.sale_occurred_at
            WHERE a.tenant_id=:tenant_id AND a.occurred_at>=:window_start AND a.occurred_at<:window_end"""
        ),
    ),
    (
        "purchase",
        _insert_fact(
            f"""SELECT {_fact_uuid("'purchase:'||p.tenant_id::text||':'||p.id::text")},
            p.tenant_id,'purchase',p.id::text,p.ordered_at,p.ordered_at::date,extract(hour from p.ordered_at)::int,
            p.company_id,p.branch_id,NULL,NULL,p.supplier_id,NULL,NULL,NULL,NULL,p.batch_id,
            'canonical_purchase_orders',p.id::text,p.version::text,
            jsonb_build_object('purchase_value',p.net_total,'purchase_merchandise',p.merchandise_total,'purchase_count',1,
              'scoped_purchase_count',1,'scoped_purchase_value',p.net_total,'purchase_discount',p.discount_total,
              'purchase_bonus',p.bonus_total,'purchase_freight',p.freight_total,'purchase_tax',p.tax_total,
              'cancelled_purchases',CASE WHEN p.status='cancelled' THEN 1 ELSE 0 END,
              'returned_purchase_value',CASE WHEN p.status='returned' THEN p.net_total ELSE 0 END,
              'emergency_purchase_count',CASE WHEN p.expected_at IS NOT NULL AND p.expected_at-p.ordered_at<interval '1 day' THEN 1 ELSE 0 END),
            jsonb_build_object('status',p.status),p.updated_at,:loaded_at,:data_version
            FROM canonical_purchase_orders p WHERE p.tenant_id=:tenant_id AND p.ordered_at>=:window_start AND p.ordered_at<:window_end"""
        ),
    ),
    (
        "purchase_item",
        _insert_fact(
            f"""SELECT {_fact_uuid("'purchase-item:'||i.tenant_id::text||':'||i.id::text")},
            i.tenant_id,'purchase_item',i.id::text,p.ordered_at,p.ordered_at::date,extract(hour from p.ordered_at)::int,
            p.company_id,p.branch_id,i.product_id,product.category_id,p.supplier_id,NULL,NULL,NULL,NULL,p.batch_id,
            'canonical_purchase_items',i.id::text,'1',
            jsonb_build_object('purchase_quantity',i.quantity,'purchase_line_count',1,
              'product_purchase_value',i.net_total,'product_purchase_discount',i.discount_total,
              'product_purchase_bonus',i.bonus_quantity*i.unit_cost,'product_purchase_tax',i.tax_total,
              'received_purchase_quantity',CASE WHEN EXISTS (
                SELECT 1 FROM canonical_purchase_receipts receipt
                WHERE receipt.tenant_id=i.tenant_id AND receipt.purchase_order_id=p.id
                  AND receipt.document_type IN ('receipt','invoice')
              ) THEN i.quantity ELSE 0 END,
              'supplier_failed_lines',CASE WHEN p.expected_at<:loaded_at AND NOT EXISTS (
                SELECT 1 FROM canonical_purchase_receipts receipt
                WHERE receipt.tenant_id=i.tenant_id AND receipt.purchase_order_id=p.id
                  AND receipt.document_type IN ('receipt','invoice')
              ) THEN 1 ELSE 0 END,
              'supplier_passed_lines',CASE WHEN p.expected_at>=:loaded_at OR EXISTS (
                SELECT 1 FROM canonical_purchase_receipts receipt
                WHERE receipt.tenant_id=i.tenant_id AND receipt.purchase_order_id=p.id
                  AND receipt.document_type IN ('receipt','invoice')
              ) THEN 1 ELSE 0 END,
              'supplier_stockout_products',CASE WHEN EXISTS (
                SELECT 1 FROM canonical_stock_balances balance
                WHERE balance.tenant_id=i.tenant_id AND balance.branch_id=p.branch_id
                  AND balance.product_id=i.product_id AND balance.on_hand=0
              ) THEN 1 ELSE 0 END,
              'multiple_adherent_lines',CASE WHEN sp.purchase_multiple>0 AND mod(i.quantity,sp.purchase_multiple)=0 THEN 1 ELSE 0 END,
              'minimum_order_total',coalesce(sp.minimum_order,0),'supplier_product_count',1),
            jsonb_build_object('unit_cost',i.unit_cost,'product_name',product.name),i.updated_at,:loaded_at,:data_version
            FROM canonical_purchase_items i JOIN canonical_purchase_orders p ON p.tenant_id=i.tenant_id AND p.id=i.purchase_order_id
            JOIN canonical_products product ON product.tenant_id=i.tenant_id AND product.id=i.product_id
            LEFT JOIN canonical_supplier_products sp ON sp.tenant_id=i.tenant_id AND sp.supplier_id=p.supplier_id AND sp.product_id=i.product_id
            WHERE i.tenant_id=:tenant_id AND p.ordered_at>=:window_start AND p.ordered_at<:window_end"""
        ),
    ),
    (
        "receipt",
        _insert_fact(
            f"""SELECT {_fact_uuid("'receipt:'||r.tenant_id::text||':'||r.id::text")},
            r.tenant_id,'receipt',r.id::text,coalesce(r.received_at,r.issued_at,p.ordered_at),coalesce(r.received_at,r.issued_at,p.ordered_at)::date,
            extract(hour from coalesce(r.received_at,r.issued_at,p.ordered_at))::int,p.company_id,p.branch_id,NULL,NULL,p.supplier_id,NULL,NULL,NULL,NULL,p.batch_id,
            'canonical_purchase_receipts',r.id::text,'1',
            jsonb_build_object('receipt_count',1,'received_purchase_count',1,'received_purchase_value',r.total,
              'on_time_receipts',CASE WHEN r.received_at IS NOT NULL AND p.expected_at IS NOT NULL AND r.received_at<=p.expected_at THEN 1 ELSE 0 END,
              'lead_time_days_total',greatest(extract(epoch from (coalesce(r.received_at,r.issued_at,p.ordered_at)-p.ordered_at))/86400,0)),
            jsonb_build_object('document_type',r.document_type),r.updated_at,:loaded_at,:data_version
            FROM canonical_purchase_receipts r JOIN canonical_purchase_orders p ON p.tenant_id=r.tenant_id AND p.id=r.purchase_order_id
            WHERE r.tenant_id=:tenant_id AND coalesce(r.received_at,r.issued_at,p.ordered_at)>=:window_start AND coalesce(r.received_at,r.issued_at,p.ordered_at)<:window_end"""
        ),
    ),
    (
        "inventory_movement",
        _insert_fact(
            f"""SELECT {_fact_uuid("'movement:'||m.tenant_id::text||':'||m.id::text")},
            m.tenant_id,'inventory_movement',m.id::text,m.occurred_at,m.occurred_at::date,extract(hour from m.occurred_at)::int,
            m.company_id,m.branch_id,m.product_id,p.category_id,NULL,NULL,NULL,m.movement_type,NULL,m.batch_id,
            'canonical_inventory_movements',m.id::text,m.source_version,
            jsonb_build_object('stock_movement_count',1,'stock_adjustment_quantity',CASE WHEN m.movement_type IN ('adjustment','inventory') THEN abs(m.quantity) ELSE 0 END,
              'stock_loss_quantity',CASE WHEN m.movement_type='loss' THEN abs(m.quantity) ELSE 0 END,
              'stock_damage_quantity',CASE WHEN m.movement_type='damage' THEN abs(m.quantity) ELSE 0 END),
            jsonb_build_object('reference_type',m.reference_type,'reference_id',m.reference_id),m.occurred_at,:loaded_at,:data_version
            FROM canonical_inventory_movements m JOIN canonical_products p ON p.tenant_id=m.tenant_id AND p.id=m.product_id
            WHERE m.tenant_id=:tenant_id AND m.occurred_at>=:window_start AND m.occurred_at<:window_end"""
        ),
    ),
    (
        "stock_snapshot",
        _insert_fact(
            f"""SELECT {_fact_uuid("'stock:'||s.tenant_id::text||':'||s.id::text")},
            s.tenant_id,'stock_snapshot',s.id::text,s.snapshot_at,s.snapshot_at::date,extract(hour from s.snapshot_at)::int,
            s.company_id,s.branch_id,s.product_id,p.category_id,NULL,NULL,NULL,NULL,NULL,s.batch_id,
            'canonical_stock_snapshots',s.id::text,'1',
            jsonb_build_object('inventory_on_hand',s.on_hand,'inventory_reserved',s.reserved,
              'inventory_available',greatest(s.on_hand-s.reserved,0),'inventory_in_transit',s.in_transit,
              'negative_stock_products',CASE WHEN s.on_hand<0 THEN 1 ELSE 0 END,
              'zero_stock_products',CASE WHEN s.on_hand=0 THEN 1 ELSE 0 END,
              'active_products',1,'inventory_retail_value',s.on_hand*coalesce(price.price,0),
              'inventory_cost_value',s.on_hand*coalesce(price.reference_cost,0),'scoped_inventory_value',s.on_hand*coalesce(price.reference_cost,0),
              'units_available_for_sale',greatest(s.on_hand-s.reserved,0)),
            jsonb_build_object('product_name',p.name),s.snapshot_at,:loaded_at,:data_version
            FROM canonical_stock_snapshots s JOIN canonical_products p ON p.tenant_id=s.tenant_id AND p.id=s.product_id
            LEFT JOIN LATERAL (SELECT pp.price,pp.reference_cost FROM canonical_product_prices pp
              WHERE pp.tenant_id=s.tenant_id AND pp.product_id=s.product_id AND pp.valid_from<=s.snapshot_at
              ORDER BY pp.valid_from DESC LIMIT 1) price ON true
            WHERE s.tenant_id=:tenant_id AND s.snapshot_at>=:window_start AND s.snapshot_at<:window_end"""
        ),
    ),
    (
        "stock_snapshot",
        _insert_fact(
            f"""SELECT {_fact_uuid("'lot:'||l.tenant_id::text||':'||l.id::text")},
            l.tenant_id,'stock_snapshot','lot:'||l.id::text,l.updated_at,l.updated_at::date,
            extract(hour from l.updated_at)::int,l.company_id,l.branch_id,l.product_id,p.category_id,NULL,NULL,NULL,NULL,NULL,b.batch_id,
            'canonical_inventory_lots',l.id::text,l.version::text,
            jsonb_build_object('expiring_lots',CASE WHEN l.quantity>0 AND l.expires_on BETWEEN cast(:loaded_at as date) AND cast(:loaded_at as date)+30 THEN 1 ELSE 0 END,
              'expired_lots',CASE WHEN l.quantity>0 AND l.expires_on<cast(:loaded_at as date) THEN 1 ELSE 0 END),
            jsonb_build_object('lot_number',l.lot_number,'expires_on',l.expires_on),l.updated_at,:loaded_at,:data_version
            FROM canonical_inventory_lots l JOIN canonical_products p ON p.tenant_id=l.tenant_id AND p.id=l.product_id
            LEFT JOIN canonical_stock_balances b ON b.tenant_id=l.tenant_id AND b.branch_id=l.branch_id AND b.product_id=l.product_id
            WHERE l.tenant_id=:tenant_id AND l.updated_at>=:window_start AND l.updated_at<:window_end"""
        ),
    ),
    (
        "price",
        _insert_fact(
            f"""SELECT {_fact_uuid("'price:'||p.tenant_id::text||':'||p.id::text")},
            p.tenant_id,'price',p.id::text,p.valid_from,p.valid_from::date,extract(hour from p.valid_from)::int,
            p.company_id,p.branch_id,p.product_id,product.category_id,NULL,NULL,NULL,NULL,NULL,p.batch_id,
            'canonical_product_prices',p.id::text,p.source_version,
            jsonb_build_object('price_value',p.price,'price_count',1,'average_price',p.price,
              'price_value_squared',p.price*p.price,
              'previous_price_value',coalesce(p.reference_price,p.price),'price_change_value',p.price-coalesce(p.reference_price,p.price)),
            jsonb_build_object('decision_source',p.decision_source),p.updated_at,:loaded_at,:data_version
            FROM canonical_product_prices p JOIN canonical_products product ON product.tenant_id=p.tenant_id AND product.id=p.product_id
            WHERE p.tenant_id=:tenant_id AND p.valid_from>=:window_start AND p.valid_from<:window_end"""
        ),
    ),
    (
        "promotion",
        _insert_fact(
            f"""SELECT {_fact_uuid("'promotion:'||p.tenant_id::text||':'||p.id::text")},
            p.tenant_id,'promotion',p.id::text,p.valid_from,p.valid_from::date,extract(hour from p.valid_from)::int,
            p.company_id,p.branch_id,NULL,NULL,NULL,NULL,NULL,NULL,p.id,p.batch_id,
            'canonical_promotions',p.id::text,p.version::text,jsonb_build_object('promotion_count',1,'promotion_discount_value',p.discount_value),
            jsonb_build_object('name',p.name,'discount_type',p.discount_type),p.updated_at,:loaded_at,:data_version
            FROM canonical_promotions p WHERE p.tenant_id=:tenant_id AND p.valid_from<:window_end AND p.valid_to>=:window_start"""
        ),
    ),
    (
        "cost",
        _insert_fact(
            f"""SELECT {_fact_uuid("'cost:'||c.tenant_id::text||':'||c.id::text")},
            c.tenant_id,'cost',c.id::text,c.valid_from,c.valid_from::date,extract(hour from c.valid_from)::int,
            product.company_id,product.branch_id,sp.product_id,product.category_id,sp.supplier_id,NULL,NULL,NULL,NULL,c.batch_id,
            'canonical_supplier_costs',c.id::text,'1',jsonb_build_object('cost_value',c.cost,'cost_count',1,
              'previous_cost_value',coalesce(sp.current_cost,c.cost),'cost_change_value',c.cost-coalesce(sp.current_cost,c.cost)),
            '{{}}'::jsonb,c.updated_at,:loaded_at,:data_version
            FROM canonical_supplier_costs c JOIN canonical_supplier_products sp ON sp.tenant_id=c.tenant_id AND sp.id=c.supplier_product_id
            JOIN canonical_products product ON product.tenant_id=sp.tenant_id AND product.id=sp.product_id
            WHERE c.tenant_id=:tenant_id AND c.valid_from>=:window_start AND c.valid_from<:window_end"""
        ),
    ),
    (
        "data_quality",
        _insert_fact(
            f"""SELECT {_fact_uuid("'quality:'||q.tenant_id::text||':'||q.id::text")},
            q.tenant_id,'data_quality',q.id::text,q.created_at,q.created_at::date,extract(hour from q.created_at)::int,
            b.company_id,b.branch_id,NULL,NULL,NULL,NULL,NULL,NULL,NULL,q.batch_id,
            'quality_results',q.id::text,'1',jsonb_build_object('quality_evaluated_records',q.evaluated_records,
              'quality_passed_records',greatest(q.evaluated_records-q.failed_records,0),'quality_incidents',q.failed_records),
            jsonb_build_object('rule_key',q.rule_key,'severity',q.severity,'score',q.score),q.updated_at,:loaded_at,:data_version
            FROM quality_results q JOIN import_batches b ON b.tenant_id=q.tenant_id AND b.id=q.batch_id
            WHERE q.tenant_id=:tenant_id AND q.created_at>=:window_start AND q.created_at<:window_end"""
        ),
    ),
    (
        "import_execution",
        _insert_fact(
            f"""SELECT {_fact_uuid("'import:'||b.tenant_id::text||':'||b.id::text")},
            b.tenant_id,'import_execution',b.id::text,b.created_at,b.created_at::date,extract(hour from b.created_at)::int,
            b.company_id,b.branch_id,NULL,NULL,NULL,NULL,NULL,NULL,NULL,b.id,
            'import_batches',b.id::text,b.version::text,jsonb_build_object('batch_count',1,
              'successful_batches',CASE WHEN b.state IN ('completed','completed_with_warnings') THEN 1 ELSE 0 END,
              'failed_batches',CASE WHEN b.state IN ('failed','quarantined') THEN 1 ELSE 0 END,
              'received_records',b.received_records,'valid_records',b.valid_records,'rejected_records',b.rejected_records,
              'duplicate_records',b.duplicate_records,'processing_seconds',coalesce(extract(epoch from (b.completed_at-b.started_at)),0),
              'analytics_processing_seconds',coalesce((SELECT sum(extract(epoch from (coalesce(j.completed_at,:loaded_at)-j.started_at)))
                FROM analytics_refresh_jobs j WHERE j.tenant_id=b.tenant_id AND j.source_batch_id=b.id AND j.started_at IS NOT NULL),0),
              'backfill_count',coalesce((SELECT count(*) FROM analytics_refresh_jobs j
                WHERE j.tenant_id=b.tenant_id AND j.source_batch_id=b.id AND j.trigger_type='backfill'),0),
              'recomputation_count',coalesce((SELECT count(*) FROM analytics_refresh_jobs j
                WHERE j.tenant_id=b.tenant_id AND j.source_batch_id=b.id AND j.trigger_type='recompute'),0),
              'source_lag_seconds',coalesce(extract(epoch from (b.created_at-(b.period_end::timestamp AT TIME ZONE 'UTC'))),0)),
            jsonb_build_object('dataset_type',b.dataset_type,'state',b.state),b.updated_at,:loaded_at,:data_version
            FROM import_batches b WHERE b.tenant_id=:tenant_id AND b.created_at>=:window_start AND b.created_at<:window_end"""
        ),
    ),
)


def _definition_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return sha256(encoded).hexdigest()


async def _sync_dimensions(
    session: AsyncSession, tenant_id: UUID, parameters: dict[str, Any]
) -> int:
    await session.execute(
        text(
            f"""WITH source AS ({DIMENSION_SOURCE_SQL})
            UPDATE analytics_dimensions current SET current=false,effective_to=:loaded_at,
              updated_at=:loaded_at,version=current.version+1
            FROM source WHERE current.tenant_id=:tenant_id AND current.current=true
              AND current.dimension_type=source.dimension_type AND current.natural_key=source.natural_key
              AND current.version_hash<>md5(source.label||':'||source.attributes::text||':'||coalesce(source.parent_natural_key,''))"""
        ),
        parameters,
    )
    result = cast(
        CursorResult[Any],
        await session.execute(
            text(
                f"""WITH source AS ({DIMENSION_SOURCE_SQL})
            INSERT INTO analytics_dimensions
              (id,tenant_id,dimension_type,natural_key,source_record_id,parent_natural_key,label,attributes,
               effective_from,effective_to,current,version_hash,version,created_at,updated_at)
            SELECT {_fact_uuid("cast(:tenant_id as text)||':'||source.dimension_type||':'||source.natural_key||':'||md5(source.label||':'||source.attributes::text||':'||coalesce(source.parent_natural_key,''))")},
              :tenant_id,source.dimension_type,source.natural_key,source.source_record_id,source.parent_natural_key,
              source.label,source.attributes,source.source_updated_at,NULL,true,
              md5(source.label||':'||source.attributes::text||':'||coalesce(source.parent_natural_key,'')),1,:loaded_at,:loaded_at
            FROM source LEFT JOIN analytics_dimensions current ON current.tenant_id=:tenant_id
              AND current.dimension_type=source.dimension_type AND current.natural_key=source.natural_key AND current.current=true
            WHERE current.id IS NULL
            ON CONFLICT (tenant_id,dimension_type,natural_key,effective_from) DO UPDATE SET
              label=EXCLUDED.label,attributes=EXCLUDED.attributes,parent_natural_key=EXCLUDED.parent_natural_key,
              source_record_id=EXCLUDED.source_record_id,updated_at=EXCLUDED.updated_at"""
            ),
            parameters,
        ),
    )
    return max(result.rowcount or 0, 0)


async def _sync_catalog(session: AsyncSession, tenant_id: UUID, now: datetime) -> None:
    existing = {
        (item.kpi_code, item.formula_version): item
        for item in (
            await session.scalars(
                select(AnalyticsKpiDefinitionVersion).where(
                    AnalyticsKpiDefinitionVersion.tenant_id == tenant_id
                )
            )
        ).all()
    }
    for definition in KPI_CATALOG:
        payload = definition.as_dict()
        digest = _definition_hash(payload)
        current = existing.get((definition.code, definition.version))
        if current is not None:
            if current.definition_hash != digest:
                raise RuntimeError(
                    f"KPI {definition.code} version {definition.version} changed without a version bump"
                )
            continue
        for (kpi_code, formula_version), previous in existing.items():
            if (
                kpi_code == definition.code
                and formula_version < definition.version
                and previous.effective_to is None
            ):
                previous.effective_to = now
        session.add(
            AnalyticsKpiDefinitionVersion(
                tenant_id=tenant_id,
                kpi_code=definition.code,
                formula_version=definition.version,
                definition=payload,
                definition_hash=digest,
                category=definition.category,
                status=definition.status,
                effective_from=now,
                created_by="release:2c.1",
                created_at=now,
            )
        )
        await append_audit_event(
            session,
            AuditRecord(
                action="analytics.formula.version_registered",
                category="analytics_governance",
                outcome="success",
                tenant_id=tenant_id,
                resource_type="kpi_definition",
                resource_id=definition.code,
                changed_fields=["definition", "formula_version"],
                justification="versioned deployment catalog synchronization",
                metadata={
                    "formula_version": definition.version,
                    "definition_hash": digest,
                    "release": TRANSFORMATION_VERSION,
                },
            ),
        )


def _aggregate_sql(grain: str, dimensions: tuple[str, ...]) -> str:
    nullable = ("company_id", "branch_id", "product_id", "category_id", "supplier_id")
    selected = [
        f"f.{column} AS {column}"
        if column in dimensions
        else f"NULL::{('uuid' if column.endswith('_id') else 'text')} AS {column}"
        for column in nullable
    ]
    dimension_value = (
        "f.channel"
        if grain == "channel"
        else "f.payment_method"
        if grain == "payment_method"
        else "f.movement_type"
        if grain == "movement_type"
        else "NULL::text"
    )
    group_columns = [f"f.{column}" for column in dimensions]
    aggregate_key = (
        "'aggregate:'||cast(:tenant_id as text)||':'||date_value::text||':'||"
        "cast(:grain as text)||':'||coalesce(company_id::text,'')||':'||"
        "coalesce(branch_id::text,'')||':'||coalesce(product_id::text,'')||':'||"
        "coalesce(category_id::text,'')||':'||coalesce(supplier_id::text,'')||':'||"
        "coalesce(dimension_value,'')"
    )
    return f"""
      INSERT INTO analytics_daily_aggregates
        (id,tenant_id,date_value,grain,company_id,branch_id,product_id,category_id,supplier_id,dimension_value,measures,source_max_updated_at,generated_at,data_version)
      SELECT {_fact_uuid(aggregate_key)},
        :tenant_id,date_value,:grain,{",".join(nullable)},dimension_value,
        jsonb_object_agg(measure_key,measure_total),max(max_source),:loaded_at,:data_version
      FROM (
        SELECT f.date_value,{",".join(selected)},{dimension_value} AS dimension_value,
          kv.key AS measure_key,sum((kv.value)::numeric) AS measure_total,max(f.source_updated_at) AS max_source
        FROM analytics_facts f CROSS JOIN LATERAL jsonb_each_text(f.measures) kv
        WHERE f.tenant_id=:tenant_id AND f.occurred_at>=:window_start AND f.occurred_at<:window_end
          AND jsonb_typeof(f.measures->kv.key)='number'
        GROUP BY f.date_value{"," if group_columns else ""}{",".join(group_columns)}{"," if grain in {"channel", "payment_method", "movement_type"} else ""}{dimension_value if grain in {"channel", "payment_method", "movement_type"} else ""},kv.key
      ) measures
      GROUP BY date_value,company_id,branch_id,product_id,category_id,supplier_id,dimension_value
      ON CONFLICT (tenant_id,date_value,grain,company_id,branch_id,product_id,category_id,supplier_id,dimension_value)
      DO UPDATE SET measures=EXCLUDED.measures,source_max_updated_at=EXCLUDED.source_max_updated_at,
        generated_at=EXCLUDED.generated_at,data_version=EXCLUDED.data_version
    """


AGGREGATE_GRAINS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("scope", ("company_id", "branch_id")),
    ("product", ("company_id", "branch_id", "product_id", "category_id")),
    ("category", ("company_id", "branch_id", "category_id")),
    ("supplier", ("company_id", "branch_id", "supplier_id")),
    ("channel", ("company_id", "branch_id")),
    ("payment_method", ("company_id", "branch_id")),
    ("movement_type", ("company_id", "branch_id")),
)


async def execute_refresh(
    session: AsyncSession, job: AnalyticsRefreshJob
) -> dict[str, int | float]:
    started = perf_counter()
    now = datetime.now(UTC)
    version_row = await session.scalar(
        select(AnalyticsDataVersion)
        .where(AnalyticsDataVersion.tenant_id == job.tenant_id)
        .with_for_update()
    )
    data_version = (version_row.current_version if version_row else 0) + 1
    parameters: dict[str, Any] = {
        "tenant_id": job.tenant_id,
        "window_start": job.window_start,
        "window_end": job.window_end,
        "loaded_at": now,
        "data_version": data_version,
    }
    dimension_count = await _sync_dimensions(session, job.tenant_id, parameters)
    job.checkpoint = {"step": "dimensions", "dimensions": dimension_count}
    await session.execute(
        delete(AnalyticsLineage).where(
            AnalyticsLineage.fact_id.in_(
                select(AnalyticsFact.id).where(
                    AnalyticsFact.tenant_id == job.tenant_id,
                    AnalyticsFact.occurred_at >= job.window_start,
                    AnalyticsFact.occurred_at < job.window_end,
                )
            )
        )
    )
    await session.execute(
        delete(AnalyticsFact).where(
            AnalyticsFact.tenant_id == job.tenant_id,
            AnalyticsFact.occurred_at >= job.window_start,
            AnalyticsFact.occurred_at < job.window_end,
        )
    )
    fact_counts: dict[str, int] = {}
    for fact_type, statement in FACT_LOADERS:
        result = cast(CursorResult[Any], await session.execute(text(statement), parameters))
        fact_counts[fact_type] = fact_counts.get(fact_type, 0) + max(result.rowcount or 0, 0)
        job.checkpoint = {"step": f"fact:{fact_type}", "facts": fact_counts}
    await session.execute(
        delete(AnalyticsDailyAggregate).where(
            AnalyticsDailyAggregate.tenant_id == job.tenant_id,
            AnalyticsDailyAggregate.date_value >= job.window_start.date(),
            AnalyticsDailyAggregate.date_value < job.window_end.date(),
        )
    )
    aggregate_count = 0
    for grain, dimensions in AGGREGATE_GRAINS:
        result = cast(
            CursorResult[Any],
            await session.execute(
                text(_aggregate_sql(grain, dimensions)), {**parameters, "grain": grain}
            ),
        )
        aggregate_count += max(result.rowcount or 0, 0)
        job.checkpoint = {"step": f"aggregate:{grain}", "facts": fact_counts}
    await session.execute(
        text(
            """INSERT INTO analytics_lineage
              (id,tenant_id,fact_id,source_batch_id,canonical_table,canonical_record_id,canonical_version,transformation_version,refresh_job_id,created_at)
              SELECT (substr(md5('lineage:'||f.id::text),1,8)||'-'||substr(md5('lineage:'||f.id::text),9,4)||'-'||substr(md5('lineage:'||f.id::text),13,4)||'-'||substr(md5('lineage:'||f.id::text),17,4)||'-'||substr(md5('lineage:'||f.id::text),21,12))::uuid,
                f.tenant_id,f.id,f.batch_id,f.canonical_table,f.canonical_record_id,f.canonical_version,:transformation_version,:job_id,:loaded_at
              FROM analytics_facts f WHERE f.tenant_id=:tenant_id AND f.occurred_at>=:window_start AND f.occurred_at<:window_end
              ON CONFLICT (tenant_id,fact_id,canonical_table,canonical_record_id) DO UPDATE SET
                source_batch_id=EXCLUDED.source_batch_id,canonical_version=EXCLUDED.canonical_version,
                transformation_version=EXCLUDED.transformation_version,refresh_job_id=EXCLUDED.refresh_job_id,created_at=EXCLUDED.created_at"""
        ),
        {**parameters, "job_id": job.id, "transformation_version": TRANSFORMATION_VERSION},
    )
    await _sync_catalog(session, job.tenant_id, now)
    quality_score = await session.scalar(
        text(
            """SELECT avg((dimension_snapshot->>'score')::numeric) FROM analytics_facts
               WHERE tenant_id=:tenant_id AND fact_type='data_quality'"""
        ),
        {"tenant_id": job.tenant_id},
    )
    watermark = await session.scalar(
        select(func.max(AnalyticsFact.source_updated_at)).where(
            AnalyticsFact.tenant_id == job.tenant_id
        )
    )
    if version_row is None:
        version_row = AnalyticsDataVersion(
            tenant_id=job.tenant_id,
            current_version=data_version,
            cache_namespace=data_version,
            watermark=watermark,
            freshness_at=now,
            quality_score=quality_score,
            last_refresh_job_id=job.id,
            updated_at=now,
        )
        session.add(version_row)
    else:
        version_row.current_version = data_version
        version_row.cache_namespace = data_version
        version_row.watermark = watermark
        version_row.freshness_at = now
        version_row.quality_score = quality_score
        version_row.last_refresh_job_id = job.id
        version_row.updated_at = now
    elapsed = perf_counter() - started
    metrics: dict[str, int | float] = {
        "facts_processed": sum(fact_counts.values()),
        "aggregates_updated": aggregate_count,
        "catalog_entries": len(KPI_CATALOG),
        "dimensions_updated": dimension_count,
        "duration_seconds": round(elapsed, 6),
        "data_version": data_version,
    }
    job.metrics = {**metrics, "fact_counts": fact_counts}
    job.checkpoint = {"step": "completed", "facts": fact_counts}
    job.watermark_after = watermark
    return metrics
