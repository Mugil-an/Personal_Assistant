"""Entry point for the multi-user Personal Assistant service.

Starts the APScheduler background jobs and the FastAPI web server together.

Usage:
    python run.py

The server will listen on http://localhost:8000.
API docs available at http://localhost:8000/docs
"""

import logging
import uvicorn
from scheduler import start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting scheduler...")
    start_scheduler()

    logger.info("Starting web server at http://localhost:8000")
    logger.info("API docs at http://localhost:8000/docs")

    uvicorn.run(
        "web_app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # reload=True conflicts with APScheduler
    )
