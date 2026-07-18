from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pharma_api.infrastructure.db.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionMixin,
)


class Brand(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "canonical_brands"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_canonical_brands_tenant_id"),
        UniqueConstraint("tenant_id", "normalized_name", name="uq_canonical_brands_name"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(180), nullable=False)


class Manufacturer(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "canonical_manufacturers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_canonical_manufacturers_tenant_id"),
        UniqueConstraint("tenant_id", "normalized_name", name="uq_canonical_manufacturers_name"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(220), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(220), nullable=False)


class Category(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "canonical_categories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_canonical_categories_tenant_id"),
        UniqueConstraint(
            "tenant_id", "parent_id", "normalized_name", name="uq_canonical_categories_path"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["canonical_categories.tenant_id", "canonical_categories.id"],
            ondelete="RESTRICT",
            name="fk_canonical_categories_parent_same_tenant",
        ),
        Index("ix_canonical_categories_parent", "tenant_id", "parent_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    parent_id: Mapped[UUID | None] = mapped_column()
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(180), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Product(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "canonical_products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_canonical_products_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "external_id",
            name="uq_canonical_products_source_external",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_canonical_products_company_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_canonical_products_branch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            ondelete="RESTRICT",
            name="fk_canonical_products_source_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="RESTRICT",
            name="fk_canonical_products_batch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            ondelete="RESTRICT",
            name="fk_canonical_products_staging_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "brand_id"],
            ["canonical_brands.tenant_id", "canonical_brands.id"],
            ondelete="RESTRICT",
            name="fk_canonical_products_brand_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "manufacturer_id"],
            ["canonical_manufacturers.tenant_id", "canonical_manufacturers.id"],
            ondelete="RESTRICT",
            name="fk_canonical_products_manufacturer_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["canonical_categories.tenant_id", "canonical_categories.id"],
            ondelete="RESTRICT",
            name="fk_canonical_products_category_same_tenant",
        ),
        CheckConstraint(
            "commercial_status IN ('active','inactive','discontinued','blocked')",
            name="ck_canonical_products_status",
        ),
        Index(
            "ix_canonical_products_scope_name",
            "tenant_id",
            "company_id",
            "branch_id",
            "normalized_name",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column()
    branch_id: Mapped[UUID | None] = mapped_column()
    data_source_id: Mapped[UUID] = mapped_column()
    batch_id: Mapped[UUID] = mapped_column()
    staging_record_id: Mapped[UUID] = mapped_column()
    external_id: Mapped[str] = mapped_column(String(240), nullable=False)
    source_version: Mapped[str] = mapped_column(String(100), nullable=False)
    sku: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(300), nullable=False)
    brand_id: Mapped[UUID | None] = mapped_column()
    manufacturer_id: Mapped[UUID | None] = mapped_column()
    category_id: Mapped[UUID | None] = mapped_column()
    base_unit: Mapped[str] = mapped_column(String(24), nullable=False)
    commercial_status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    commercial_classification: Mapped[str | None] = mapped_column(String(100))
    regulatory_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    controlled_attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )


class ProductIdentifier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "canonical_product_identifiers"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "identifier_type",
            "identifier_value",
            name="uq_canonical_product_identifiers_value",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            ondelete="CASCADE",
            name="fk_canonical_product_identifiers_product_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            ondelete="CASCADE",
            name="fk_canonical_product_identifiers_source_same_tenant",
        ),
        Index("ix_canonical_product_identifiers_lookup", "tenant_id", "identifier_value"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    product_id: Mapped[UUID] = mapped_column()
    data_source_id: Mapped[UUID | None] = mapped_column()
    identifier_type: Mapped[str] = mapped_column(String(40), nullable=False)
    identifier_value: Mapped[str] = mapped_column(String(180), nullable=False)
    primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ProductPresentation(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "canonical_product_presentations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "product_id", "name", name="uq_canonical_product_presentations_name"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            ondelete="CASCADE",
            name="fk_canonical_product_presentations_product_same_tenant",
        ),
        CheckConstraint("conversion_factor > 0", name="ck_canonical_product_presentations_factor"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    product_id: Mapped[UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    unit: Mapped[str] = mapped_column(String(24), nullable=False)
    conversion_factor: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(40))


class Supplier(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "canonical_suppliers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_canonical_suppliers_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "external_id",
            name="uq_canonical_suppliers_source_external",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_canonical_suppliers_company_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            ondelete="RESTRICT",
            name="fk_canonical_suppliers_source_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="RESTRICT",
            name="fk_canonical_suppliers_batch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            ondelete="RESTRICT",
            name="fk_canonical_suppliers_staging_same_tenant",
        ),
        Index("ix_canonical_suppliers_scope_name", "tenant_id", "company_id", "normalized_name"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column()
    data_source_id: Mapped[UUID] = mapped_column()
    batch_id: Mapped[UUID] = mapped_column()
    staging_record_id: Mapped[UUID] = mapped_column()
    external_id: Mapped[str] = mapped_column(String(240), nullable=False)
    source_version: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(260), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(260), nullable=False)
    tax_id_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    commercial_terms: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class SupplierIdentifier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "canonical_supplier_identifiers"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "identifier_type",
            "identifier_value",
            name="uq_canonical_supplier_identifiers_value",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["canonical_suppliers.tenant_id", "canonical_suppliers.id"],
            ondelete="CASCADE",
            name="fk_canonical_supplier_identifiers_supplier_same_tenant",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    supplier_id: Mapped[UUID] = mapped_column()
    identifier_type: Mapped[str] = mapped_column(String(40), nullable=False)
    identifier_value: Mapped[str] = mapped_column(String(180), nullable=False)


class SupplierProduct(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "canonical_supplier_products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_canonical_supplier_products_tenant_id"),
        UniqueConstraint(
            "tenant_id", "supplier_id", "product_id", name="uq_canonical_supplier_products_pair"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["canonical_suppliers.tenant_id", "canonical_suppliers.id"],
            ondelete="CASCADE",
            name="fk_canonical_supplier_products_supplier_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            ondelete="CASCADE",
            name="fk_canonical_supplier_products_product_same_tenant",
        ),
        CheckConstraint(
            "lead_time_days >= 0 AND minimum_order >= 0 AND purchase_multiple > 0",
            name="ck_canonical_supplier_products_terms",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    supplier_id: Mapped[UUID] = mapped_column()
    product_id: Mapped[UUID] = mapped_column()
    supplier_product_code: Mapped[str | None] = mapped_column(String(160))
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    minimum_order: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    purchase_multiple: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=1)
    current_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))


