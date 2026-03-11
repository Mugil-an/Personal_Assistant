"""Streamlit UI - Personal Assistant (multi-user, backed by FastAPI)."""

import datetime
import json
import os
import requests
import streamlit as st
from models import Session, LinkedAccount

# --- Page config (must be first) ---
st.set_page_config(
    page_title="Personal Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Global styles ---
st.markdown("""
<style>
    /* General layout */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        padding-left: 3rem;
        padding-right: 3rem;
    }
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: var(--secondary-background-color);
    }
    /* Card-like containers */
    .st-emotion-cache-1r4qj8v {
        background-color: var(--background-color);
        border-radius: 10px;
        padding: 1.5rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        border: 1px solid var(--secondary-background-color);
    }
    /* Metric styles */
    .stMetric {
        background-color: var(--secondary-background-color);
        border-radius: 8px;
        padding: 12px;
        border: 1px solid var(--secondary-background-color);
    }
    /* Custom badges */
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.78rem;
        font-weight: 600;
        margin-left: 6px;
    }
    .b-blue   { background: #DBEAFE; color: #1D4ED8; }
    .b-green  { background: #DCFCE7; color: #15803D; }
    .b-yellow { background: #FEF9C3; color: #A16207; }
    .b-red    { background: #FEE2E2; color: #B91C1C; }
    .b-gray   { background: #F1F5F9; color: #475569; }

    /* Dark theme adjustments */
    body[class*="dark"] .b-blue   { color: #60A5FA; }
    body[class*="dark"] .b-green  { color: #4ADE80; }
    body[class*="dark"] .b-yellow { color: #FACC15; }
    body[class*="dark"] .b-red    { color: #F87171; }
    body[class*="dark"] .b-gray   { color: #94A3B8; }
</style>
""", unsafe_allow_html=True)

# --- Constants ---
API = "http://localhost:8000"

# --- Server-side session file (replaces browser cookies — no JS timing issues) ---
_SESSION_FILE = os.path.join(os.path.dirname(__file__), ".user_session.json")

def _save_session(user_id: str):
    """Persist the logged-in user_id to a local file so refreshes don't log out."""
    try:
        with open(_SESSION_FILE, "w") as _f:
            json.dump({"user_id": user_id}, _f)
    except Exception:
        pass

def _clear_session():
    """Delete the persisted session file on sign-out."""
    try:
        if os.path.exists(_SESSION_FILE):
            os.remove(_SESSION_FILE)
    except Exception:
        pass

def _load_session() -> str | None:
    """Read the persisted user_id from the session file, if it exists."""
    try:
        if os.path.exists(_SESSION_FILE):
            with open(_SESSION_FILE) as _f:
                return json.load(_f).get("user_id")
    except Exception:
        pass
    return None

TIMEZONES = [
    "UTC","Asia/Kolkata","Asia/Singapore","Asia/Tokyo","Asia/Dubai",
    "Europe/London","Europe/Paris","America/New_York",
    "America/Chicago","America/Los_Angeles","Australia/Sydney",
]

INTENT_COLOR = {
    "Event Scheduling":    "b-blue",
    "Task Assignment":     "b-yellow",
    "Information Sharing": "b-gray",
    "Spam":                "b-red",
}

# --- API helpers ---

def _get(path, **params):
    try:
        r = requests.get(f"{API}{path}", params=params, timeout=15)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.ConnectionError:
        return None, "API server is offline"
    except Exception as e:
        return None, str(e)

def _post(path, payload):
    try:
        r = requests.post(f"{API}{path}", json=payload, timeout=60)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.ConnectionError:
        return None, "API server is offline"
    except Exception as e:
        return None, str(e)

# --- Session Management ---

def restore_session():
    """On every page load, restore session from the server-side session file.
    This is instant — no JS round-trip needed.
    """
    if not st.session_state.get("user_id"):
        saved_uid = _load_session()
        if saved_uid:
            _status, _err = _get("/status", user_id=saved_uid)
            if not _err and _status:
                st.session_state["user_id"] = saved_uid
                st.session_state["user"]    = _status
            else:
                # Saved session is stale (user deleted, server reset, etc.) — clean up
                _clear_session()

def handle_oauth_redirect():
    _qp = st.query_params
    if "user_id" in _qp and not st.session_state.get("user_id"):
        _uid = _qp["user_id"]
        _status, _err = _get("/status", user_id=_uid)
        if not _err and _status:
            st.session_state["user_id"] = _uid
            st.session_state["user"]    = _status
            _save_session(_uid)
        st.query_params.clear()
        st.rerun()

restore_session()
handle_oauth_redirect()

# --- Sidebar ---
with st.sidebar:
    st.title("🤖 Personal Assistant")
    st.write("Your automated command center.")
    st.divider()

    health, err = _get("/")
    if err:
        st.error("API offline. Run: `python run.py`")
        st.stop()
    st.success("API Server is Online")
    st.divider()

    if not st.session_state.get("user"):
        st.subheader("Sign In")
        st.markdown(
            f'<a href="{API}/signup" style="text-decoration:none;">'
            '<button style="width:100%;background:#4285F4;color:white;border:none;'
            'padding:10px;border-radius:8px;cursor:pointer;font-size:16px;">'
            '🚀 Sign in with Google</button></a>',
            unsafe_allow_html=True,
        )
        st.caption("You will be redirected to Google and back.")
    else:
        u = st.session_state["user"]
        st.subheader(f"Welcome, {u['email'].split('@')[0]}!")
        st.caption(f"Notify: **{u['notify_time']}** ({u['timezone']})")
        
        if 'page' not in st.session_state:
            st.session_state.page = "Dashboard"

        PAGES = {
            "Dashboard": "📊",
            "Emails": "📧",
            "Calendar": "🗓️",
            "Preferences": "⚙️",
            "Accounts": "🔗",
        }
        for page, icon in PAGES.items():
            if st.button(f"{icon} {page}", use_container_width=True):
                st.session_state.page = page
        
        st.divider()
        if st.button("Sign out", use_container_width=True):
            _clear_session()
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

# --- Main App ---
if not st.session_state.get("user_id"):
    st.info("Please sign in using the sidebar to continue.")
    st.stop()

uid  = st.session_state["user_id"]
user = st.session_state["user"]

if "cfg" not in st.session_state:
    cfg, _ = _get("/api/config")
    st.session_state["cfg"] = cfg or {}
cfg = st.session_state["cfg"]

page = st.session_state.get("page", "Dashboard")

# --- Page Content ---

if page == "Dashboard":
    st.header("📊 Dashboard")
    
    with st.container():
        st.subheader("Automation Status")
        _db_for_count = Session()
        try:
            _linked_count = _db_for_count.query(LinkedAccount).filter(LinkedAccount.owner_id == uid).count()
        finally:
            _db_for_count.close()
        _total_accounts = 1 + _linked_count
        
        ac1, ac2, ac3 = st.columns(3)
        ac1.metric("Email Fetch", "Every 1 hour")
        ac2.metric("Daily Report", user["notify_time"])
        ac3.metric("Gmail Accounts", _total_accounts)
        st.info("The assistant automatically processes emails from all linked accounts to create calendar events and sends you a daily schedule.")

    st.divider()
    
    with st.container():
        st.subheader("Run Assistant Manually")
        send_email_opt = st.checkbox("Send me today's schedule by email after running")
        if st.button("🚀 Run Now", use_container_width=True, type="primary"):
            with st.spinner("Working..."):
                res, err = _post("/api/run-assistant", {"user_id": uid, "send_email": send_email_opt})
            if err:
                st.error(err)
            else:
                st.success(f"Done! Processed **{res['emails_processed']}** emails, created **{res['events_created']}** events.")
                if res.get("details"):
                    with st.expander("See processing details"):
                        for item in res["details"]:
                            icon = "🗓️" if item["event_created"] else "📧"
                            color = INTENT_COLOR.get(item["intent"], "b-gray")
                            st.markdown(f"{icon} **{item['subject'] or '(no subject)'}** <span class='badge {color}'>{item['intent'] or '?'}</span><br><small>{item['summary'] or ''}</small>", unsafe_allow_html=True)

    st.divider()

    with st.container():
        st.subheader("Today's Schedule")
        if st.button("🔄 Refresh Schedule"):
            data, err = _get("/api/schedule", user_id=uid)
            st.session_state["schedule"] = data.get("schedule", "") if not err else ""
        
        if "schedule" not in st.session_state:
            data, err = _get("/api/schedule", user_id=uid)
            st.session_state["schedule"] = data.get("schedule", "") if not err else ""

        sched = st.session_state.get("schedule", "")
        if sched:
            st.markdown(sched)
        else:
            st.info("No events scheduled for today.")

elif page == "Emails":
    st.header("📧 Emails")
    st.caption("Fetch and analyze emails from your Gmail accounts.")

    with st.container():
        _linked, _ = _get("/linked-accounts", user_id=uid)
        _linked = _linked or []
        _account_options = {"Primary (" + user["email"] + ")": None}
        for _la in _linked:
            _account_options[_la["email"]] = _la["id"]
        
        c1, c2, c3 = st.columns([2,3,1])
        with c1:
            _selected_label = st.selectbox("Account", list(_account_options.keys()))
            _selected_account_id = _account_options[_selected_label]
        with c2:
            query = st.text_input("Search query", value=cfg.get("gmail_query", "subject:meeting"))
        with c3:
            max_r = st.number_input("Max", 1, 100, int(cfg.get("gmail_max_results", 20)))

        if st.button("🔍 Fetch & Analyze", use_container_width=True, type="primary"):
            with st.spinner("Fetching and analyzing..."):
                _payload = {"user_id": uid, "query": query, "max_results": int(max_r)}
                if _selected_account_id:
                    _payload["linked_account_id"] = _selected_account_id
                data, err = _post("/api/fetch-emails", _payload)
            st.session_state["emails"] = data if not err else None
    
    st.divider()

    emails_data = st.session_state.get("emails")
    if emails_data:
        st.success(f"Found **{emails_data['count']}** email(s).")
        for i, em in enumerate(emails_data["emails"]):
            with st.container():
                intent = em.get("intent", "")
                color = INTENT_COLOR.get(intent, "b-gray")
                
                col1, col2 = st.columns([4,1])
                with col1:
                    st.markdown(f"**{em['subject'] or '(no subject)'}** <span class='badge {color}'>{intent or 'Unknown'}</span>", unsafe_allow_html=True)
                    st.caption(f"From: {em.get('from_') or '-'} | Date: {em.get('date') or '-'} | Attachments: {len(em.get('attachments', []))}")
                
                if intent == "Event Scheduling":
                    with col2:
                        if st.button("➕ Add to Calendar", key=f"add_{i}"):
                            res, err = _post("/api/create-event", {"user_id": uid, "subject": em["subject"], "description": em.get("body_preview", "")})
                            st.success("Added!") if not err else st.error(err)
                
                if em.get("summary"):
                    st.write(f"**Summary:** {em['summary']}")
                if em.get("suggested_action"):
                    st.write(f"**Action:** {em['suggested_action']}")
                with st.expander("Preview Email Body"):
                    st.text(em.get("body_preview") or "No preview available.")
                st.divider()
    else:
        st.info("Click 'Fetch & Analyze' to see your emails.")

elif page == "Calendar":
    st.header("🗓️ Calendar")
    
    c1, c2 = st.columns(2)
    with c1:
        with st.container():
            st.subheader("Today's Events")
            if st.button("🔄 Refresh", key="cal_refresh"):
                data, err = _get("/api/schedule", user_id=uid)
                st.session_state["schedule"] = data.get("schedule", "") if not err else ""
            
            sched = st.session_state.get("schedule", "")
            if sched:
                st.markdown(sched)
            else:
                st.info("No events today.")

    with c2:
        with st.container():
            st.subheader("Add New Event")
            with st.form("new_event"):
                evt_title = st.text_input("Title", placeholder="Team Standup")
                evt_desc = st.text_area("Description (include date/time)", placeholder="Daily standup tomorrow at 10 AM")
                if st.form_submit_button("Create Event", use_container_width=True, type="primary"):
                    if evt_title:
                        res, err = _post("/api/create-event", {"user_id": uid, "subject": evt_title, "description": evt_desc})
                        if err:
                            st.error(err)
                        else:
                            st.success(res["message"])
                            data, _ = _get("/api/schedule", user_id=uid)
                            st.session_state["schedule"] = data.get("schedule", "") if data else ""
                            st.rerun()
                    else:
                        st.error("Title is required.")

elif page == "Preferences":
    st.header("⚙️ Preferences")
    st.caption("Manage your notification settings.")

    with st.container():
        with st.form("prefs"):
            current_time = user.get("notify_time", "07:00")
            h, m = map(int, current_time.split(":"))
            
            notify_time = st.time_input("Daily notification time", value=datetime.time(h, m))
            tz = st.selectbox("Timezone", options=TIMEZONES, index=TIMEZONES.index(user.get("timezone", "UTC")) if user.get("timezone") in TIMEZONES else 0)
            notify_email = st.text_input("Notification email", value=user.get("notify_email") or "", placeholder="you@example.com")
            
            if st.form_submit_button("Save Preferences", use_container_width=True, type="primary"):
                nt_str = notify_time.strftime("%H:%M")
                try:
                    r = requests.post(
                        f"{API}/preferences",
                        params={
                            "user_id":      uid,
                            "notify_time":  nt_str,
                            "timezone":     tz,
                            "notify_email": notify_email,
                        },
                        timeout=10,
                    )
                    r.raise_for_status()
                    st.success("Preferences saved!")
                    st.session_state["user"].update({"notify_time": nt_str, "timezone": tz, "notify_email": notify_email})
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to save: {e}")

elif page == "Accounts":
    st.header("🔗 Linked Accounts")
    st.caption("Manage primary and linked Gmail accounts for email processing.")

    if st.button("🔄 Refresh List"):
        st.session_state.pop("linked_accounts", None)

    if "linked_accounts" not in st.session_state:
        _la_data, _la_err = _get("/linked-accounts", user_id=uid)
        st.session_state["linked_accounts"] = _la_data or []
    
    linked_accounts = st.session_state["linked_accounts"]

    with st.container():
        st.subheader("Primary Account")
        st.markdown(f"**{user['email']}** <span class='badge b-blue'>Primary</span>", unsafe_allow_html=True)

    st.divider()

    with st.container():
        st.subheader("Linked Accounts")
        if not linked_accounts:
            st.info("No other accounts are linked.")
        
        for _la in linked_accounts:
            c1, c2 = st.columns([4,1])
            with c1:
                st.write(f"**{_la['email']}**")
            with c2:
                if st.button("Remove", key=f"del_{_la['id']}", type="secondary"):
                    _del_r = requests.delete(f"{API}/linked-accounts/{_la['id']}", params={"user_id": uid}, timeout=10)
                    if _del_r.ok:
                        st.success(f"Removed {_la['email']}")
                        st.session_state.pop("linked_accounts", None)
                        st.rerun()
                    else:
                        st.error(_del_r.text)
    
    st.divider()

    with st.container():
        st.subheader("Add another Gmail account")
        st.markdown(
            f'<a href="{API}/link-account?owner_id={uid}" style="text-decoration:none;">'
            '<button style="background:#34a853;color:white;border:none;padding:10px 18px;border-radius:8px;cursor:pointer;font-size:16px;">'
            '➕ Link a New Account</button></a>',
            unsafe_allow_html=True
        )

