from datetime import date, datetime
from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class Msg(BaseModel):
    message: str
    detail: dict | None = None


# ---------- auth / users ----------
class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str
    company: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(min_length=10)
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class UserOut(ORM):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    is_demo: bool
    created_at: datetime
    last_login_at: datetime | None = None
    customer_id: int | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class StaffCreateIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str


class UserUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    is_active: bool | None = None


# ---------- customers ----------
class CustomerIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    phone: str | None = None
    company: str | None = None
    segment: str = Field(default="small_business", pattern="^(small_business|enterprise)$")
    address: str | None = None
    gstin: str | None = Field(default=None, max_length=20)


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    phone: str | None = None
    company: str | None = None
    segment: str | None = Field(default=None, pattern="^(small_business|enterprise)$")
    address: str | None = None
    gstin: str | None = Field(default=None, max_length=20)


class CustomerOut(ORM):
    id: int
    name: str
    email: str
    phone: str | None
    company: str | None
    segment: str
    address: str | None
    gstin: str | None
    user_id: int | None
    is_demo: bool
    created_at: datetime


class CustomerRow(CustomerOut):
    active_subscriptions: int = 0
    outstanding: Decimal = Decimal(0)


# ---------- taxes ----------
class TaxIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    tax_type: str = Field(pattern="^(percentage|fixed)$")
    rate: Decimal = Field(ge=0, le=100000)
    applicability: str = Field(default="sales", pattern="^(sales)$")
    description: str | None = None
    is_active: bool = True

    @field_validator("rate")
    @classmethod
    def pct_cap(cls, v, info):
        if info.data.get("tax_type") == "percentage" and v > 100:
            raise ValueError("Percentage tax cannot exceed 100")
        return v


class TaxOut(ORM):
    id: int
    name: str
    tax_type: str
    rate: Decimal
    applicability: str
    description: str | None
    is_active: bool


# ---------- products ----------
class VariantIn(BaseModel):
    id: int | None = None
    attribute: str = Field(min_length=1, max_length=60)
    value: str = Field(min_length=1, max_length=80)
    price_extra: Decimal = Field(default=Decimal(0), ge=-10_000_000, le=10_000_000)
    is_active: bool = True


class VariantOut(ORM):
    id: int
    attribute: str
    value: str
    price_extra: Decimal
    is_active: bool


class ProductIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    product_type: str = Field(pattern="^(software|addon|service|goods)$")
    sales_price: Decimal = Field(ge=0, le=100_000_000)
    cost_price: Decimal = Field(default=Decimal(0), ge=0, le=100_000_000)
    notes: str | None = None
    tax_id: int | None = None
    is_active: bool = True
    variants: list[VariantIn] = []


class ProductOut(ORM):
    id: int
    name: str
    product_type: str
    sales_price: Decimal
    cost_price: Decimal
    notes: str | None
    tax_id: int | None
    tax: TaxOut | None
    is_active: bool
    variants: list[VariantOut]
    created_at: datetime


# ---------- plans ----------
class LineIn(BaseModel):
    product_id: int
    variant_id: int | None = None
    quantity: int = Field(default=1, ge=1, le=1_000_000)
    unit_price: Decimal | None = Field(default=None, ge=0)


class LineOut(ORM):
    id: int
    product_id: int
    variant_id: int | None
    quantity: int
    unit_price: Decimal | None
    product_name: str | None = None
    variant_label: str | None = None
    effective_price: Decimal | None = None


class PlanIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = None
    billing_period: str = Field(pattern="^(daily|weekly|monthly|yearly)$")
    billing_interval: int = Field(default=1, ge=1, le=36)
    min_quantity: int = Field(default=1, ge=1)
    start_date: date | None = None
    end_date: date | None = None
    term_periods: int | None = Field(default=None, ge=1, le=1000)
    auto_close: bool = False
    closable: bool = True
    pausable: bool = False
    renewable: bool = True
    is_active: bool = True
    lines: list[LineIn] = []


class PlanOut(ORM):
    id: int
    name: str
    description: str | None
    billing_period: str
    billing_interval: int
    min_quantity: int
    start_date: date | None
    end_date: date | None
    term_periods: int | None
    auto_close: bool
    closable: bool
    pausable: bool
    renewable: bool
    is_active: bool
    lines: list[LineOut] = []
    price: Decimal = Decimal(0)
    subscription_count: int = 0


# ---------- quotation templates ----------
class TemplateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    plan_id: int
    validity_days: int = Field(default=30, ge=1, le=365)
    payment_terms_days: int = Field(default=15, ge=0, le=365)
    notes: str | None = None
    is_active: bool = True
    lines: list[LineIn] = Field(min_length=1)


class TemplateOut(ORM):
    id: int
    name: str
    plan_id: int
    plan_name: str | None = None
    validity_days: int
    payment_terms_days: int
    notes: str | None
    is_active: bool
    lines: list[LineOut] = []
