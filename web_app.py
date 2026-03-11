"""FastAPI application entry point -- registers all routers."""

import os

# Allow OAuth over plain HTTP in development (localhost). Remove in production.
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

from fastapi import FastAPI
from app.api import auth, emails, calendar, system

app = FastAPI(title="Personal Assistant", version="1.0.0")

app.include_router(auth.router)
app.include_router(emails.router)
app.include_router(calendar.router)
app.include_router(system.router)
