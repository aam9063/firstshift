"""Uvicorn entry point: python -m mocks.services serves the mock systems."""

from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run("mocks.services.main:app", host="127.0.0.1", port=8010)
