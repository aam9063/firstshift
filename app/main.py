"""FirstShift API entrypoint.

F01 scope: application factory, CORS for the console dev server, and /health.
No business logic yet; agents, ports and adapters arrive in later features.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app


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

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "firstshift-backend"}

    app.mount("/metrics", make_asgi_app())

    return app


app = create_app()
