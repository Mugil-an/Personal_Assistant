"""Entry point for the multi-user Personal Assistant service.

Starts the APScheduler background jobs and the FastAPI web server together.

Usage:
    python run.py

The server will listen on http://localhost:8000.
API docs available at http://localhost:8000/docs
"""

import logging
import os
import uvicorn
from app.scheduler import start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting scheduler...")
    start_scheduler()

    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting web server at http://0.0.0.0:{port}")
    logger.info(f"API docs at http://0.0.0.0:{port}/docs")

    uvicorn.run(
        "web_app:app",
        host="0.0.0.0",
        port=port,
        reload=False,  # reload=True conflicts with APScheduler
    )
