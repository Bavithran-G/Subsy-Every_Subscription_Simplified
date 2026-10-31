from fastapi import Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session


class Paging:
    def __init__(self, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200)):
        self.page, self.page_size = page, page_size


def paginate(db: Session, stmt, paging: Paging):
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.scalars(stmt.limit(paging.page_size).offset((paging.page - 1) * paging.page_size)).unique().all()
    return rows, total


def page(items, total, paging: Paging) -> dict:
    return {"items": items, "total": total, "page": paging.page, "page_size": paging.page_size}