class SupplierCost(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "canonical_supplier_costs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "supplier_product_id"],
            ["canonical_supplier_products.tenant_id", "canonical_supplier_products.id"],
            ondelete="CASCADE",
            name="fk_canonical_supplier_costs_link_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="RESTRICT",
            name="fk_canonical_supplier_costs_batch_same_tenant",
        ),
        CheckConstraint("cost >= 0", name="ck_canonical_supplier_costs_cost"),
        Index(
            "ix_canonical_supplier_costs_history", "tenant_id", "supplier_product_id", "valid_from"
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    supplier_product_id: Mapped[UUID] = mapped_column()
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    batch_id: Mapped[UUID] = mapped_column()


class Sale(TimestampMixin, VersionMixin, Base):
    __tablename__ = "canonical_sales"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "id", "occurred_at", name="uq_canonical_sales_tenant_id_occurred"
        ),
        UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "external_id",
            "occurred_at",
            name="uq_canonical_sales_source_external",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_canonical_sales_branch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            ondelete="RESTRICT",
            name="fk_canonical_sales_source_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="RESTRICT",
            name="fk_canonical_sales_batch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            ondelete="RESTRICT",
            name="fk_canonical_sales_staging_same_tenant",
        ),
        CheckConstraint(
            "gross_total >= 0 AND discount_total >= 0 AND net_total >= 0",
            name="ck_canonical_sales_totals",
        ),
        Index(
            "ix_canonical_sales_scope_occurred",
            "tenant_id",
            "company_id",
            "branch_id",
            "occurred_at",
        ),
        Index("ix_canonical_sales_occurred_brin", "occurred_at", postgresql_using="brin"),
        {"postgresql_partition_by": "RANGE (occurred_at)"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column()
    branch_id: Mapped[UUID] = mapped_column()
    data_source_id: Mapped[UUID] = mapped_column()
    batch_id: Mapped[UUID] = mapped_column()
    staging_record_id: Mapped[UUID] = mapped_column()
    external_id: Mapped[str] = mapped_column(String(240), nullable=False)
    source_version: Mapped[str] = mapped_column(String(100), nullable=False)
    accounting_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="completed")
    operator_external_id: Mapped[str | None] = mapped_column(String(160))
    customer_pseudonym: Mapped[str | None] = mapped_column(String(64))
    gross_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    net_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)


class SaleItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "canonical_sale_items"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "sale_id",
            "sale_occurred_at",
            "line_number",
            name="uq_canonical_sale_items_line",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sale_id", "sale_occurred_at"],
            ["canonical_sales.tenant_id", "canonical_sales.id", "canonical_sales.occurred_at"],
            ondelete="CASCADE",
            name="fk_canonical_sale_items_sale_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            ondelete="RESTRICT",
            name="fk_canonical_sale_items_product_same_tenant",
        ),
        CheckConstraint(
            "quantity <> 0 AND gross_total >= 0 AND discount_total >= 0 AND net_total >= 0",
            name="ck_canonical_sale_items_values",
        ),
        Index("ix_canonical_sale_items_product", "tenant_id", "product_id", "sale_occurred_at"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    sale_id: Mapped[UUID] = mapped_column()
    sale_occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column()
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    gross_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    net_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)


class SalePayment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "canonical_sale_payments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "sale_id", "sale_occurred_at"],
            ["canonical_sales.tenant_id", "canonical_sales.id", "canonical_sales.occurred_at"],
            ondelete="CASCADE",
            name="fk_canonical_sale_payments_sale_same_tenant",
        ),
        CheckConstraint("amount >= 0", name="ck_canonical_sale_payments_amount"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    sale_id: Mapped[UUID] = mapped_column()
    sale_occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    method: Mapped[str] = mapped_column(String(60), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    installments: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class SaleAdjustment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "canonical_sale_adjustments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "sale_id", "sale_occurred_at"],
            ["canonical_sales.tenant_id", "canonical_sales.id", "canonical_sales.occurred_at"],
            ondelete="CASCADE",
            name="fk_canonical_sale_adjustments_sale_same_tenant",
        ),
        CheckConstraint(
            "adjustment_type IN ('cancellation','return','discount','charge')",
            name="ck_canonical_sale_adjustments_type",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    sale_id: Mapped[UUID] = mapped_column()
    sale_occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    adjustment_type: Mapped[str] = mapped_column(String(24), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(300))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PurchaseOrder(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "canonical_purchase_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_canonical_purchase_orders_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "external_id",
            name="uq_canonical_purchase_orders_source_external",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_canonical_purchase_orders_branch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["canonical_suppliers.tenant_id", "canonical_suppliers.id"],
            ondelete="RESTRICT",
            name="fk_canonical_purchase_orders_supplier_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            ondelete="RESTRICT",
            name="fk_canonical_purchase_orders_source_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="RESTRICT",
            name="fk_canonical_purchase_orders_batch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            ondelete="RESTRICT",
            name="fk_canonical_purchase_orders_staging_same_tenant",
        ),
        Index(
            "ix_canonical_purchase_orders_scope_date",
            "tenant_id",
            "company_id",
            "branch_id",
            "ordered_at",
        ),
        Index("ix_canonical_purchase_orders_ordered_brin", "ordered_at", postgresql_using="brin"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column()
    branch_id: Mapped[UUID] = mapped_column()
    supplier_id: Mapped[UUID] = mapped_column()
    data_source_id: Mapped[UUID] = mapped_column()
    batch_id: Mapped[UUID] = mapped_column()
    staging_record_id: Mapped[UUID] = mapped_column()
    external_id: Mapped[str] = mapped_column(String(240), nullable=False)
    source_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accounting_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merchandise_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    bonus_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    freight_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    net_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)


class PurchaseItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "canonical_purchase_items"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "purchase_order_id", "line_number", name="uq_canonical_purchase_items_line"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["canonical_purchase_orders.tenant_id", "canonical_purchase_orders.id"],
            ondelete="CASCADE",
            name="fk_canonical_purchase_items_order_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            ondelete="RESTRICT",
            name="fk_canonical_purchase_items_product_same_tenant",
        ),
        CheckConstraint(
            "quantity > 0 AND unit_cost >= 0 AND net_total >= 0",
            name="ck_canonical_purchase_items_values",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    purchase_order_id: Mapped[UUID] = mapped_column()
    product_id: Mapped[UUID] = mapped_column()
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    bonus_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    net_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)


class PurchaseReceipt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "canonical_purchase_receipts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "purchase_order_id",
            "document_number",
            name="uq_canonical_purchase_receipts_document",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["canonical_purchase_orders.tenant_id", "canonical_purchase_orders.id"],
            ondelete="CASCADE",
            name="fk_canonical_purchase_receipts_order_same_tenant",
        ),
        CheckConstraint(
            "document_type IN ('receipt','invoice','return','cancellation')",
            name="ck_canonical_purchase_receipts_type",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    purchase_order_id: Mapped[UUID] = mapped_column()
    document_type: Mapped[str] = mapped_column(String(24), nullable=False)
    document_number: Mapped[str] = mapped_column(String(120), nullable=False)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)


