"""Money helpers. All monetary values are Decimal, rounded half-up to 2 places."""
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def D(value) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def r2(value) -> Decimal:
    return D(value).quantize(CENT, rounding=ROUND_HALF_UP)
