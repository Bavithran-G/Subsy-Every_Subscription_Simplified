from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.util import Paging, page, paginate
from app.core.db import get_db
from app.core.deps import admin_only, internal
from app.core.money import r2
from app.models import (
    Plan, PlanLine, Product, ProductVariant, QuotationTemplate, QuotationTemplateLine, Subscription, Tax, User,
)
from app.schemas.common import (
    LineIn, LineOut, Page, PlanIn, PlanOut, ProductIn, ProductOut, TaxIn, TaxOut, TemplateIn, TemplateOut,
)
from app.services.common import audit
from app.services.pricing import catalog_unit_price

router = APIRouter(tags=["catalog"])


# ---------------- taxes ----------------
@router.get("/taxes", response_model=list[TaxOut])
def list_taxes(_: User = Depends(internal), db: Session = Depends(get_db)):
    return db.scalars(select(Tax).order_by(Tax.name)).all()


@router.post("/taxes", response_model=TaxOut, status_code=201)
def create_tax(data: TaxIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    if db.scalar(select(Tax.id).where(func.lower(Tax.name) == data.name.lower())):
        raise HTTPException(409, "A tax with this name already exists")
    t = Tax(**data.model_dump())
    db.add(t)
    db.flush()
    audit(db, user.id, "tax.create", "tax", t.id, rate=str(t.rate))
    db.commit()
    return t


@router.put("/taxes/{tax_id}", response_model=TaxOut)
def update_tax(tax_id: int, data: TaxIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    t = db.get(Tax, tax_id)
    if not t:
        raise HTTPException(404, "Tax not found")
    for k, v in data.model_dump().items():
        setattr(t, k, v)
    audit(db, user.id, "tax.update", "tax", t.id, rate=str(t.rate))
    db.commit()
    return t


# ---------------- products ----------------
def _validate_variants(variants):
    seen = set()
    for v in variants:
        key = (v.attribute.strip().lower(), v.value.strip().lower())
        if key in seen:
            raise HTTPException(422, f"Duplicate variant {v.attribute}: {v.value}")
        seen.add(key)


def _apply_product(db: Session, p: Product, data: ProductIn):
    if data.tax_id and not db.get(Tax, data.tax_id):
        raise HTTPException(422, "Tax not found")
    _validate_variants(data.variants)
    for k in ("name", "product_type", "sales_price", "cost_price", "notes", "tax_id", "is_active"):
        setattr(p, k, getattr(data, k))
    existing = {v.id: v for v in p.variants}
    keep = set()
    for vin in data.variants:
        if vin.id and vin.id in existing:
            v = existing[vin.id]
            v.attribute, v.value, v.price_extra, v.is_active = (vin.attribute.strip(), vin.value.strip(),
                                                                vin.price_extra, vin.is_active)
            keep.add(v.id)
        else:
            p.variants.append(ProductVariant(attribute=vin.attribute.strip(), value=vin.value.strip(),
                                             price_extra=vin.price_extra, is_active=vin.is_active))
    for vid, v in existing.items():
        if vid not in keep:
            v.is_active = False  # never hard-delete: historical lines may reference it
    if data.sales_price + min([v.price_extra for v in data.variants] + [Decimal(0)]) < 0:
        raise HTTPException(422, "A variant adjustment would make the price negative")


@router.get("/products", response_model=Page[ProductOut])
def list_products(q: str | None = None, active: bool | None = None, product_type: str | None = None,
                  paging: Paging = Depends(), _: User = Depends(internal), db: Session = Depends(get_db)):
    stmt = select(Product).options(selectinload(Product.variants), selectinload(Product.tax)).order_by(Product.name)
    if q:
        stmt = stmt.where(or_(Product.name.ilike(f"%{q}%"), Product.notes.ilike(f"%{q}%")))
    if active is not None:
        stmt = stmt.where(Product.is_active.is_(active))
    if product_type:
        stmt = stmt.where(Product.product_type == product_type)
    rows, total = paginate(db, stmt, paging)
    return page(rows, total, paging)


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, _: User = Depends(internal), db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    return p


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(data: ProductIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    p = Product()
    _apply_product(db, p, data)
    db.add(p)
    db.flush()
    audit(db, user.id, "product.create", "product", p.id)
    db.commit()
    return p


@router.put("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, data: ProductIn, user: User = Depends(admin_only),
                   db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    _apply_product(db, p, data)
    audit(db, user.id, "product.update", "product", p.id)
    db.commit()
    db.refresh(p)
    return p


# ---------------- plans ----------------
def line_out(l) -> LineOut:
    o = LineOut.model_validate(l)
    o.product_name = l.product.name
    o.variant_label = f"{l.variant.attribute}: {l.variant.value}" if l.variant else None
    o.effective_price = l.unit_price if l.unit_price is not None else catalog_unit_price(l.product, l.variant)
    return o


def plan_out(p: Plan, count: int = 0) -> PlanOut:
    o = PlanOut.model_validate(p)
    o.lines = [line_out(l) for l in p.lines]
    o.price = r2(sum((l.effective_price * l.quantity for l in o.lines), Decimal(0)))
    o.subscription_count = count
    return o


def _check_lines(db: Session, lines: list[LineIn]):
    for l in lines:
        prod = db.get(Product, l.product_id)
        if not prod:
            raise HTTPException(422, f"Product {l.product_id} not found")
        if l.variant_id:
            v = db.get(ProductVariant, l.variant_id)
            if not v or v.product_id != l.product_id:
                raise HTTPException(422, f"Variant {l.variant_id} does not belong to product '{prod.name}'")


def _apply_plan(db: Session, p: Plan, data: PlanIn):
    if data.start_date and data.end_date and data.end_date < data.start_date:
        raise HTTPException(422, "Availability end date must be on or after the start date")
    _check_lines(db, data.lines)
    for k, v in data.model_dump(exclude={"lines"}).items():
        setattr(p, k, v)
    p.lines.clear()
    db.flush()
    for l in data.lines:
        p.lines.append(PlanLine(**l.model_dump()))


@router.get("/plans", response_model=list[PlanOut])
def list_plans(active: bool | None = None, _: User = Depends(internal), db: Session = Depends(get_db)):
    stmt = select(Plan).options(selectinload(Plan.lines).selectinload(PlanLine.product),
                                selectinload(Plan.lines).selectinload(PlanLine.variant)).order_by(Plan.name)
    if active is not None:
        stmt = stmt.where(Plan.is_active.is_(active))
    counts = dict(db.execute(select(Subscription.plan_id, func.count()).group_by(Subscription.plan_id)).all())
    return [plan_out(p, counts.get(p.id, 0)) for p in db.scalars(stmt).all()]


@router.get("/plans/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: int, _: User = Depends(internal), db: Session = Depends(get_db)):
    p = db.get(Plan, plan_id)
    if not p:
        raise HTTPException(404, "Plan not found")
    return plan_out(p)


@router.post("/plans", response_model=PlanOut, status_code=201)
def create_plan(data: PlanIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    if db.scalar(select(Plan.id).where(func.lower(Plan.name) == data.name.lower())):
        raise HTTPException(409, "A plan with this name already exists")
    p = Plan()
    db.add(p)
    _apply_plan(db, p, data)
    db.flush()
    audit(db, user.id, "plan.create", "plan", p.id)
    db.commit()
    db.refresh(p)
    return plan_out(p)


@router.put("/plans/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: int, data: PlanIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    p = db.get(Plan, plan_id)
    if not p:
        raise HTTPException(404, "Plan not found")
    _apply_plan(db, p, data)
    audit(db, user.id, "plan.update", "plan", p.id)
    db.commit()
    db.refresh(p)
    return plan_out(p)


# ---------------- quotation templates ----------------
def template_out(t: QuotationTemplate) -> TemplateOut:
    o = TemplateOut.model_validate(t)
    o.plan_name = t.plan.name
    o.lines = [line_out(l) for l in t.lines]
    return o


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(active: bool | None = None, plan_id: int | None = Query(None), _: User = Depends(internal),
                   db: Session = Depends(get_db)):
    stmt = select(QuotationTemplate).order_by(QuotationTemplate.name)
    if active is not None:
        stmt = stmt.where(QuotationTemplate.is_active.is_(active))
    if plan_id:
        stmt = stmt.where(QuotationTemplate.plan_id == plan_id)
    return [template_out(t) for t in db.scalars(stmt).all()]


def _apply_template(db: Session, t: QuotationTemplate, data: TemplateIn):
    if not db.get(Plan, data.plan_id):
        raise HTTPException(422, "Plan not found")
    _check_lines(db, data.lines)
    for k, v in data.model_dump(exclude={"lines"}).items():
        setattr(t, k, v)
    t.lines.clear()
    db.flush()
    for l in data.lines:
        t.lines.append(QuotationTemplateLine(**l.model_dump()))


@router.post("/templates", response_model=TemplateOut, status_code=201)
def create_template(data: TemplateIn, user: User = Depends(internal), db: Session = Depends(get_db)):
    if db.scalar(select(QuotationTemplate.id).where(func.lower(QuotationTemplate.name) == data.name.lower())):
        raise HTTPException(409, "A template with this name already exists")
    t = QuotationTemplate()
    db.add(t)
    _apply_template(db, t, data)
    db.flush()
    audit(db, user.id, "template.create", "template", t.id)
    db.commit()
    db.refresh(t)
    return template_out(t)


@router.put("/templates/{template_id}", response_model=TemplateOut)
def update_template(template_id: int, data: TemplateIn, user: User = Depends(internal),
                    db: Session = Depends(get_db)):
    t = db.get(QuotationTemplate, template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    _apply_template(db, t, data)
    audit(db, user.id, "template.update", "template", t.id)
    db.commit()
    db.refresh(t)
    return template_out(t)