class InventoryLot(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "canonical_inventory_lots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_canonical_inventory_lots_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "branch_id",
            "product_id",
            "lot_number",
            name="uq_canonical_inventory_lots_number",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            ondelete="CASCADE",
            name="fk_canonical_inventory_lots_product_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_canonical_inventory_lots_branch_same_tenant",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column()
    branch_id: Mapped[UUID] = mapped_column()
    product_id: Mapped[UUID] = mapped_column()
    lot_number: Mapped[str] = mapped_column(String(120), nullable=False)
    manufactured_on: Mapped[date | None] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)


class StockBalance(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "canonical_stock_balances"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "branch_id", "product_id", name="uq_canonical_stock_balances_product"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            ondelete="CASCADE",
            name="fk_canonical_stock_balances_product_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            ondelete="RESTRICT",
            name="fk_canonical_stock_balances_source_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="RESTRICT",
            name="fk_canonical_stock_balances_batch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_canonical_stock_balances_branch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            ondelete="RESTRICT",
            name="fk_canonical_stock_balances_staging_same_tenant",
        ),
        CheckConstraint(
            "on_hand >= 0 AND reserved >= 0 AND in_transit >= 0 AND reserved <= on_hand",
            name="ck_canonical_stock_balances_values",
        ),
        Index("ix_canonical_stock_balances_scope", "tenant_id", "company_id", "branch_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column()
    branch_id: Mapped[UUID] = mapped_column()
    product_id: Mapped[UUID] = mapped_column()
    data_source_id: Mapped[UUID] = mapped_column()
    batch_id: Mapped[UUID] = mapped_column()
    staging_record_id: Mapped[UUID] = mapped_column()
    source_version: Mapped[str] = mapped_column(String(100), nullable=False)
    on_hand: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    reserved: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    in_transit: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    updated_from_source_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class StockSnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "canonical_stock_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            ondelete="CASCADE",
            name="fk_canonical_stock_snapshots_product_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_canonical_stock_snapshots_branch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="RESTRICT",
            name="fk_canonical_stock_snapshots_batch_same_tenant",
        ),
        CheckConstraint(
            "on_hand >= 0 AND reserved >= 0 AND in_transit >= 0",
            name="ck_canonical_stock_snapshots_values",
        ),
        Index("ix_canonical_stock_snapshots_scope_at", "tenant_id", "branch_id", "snapshot_at"),
        Index("ix_canonical_stock_snapshots_at_brin", "snapshot_at", postgresql_using="brin"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column()
    branch_id: Mapped[UUID] = mapped_column()
    product_id: Mapped[UUID] = mapped_column()
    batch_id: Mapped[UUID] = mapped_column()
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    on_hand: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    reserved: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    in_transit: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)


