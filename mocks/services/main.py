"""The mock client systems as one FastAPI app (specs/04 section 1.2).

Run with: python -m mocks.services (uvicorn). One router per client system:
HireDesk, Nómina360, ShiftGrid, TillCloud, LearnBite. In-memory module-level
stores, seeded at startup and re-seeded by each router's /reset endpoint.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from mocks.services.routers import hiredesk, learnbite, nomina360, shiftgrid, tillcloud
from mocks.services.seed import build_seed


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    seed = build_seed()
    hiredesk.store.reset(seed)
    nomina360.store.reset(seed)
    shiftgrid.store.reset(seed)
    tillcloud.store.reset(seed)
    learnbite.store.reset(seed)
    yield


app = FastAPI(
    title="Lumbre Burger mock client systems",
    description="Mock ATS, HRIS, WFM, POS and LMS for the FirstShift prototype.",
    lifespan=lifespan,
)

for system_router in (
    hiredesk.router,
    nomina360.router,
    shiftgrid.router,
    tillcloud.router,
    learnbite.router,
):
    app.include_router(system_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "mocks"}
