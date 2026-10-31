from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, Enum, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import BillingPeriod, Money, Rate, TaxType, TimestampMixin


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    company: Mapped[str | None] = mapped_column(String(160))
    segment: Mapped[str] = mapped_column(String(20), default="small_business", nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    gstin: Mapped[str | None] = mapped_column(String(20))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="customer")


class Tax(TimestampMixin, Base):
    __tablename__ = "taxes"
    __table_args__ = (CheckConstraint("rate >= 0", name="ck_tax_rate_nonneg"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    tax_type: Mapped[TaxType] = mapped_column(Enum(TaxType, name="tax_type"), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Rate, nullable=False)
    applicability: Mapped[str] = mapped_column(String(20), default="sales", nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("sales_price >= 0", name="ck_product_price_nonneg"),
        CheckConstraint("cost_price >= 0", name="ck_product_cost_nonneg"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    product_type: Mapped[str] = mapped_column(String(20), nullable=False)  # service | software | addon | goods
    sales_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    cost_price: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    tax_id: Mapped[int | None] = mapped_column(ForeignKey("taxes.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    tax = relationship("Tax")
    variants = relationship(
        "ProductVariant", back_populates="product", cascade="all, delete-orphan", order_by="ProductVariant.id"
    )


class ProductVariant(TimestampMixin, Base):
    """An attribute value (e.g. Brand = Odoo) that adjusts the product's price by price_extra."""

    __tablename__ = "product_variants"
    __table_args__ = (UniqueConstraint("product_id", "attribute", "value", name="uq_variant_combo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    attribute: Mapped[str] = mapped_column(String(60), nullable=False)
    value: Mapped[str] = mapped_column(String(80), nullable=False)
    price_extra: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    product = relationship("Product", back_populates="variants")


class Plan(TimestampMixin, Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("min_quantity >= 1", name="ck_plan_min_qty"),
        CheckConstraint("billing_interval >= 1", name="ck_plan_interval"),
        CheckConstraint("end_date IS NULL OR start_date IS NULL OR end_date >= start_date", name="ck_plan_dates"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    billing_period: Mapped[BillingPeriod] = mapped_column(Enum(BillingPeriod, name="billing_period"), nullable=False)
    billing_interval: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    min_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)  # availability window
    end_date: Mapped[date | None] = mapped_column(Date)
    term_periods: Mapped[int | None] = mapped_column(Integer)  # default subscription length in billing periods
    auto_close: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    closable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pausable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    renewable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    lines = relationship("PlanLine", back_populates="plan", cascade="all, delete-orphan", order_by="PlanLine.id")


class PlanLine(Base):
    """Products included in a plan. unit_price overrides the catalog price when set."""

    __tablename__ = "plan_lines"
    __table_args__ = (CheckConstraint("quantity >= 1", name="ck_planline_qty"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("product_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Money)

    plan = relationship("Plan", back_populates="lines")
    product = relationship("Product")
    variant = relationship("ProductVariant")


class QuotationTemplate(TimestampMixin, Base):
    __tablename__ = "quotation_templates"
    __table_args__ = (CheckConstraint("validity_days >= 1", name="ck_tmpl_validity"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False)
    validity_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    plan = relationship("Plan")
    lines = relationship(
        "QuotationTemplateLine", back_populates="template", cascade="all, delete-orphan",
        order_by="QuotationTemplateLine.id",
    )


class QuotationTemplateLine(Base):
    __tablename__ = "quotation_template_lines"
    __table_args__ = (CheckConstraint("quantity >= 1", name="ck_tmplline_qty"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("quotation_templates.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("product_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Money)

    template = relationship("QuotationTemplate", back_populates="lines")
    product = relationship("Product")
    variant = relationship("ProductVariant")
