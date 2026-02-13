"""Uvicorn entry point for the GoA2 API server."""

import uvicorn

from goa2.server.app import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run("goa2.main:app", host="0.0.0.0", port=8000, reload=True)
