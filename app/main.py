"""FirstShift API entrypoint.

F01 scope: application factory, CORS for the console dev server, and /health.
F06 (T5): the HireDesk webhook router and the simulator message listing are
wired with a request-scoped session dependency (app/api/deps.py).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.api.events_stream import router as events_stream_router
from app.api.sim import router as sim_router
from app.api.simulator import router as simulator_router
from app.api.webhooks import router as webhooks_router


def create_app() -> FastAPI:
    app = FastAPI(title="FirstShift API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(webhooks_router)
    app.include_router(simulator_router)
    app.include_router(sim_router)
    app.include_router(events_stream_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "firstshift-backend"}

    app.mount("/metrics", make_asgi_app())

    return app


app = create_app()
