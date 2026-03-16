"""Auth-related routes: sign-up, OAuth callbacks, linked accounts, preferences."""

import json
import logging
import os

import requests as _requests
from fastapi import APIRouter, HTTPException, Query, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as DBSession

from app.auth_web import create_auth_flow
from app.models import Session, User, LinkedAccount, get_db

logger = logging.getLogger(__name__)
router = APIRouter()


# URLs should be configured via environment variables for production
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
STREAMLIT_URL = os.getenv("STREAMLIT_URL", "http://localhost:8501")

REDIRECT_URI       = f"{BASE_URL}/oauth/callback"
LINK_REDIRECT_URI  = f"{BASE_URL}/link-account/callback"

# ---------------------------------------------------------------------------
# Primary account sign-up
# ---------------------------------------------------------------------------

@router.get("/signup", summary="Begin Google OAuth sign-up")
def signup():
    """Redirects the user to Google's OAuth2 consent screen."""
    flow = create_auth_flow(REDIRECT_URI)
    auth_url, state = flow.authorization_url(prompt="consent", access_type="offline")
    response = RedirectResponse(auth_url)
    response.set_cookie(key="oauth_state", value=state, httponly=True, max_age=1200, samesite="lax")
    response.set_cookie(key="code_verifier", value=flow.code_verifier, httponly=True, max_age=1200, samesite="lax")
    return response


@router.get("/oauth/callback", summary="Google OAuth callback")
def oauth_callback(request: Request, db: DBSession = Depends(get_db)):
    """Google redirects here after the user grants permission."""
    error = request.query_params.get("error")
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")

    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing 'code' parameter from Google.")

    state = request.query_params.get("state")
    cookie_state = request.cookies.get("oauth_state")
    code_verifier = request.cookies.get("code_verifier")
    if not cookie_state or state != cookie_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state or session expired. Please try again.")

    try:
        flow = create_auth_flow(REDIRECT_URI, state=cookie_state)
        flow.code_verifier = code_verifier
        flow.fetch_token(authorization_response=str(request.url))
        creds = flow.credentials
    except Exception as exc:
        logger.exception("Token exchange failed")
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {exc}")

    try:
        userinfo_resp = _requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=10,
        )
        userinfo_resp.raise_for_status()
        info = userinfo_resp.json()
        user_id    = info.get("sub") or info.get("id")
        user_email = info.get("email")
        if not user_id or not user_email:
            raise ValueError(f"Incomplete profile info returned: {info}")
    except Exception as exc:
        logger.exception("Failed to fetch user profile")
        raise HTTPException(status_code=500, detail=f"Failed to fetch user profile: {exc}")

    token_dict = json.loads(creds.to_json())

    try:
        user = db.get(User, user_id)
        if not user:
            user = User(id=user_id, email=user_email, token_json=token_dict)
            logger.info("New user signed up: %s", user_email)
        else:
            user.token_json = token_dict
            logger.info("Existing user re-authenticated: %s", user_email)

        db.add(user)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Database error during sign-up")
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")

    response = RedirectResponse(f"{STREAMLIT_URL}/?user_id={user_id}")
    response.delete_cookie("oauth_state")
    response.delete_cookie("code_verifier")
    return response


# ---------------------------------------------------------------------------
# Link additional Gmail account
# ---------------------------------------------------------------------------

@router.get("/link-account", summary="Begin linking a secondary Gmail account")
def link_account(owner_id: str = Query(..., description="Primary user ID")):
    """Start a second OAuth flow so the user can grant access to another Gmail account."""
    flow = create_auth_flow(LINK_REDIRECT_URI)
    auth_url, state = flow.authorization_url(
        prompt="consent",
        access_type="offline",
        login_hint="",
    )
    response = RedirectResponse(auth_url)
    response.set_cookie(key="oauth_link_state", value=state, httponly=True, max_age=1200, samesite="lax")
    response.set_cookie(key="oauth_link_code_verifier", value=flow.code_verifier, httponly=True, max_age=1200, samesite="lax")
    response.set_cookie(key="oauth_owner_id", value=owner_id, httponly=True, max_age=1200, samesite="lax")
    return response


