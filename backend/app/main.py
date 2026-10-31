import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import admin, auth, catalog, customers, discounts, invoices, payments, portal, reports, subscriptions, users
from app.automation.scheduler import start_scheduler, stop_scheduler
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import internal
from app.models import Customer, Invoice, Subscription, User
from app.services.errors import DomainError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("subsy")


@asynccontextmanager
async def lifespan(_: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Subsy API", version="1.0.0", description="Every Subscription, Simplified.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origin_list, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition", "X-Response-Time"])


@app.middleware("http")
async def timing(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    response.headers["X-Response-Time"] = f"{ms:.1f}ms"
    response.headers["X-Content-Type-Options"] = "nosniff"
    if ms > 2000:
        log.warning("SLOW %s %s took %.0fms", request.method, request.url.path, ms)
    return response


@app.exception_handler(DomainError)
async def domain_error(_: Request, exc: DomainError):
    return JSONResponse({"detail": exc.message}, status_code=exc.status_code)


@app.exception_handler(IntegrityError)
async def integrity_error(_: Request, exc: IntegrityError):
    log.warning("integrity error: %s", exc.orig)
    return JSONResponse({"detail": "This change conflicts with existing data (duplicate or invalid reference)."},
                        status_code=409)


API = "/api"
for r in (auth.router, users.router, customers.router, catalog.router, subscriptions.router, invoices.router,
          payments.router, discounts.router, reports.router, portal.router, admin.router):
    app.include_router(r, prefix=API)


@app.get(f"{API}/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "app": "Subsy"}


@app.get(f"{API}/search")
def search(q: str, _: User = Depends(internal), db: Session = Depends(get_db)):
    if len(q.strip()) < 2:
        return {"customers": [], "subscriptions": [], "invoices": []}
    like = f"%{q.strip()}%"
    cs = db.scalars(select(Customer).where(or_(Customer.name.ilike(like), Customer.email.ilike(like),
                                               Customer.company.ilike(like))).limit(5)).all()
    ss = db.scalars(select(Subscription).where(Subscription.number.ilike(like)).limit(5)).all()
    ivs = db.scalars(select(Invoice).where(Invoice.number.ilike(like)).limit(5)).all()
    return {"customers": [{"id": c.id, "label": c.name, "sub": c.email} for c in cs],
            "subscriptions": [{"id": s.id, "label": s.number, "sub": f"{s.customer.name} · {s.state}"} for s in ss],
            "invoices": [{"id": i.id, "label": i.number, "sub": f"{i.customer.name} · {i.state}"} for i in ivs]}