class InventoryMovement(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "canonical_inventory_movements"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "external_id",
            name="uq_canonical_inventory_movements_source_external",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            ondelete="CASCADE",
            name="fk_canonical_inventory_movements_product_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "inventory_lot_id"],
            ["canonical_inventory_lots.tenant_id", "canonical_inventory_lots.id"],
            ondelete="SET NULL",
            name="fk_canonical_inventory_movements_lot_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_canonical_inventory_movements_branch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            ondelete="RESTRICT",
            name="fk_canonical_inventory_movements_source_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="RESTRICT",
            name="fk_canonical_inventory_movements_batch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            ondelete="RESTRICT",
            name="fk_canonical_inventory_movements_staging_same_tenant",
        ),
        CheckConstraint(
            "movement_type IN ('receipt','sale','adjustment','transfer_in','transfer_out',"
            "'loss','damage','return','inventory','reservation','transit')",
            name="ck_canonical_inventory_movements_type",
        ),
        CheckConstraint("quantity <> 0", name="ck_canonical_inventory_movements_quantity"),
        Index("ix_canonical_inventory_movements_scope_at", "tenant_id", "branch_id", "occurred_at"),
        Index("ix_canonical_inventory_movements_at_brin", "occurred_at", postgresql_using="brin"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column()
    branch_id: Mapped[UUID] = mapped_column()
    product_id: Mapped[UUID] = mapped_column()
    inventory_lot_id: Mapped[UUID | None] = mapped_column()
    data_source_id: Mapped[UUID] = mapped_column()
    batch_id: Mapped[UUID] = mapped_column()
    staging_record_id: Mapped[UUID] = mapped_column()
    external_id: Mapped[str] = mapped_column(String(240), nullable=False)
    source_version: Mapped[str] = mapped_column(String(100), nullable=False)
    movement_type: Mapped[str] = mapped_column(String(24), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    balance_after: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accounting_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(60))
    reference_id: Mapped[str | None] = mapped_column(String(240))


class ProductPrice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "canonical_product_prices"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "external_id",
            "valid_from",
            name="uq_canonical_product_prices_source_external",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            ondelete="CASCADE",
            name="fk_canonical_product_prices_product_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_canonical_product_prices_branch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            ondelete="RESTRICT",
            name="fk_canonical_product_prices_source_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="RESTRICT",
            name="fk_canonical_product_prices_batch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "staging_record_id"],
            ["staging_records.tenant_id", "staging_records.id"],
            ondelete="RESTRICT",
            name="fk_canonical_product_prices_staging_same_tenant",
        ),
        CheckConstraint(
            "price >= 0 AND (reference_price IS NULL OR reference_price >= 0) "
            "AND (reference_cost IS NULL OR reference_cost >= 0)",
            name="ck_canonical_product_prices_values",
        ),
        Index("ix_canonical_product_prices_scope_valid", "tenant_id", "branch_id", "valid_from"),
        Index("ix_canonical_product_prices_valid_brin", "valid_from", postgresql_using="brin"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column()
    branch_id: Mapped[UUID] = mapped_column()
    product_id: Mapped[UUID] = mapped_column()
    data_source_id: Mapped[UUID] = mapped_column()
    batch_id: Mapped[UUID] = mapped_column()
    staging_record_id: Mapped[UUID] = mapped_column()
    external_id: Mapped[str] = mapped_column(String(240), nullable=False)
    source_version: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    reference_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    reference_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    decision_source: Mapped[str] = mapped_column(String(60), nullable=False, default="erp")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Promotion(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "canonical_promotions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_canonical_promotions_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "external_id",
            name="uq_canonical_promotions_source_external",
        ),
        CheckConstraint(
            "discount_type IN ('percentage','fixed','price','quantity')",
            name="ck_canonical_promotions_discount_type",
        ),
        CheckConstraint("valid_to > valid_from", name="ck_canonical_promotions_period"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
            name="fk_canonical_promotions_company_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "branch_id"],
            ["branches.tenant_id", "branches.company_id", "branches.id"],
            ondelete="CASCADE",
            name="fk_canonical_promotions_branch_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "data_source_id"],
            ["data_sources.tenant_id", "data_sources.id"],
            ondelete="RESTRICT",
            name="fk_canonical_promotions_source_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["import_batches.tenant_id", "import_batches.id"],
            ondelete="RESTRICT",
            name="fk_canonical_promotions_batch_same_tenant",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column()
    branch_id: Mapped[UUID | None] = mapped_column()
    data_source_id: Mapped[UUID] = mapped_column()
    batch_id: Mapped[UUID] = mapped_column()
    external_id: Mapped[str] = mapped_column(String(240), nullable=False)
    source_version: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(220), nullable=False)
    discount_type: Mapped[str] = mapped_column(String(24), nullable=False)
    discount_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    decision_source: Mapped[str] = mapped_column(String(60), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PromotionProduct(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "canonical_promotion_products"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "promotion_id", "product_id", name="uq_canonical_promotion_products_pair"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "promotion_id"],
            ["canonical_promotions.tenant_id", "canonical_promotions.id"],
            ondelete="CASCADE",
            name="fk_canonical_promotion_products_promotion_same_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["canonical_products.tenant_id", "canonical_products.id"],
            ondelete="CASCADE",
            name="fk_canonical_promotion_products_product_same_tenant",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    promotion_id: Mapped[UUID] = mapped_column()
    product_id: Mapped[UUID] = mapped_column()
    promotional_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
