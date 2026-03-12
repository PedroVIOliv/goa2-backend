"""Uvicorn entry point for the GoA2 API server."""

import os

import uvicorn

from goa2.server.app import create_app

app = create_app()

if __name__ == "__main__":
    is_prod = os.environ.get("GOA2_ENV", "development") == "production"
    uvicorn.run(
        "goa2.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("GOA2_PORT", "8000")),
        reload=not is_prod,
    )