@router.get("/link-account/callback", summary="OAuth callback for linked account")
def link_account_callback(request: Request, db: DBSession = Depends(get_db)):
    error = request.query_params.get("error")
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")

    code  = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code:
        raise HTTPException(status_code=400, detail="Missing 'code' parameter.")

    cookie_state = request.cookies.get("oauth_link_state")
    code_verifier = request.cookies.get("oauth_link_code_verifier")
    owner_id = request.cookies.get("oauth_owner_id")

    if not cookie_state or state != cookie_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state or session expired. Please try again.")
    
    if not owner_id:
        raise HTTPException(status_code=400, detail="Missing owner ID in session. Please try again.")

    if not code_verifier:
        raise HTTPException(status_code=400, detail="Missing PKCE verifier in session. Please restart linking.")

    try:
        flow = create_auth_flow(LINK_REDIRECT_URI, state=cookie_state)
        flow.code_verifier = code_verifier
        flow.fetch_token(authorization_response=str(request.url))
        creds = flow.credentials
    except Exception as exc:
        logger.exception("Token exchange failed for linked account")
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {exc}")

    try:
        userinfo_resp = _requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=10,
        )
        userinfo_resp.raise_for_status()
        info       = userinfo_resp.json()
        account_id = info.get("sub") or info.get("id")
        email      = info.get("email")
        if not account_id or not email:
            raise ValueError(f"Incomplete profile info: {info}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch profile: {exc}")

    if account_id == owner_id:
        raise HTTPException(
            status_code=400,
            detail="This is already your primary account. Please choose a different account.",
        )

    token_dict = json.loads(creds.to_json())
    try:
        existing = db.get(LinkedAccount, account_id)
        if existing:
            existing.token_json = token_dict
            existing.owner_id   = owner_id
            existing.email      = email
        else:
            db.add(LinkedAccount(
                id=account_id, owner_id=owner_id,
                email=email, token_json=token_dict,
            ))
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")
    
    response = RedirectResponse(f"{STREAMLIT_URL}/?user_id={owner_id}&linked_account=true")
    response.delete_cookie("oauth_link_state")
    response.delete_cookie("oauth_link_code_verifier")
    response.delete_cookie("oauth_owner_id")
    return response


@router.get("/linked-accounts", summary="List linked Gmail accounts for a user")
def list_linked_accounts(user_id: str = Query(...), db: DBSession = Depends(get_db)):
    accounts = db.query(LinkedAccount).filter(LinkedAccount.owner_id == user_id).all()
    return [{"id": a.id, "email": a.email} for a in accounts]


@router.delete("/linked-accounts/{account_id}", summary="Remove a linked Gmail account")
def delete_linked_account(account_id: str, user_id: str = Query(...)):
    db = Session()
    try:
        account = db.get(LinkedAccount, account_id)
        if not account or account.owner_id != user_id:
            raise HTTPException(status_code=404, detail="Linked account not found.")
        db.delete(account)
        db.commit()
        return {"message": f"Account {account.email} removed."}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        db.close()


@router.post("/preferences", summary="Set notification time and email address")
def set_preferences(
    user_id:      str          = Query(...,     description="Your Google user ID returned after sign-up"),
    notify_time:      str          = Query("07:00", description="Daily notification time in HH:MM 24h format"),
    timezone:         str          = Query("UTC",   description="Your timezone, e.g. Asia/Kolkata"),
    notify_email:     str          = Query(...,     description="Email address to receive your daily schedule"),
    gmail_query:      str | None   = Query(None,    description="Gmail search query used when syncing emails"),
    email_sync_hours: int          = Query(24,      description="Sync interval in hours: auto-sync runs this often and looks back this far (e.g. 6 = sync every 6h, fetch last 6h of mail)"),
):
    """Save the user's notification preferences and email search query."""
    if email_sync_hours < 1:
        raise HTTPException(status_code=400, detail="email_sync_hours must be at least 1.")
    db = Session()
    try:
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found. Please sign up first.")

        notify_email_final = (notify_email or "").strip() or user.email
        gmail_query_final = gmail_query.strip() if isinstance(gmail_query, str) else gmail_query

        user.notify_time      = notify_time
        user.timezone         = timezone
        user.notify_email     = notify_email_final
        user.email_sync_hours = email_sync_hours
        if gmail_query_final is not None:
            user.gmail_query = gmail_query_final
        db.commit()
    finally:
        db.close()

    return {
        "message":          "✅ Preferences saved!",
        "notify_time":      notify_time,
        "timezone":         timezone,
        "notify_email":     notify_email_final,
        "gmail_query":      gmail_query_final,
        "email_sync_hours": email_sync_hours,
    }
