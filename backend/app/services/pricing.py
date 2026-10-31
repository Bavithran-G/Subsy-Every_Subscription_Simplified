"""Single source of truth for prices and taxes, used by quotations, subscriptions, invoices and reports."""
from dataclasses import dataclass
from decimal import Decimal

from app.core.money import ZERO, D, r2
from app.models import Product, ProductVariant, Tax, TaxType
from app.services.errors import DomainError


def catalog_unit_price(product: Product, variant: ProductVariant | None) -> Decimal:
    """Product sales price plus the variant's configured price adjustment."""
    if variant is not None and variant.product_id != product.id:
        raise DomainError(f"Variant {variant.id} does not belong to product '{product.name}'")
    return r2(D(product.sales_price) + (D(variant.price_extra) if variant else ZERO))


def compute_tax(tax: Tax | None, taxable_amount: Decimal, quantity: int) -> Decimal:
    if tax is None or not tax.is_active:
        return ZERO
    if tax.tax_type == TaxType.percentage:
        return r2(D(taxable_amount) * D(tax.rate) / Decimal(100))
    # fixed tax: amount per unit
    return r2(D(tax.rate) * quantity)


@dataclass
class LineAmounts:
    gross: Decimal
    discount: Decimal
    taxable: Decimal
    tax: Decimal
    total: Decimal


def line_amounts(quantity: int, unit_price, tax: Tax | None, discount=ZERO) -> LineAmounts:
    gross = r2(D(unit_price) * quantity)
    discount = min(r2(discount), gross)
    taxable = gross - discount
    tax_amt = compute_tax(tax, taxable, quantity)
    return LineAmounts(gross, discount, taxable, tax_amt, taxable + tax_amt)
