"""Streamlit UI - Personal Assistant (multi-user, backed by FastAPI)."""

import sys
import os

# Ensure the project root is on sys.path so `app` is importable
# regardless of the working directory when streamlit is launched.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import datetime
import json
import requests
import streamlit as st
from app.models import Session, LinkedAccount

# --- Page config (must be first) ---
st.set_page_config(
    page_title="Personal Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="auto",
)

# --- Global styles ---
st.markdown("""
<style>
  /* ── Layout ─────────────────────────────────────────────── */
  .block-container { padding: 4rem 2.5rem 1rem !important; }

  /* ── Metrics ─────────────────────────────────────────────── */
  [data-testid="stMetric"] {
      background: var(--secondary-background-color);
      border-radius: 10px;
      padding: 1rem 1.25rem;
      border: 1px solid rgba(128,128,128,0.18);
  }

  /* ── Page header ─────────────────────────────────────────── */
  .pa-page-header {
      display: flex; align-items: center; gap: 0.5rem;
      margin-bottom: 0.25rem;
      border-left: 4px solid #4285F4;
      padding-left: 0.6rem;
  }
  .pa-page-title { font-size: 1.55rem; font-weight: 800; margin: 0; }
  .pa-page-sub   { color: #888; font-size: 0.88rem; margin-bottom: 1.5rem; }

  /* ── Sidebar user card ───────────────────────────────────── */
  .pa-user-card {
      display: flex; align-items: center; gap: 10px;
      padding: 8px 4px; margin-bottom: 4px;
  }
  .pa-avatar {
      width: 36px; height: 36px; border-radius: 50%;
      background: #4285F4; color: white;
      display: flex; align-items: center; justify-content: center;
      font-weight: 700; font-size: 1rem; flex-shrink: 0;
  }
  .pa-user-name  { font-weight: 600; font-size: 0.9rem; line-height: 1.2; }
  .pa-user-email { color: #888; font-size: 0.72rem; }

  /* ── Badges ──────────────────────────────────────────────── */
  .badge {
      display: inline-block; padding: 2px 10px; border-radius: 20px;
      font-size: 0.72rem; font-weight: 700; margin-left: 6px;
  }
  .b-blue   { background:#DBEAFE; color:#1D4ED8; }
  .b-green  { background:#DCFCE7; color:#15803D; }
  .b-yellow { background:#FEF9C3; color:#A16207; }
  .b-red    { background:#FEE2E2; color:#B91C1C; }
  .b-gray   { background:#F1F5F9; color:#475569; }

  /* Dark-mode badge overrides */
  [data-theme="dark"] .b-blue,
  [class*="dark"] .b-blue   { background:#1E3A8A; color:#93C5FD; }
  [data-theme="dark"] .b-green,
  [class*="dark"] .b-green  { background:#14532D; color:#86EFAC; }
  [data-theme="dark"] .b-yellow,
  [class*="dark"] .b-yellow { background:#713F12; color:#FDE047; }
  [data-theme="dark"] .b-red,
  [class*="dark"] .b-red    { background:#7F1D1D; color:#FCA5A5; }
  [data-theme="dark"] .b-gray,
  [class*="dark"] .b-gray   { background:#334155; color:#CBD5E1; }

  /* ── Account row ─────────────────────────────────────────── */
  .acc-row {
      display: flex; align-items: center; justify-content: space-between;
      padding: 0.75rem 1rem; border-radius: 8px;
      background: var(--secondary-background-color);
      border: 1px solid rgba(128,128,128,0.15);
      margin-bottom: 0.5rem;
  }

  /* ── Google sign-in button ───────────────────────────────── */
  .g-signin {
      display: inline-flex; align-items: center; gap: 10px;
      background: #fffcfc; color: white;
      border: none; padding: 11px 24px; border-radius: 8px;
      cursor: pointer; font-size: 0.95rem; font-weight: 600;
      text-decoration: none; width: 100%; justify-content: center;
      margin-top: 8px; box-sizing: border-box;
  }
  .g-signin:hover { background: #3367D6; color: white; }
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
PAGES     = ["Dashboard", "Calendar", "Preferences", "Accounts"]
PAGE_ICON = {"Dashboard": "📊", "Calendar": "�", "Preferences": "🔧", "Accounts": "🔗"}

with st.sidebar:
    st.markdown("## 🤖 Personal Assistant")
    st.caption("Your automated command center")
    st.divider()

    health, err = _get("/")
    if err:
        st.error("Service unavailable. Please try again later.")
        st.stop()


    if not st.session_state.get("user"):
        st.markdown("### Sign In")
        st.markdown(
            f'<a class="g-signin" href="{API}/signup">'
            '<svg width="18" height="18" viewBox="0 0 48 48">'
            '<path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>'
            '<path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>'
            '<path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>'
            '<path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.18 1.48-4.97 2.31-8.16 2.31-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>'
            '</svg> Sign in with Google</a>',
            unsafe_allow_html=True,
        )
        st.caption("Sign in securely with your Google account.")
    else:
        u = st.session_state["user"]
        letter = u["email"][0].upper()
        st.markdown(
            f'<div class="pa-user-card">'
            f'<div class="pa-avatar">{letter}</div>'
            f'<div><div class="pa-user-name">{u["email"].split("@")[0]}</div>'
            f'<div class="pa-user-email">{u["email"]}</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        if "page" not in st.session_state:
            st.session_state.page = "Dashboard"

        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        for p in PAGES:
            btn_type = "primary" if st.session_state.page == p else "secondary"
            if st.button(f"{PAGE_ICON[p]}  {p}", key=f"nav_{p}", use_container_width=True, type=btn_type):
                st.session_state.page = p
                st.rerun()

        st.divider()
        if st.button("↩  Sign out", use_container_width=True):
            _clear_session()
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

# --- Main App ---
if not st.session_state.get("user_id"):
    st.markdown(
        "<div style='text-align:center;padding:4rem 1rem'>"
        "<div style='font-size:2.2rem;font-weight:800;margin-bottom:0.4rem'>� Personal Assistant</div>"
        "<div style='color:#888;font-size:1rem'>Sign in from the sidebar to manage your Gmail, Calendar &amp; daily schedule.</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()

uid  = st.session_state["user_id"]
user = st.session_state["user"]

if "cfg" not in st.session_state:
    cfg, _ = _get("/api/config")
    st.session_state["cfg"] = cfg or {}
cfg = st.session_state["cfg"]

page = st.session_state.get("page", "Dashboard")

# --- Page header helper ---
def _ph(icon, title, subtitle=""):
    st.markdown(
        f'<div class="pa-page-header">'
        f'<span style="font-size:1.5rem">{icon}</span>'
        f'<span class="pa-page-title">{title}</span></div>',
        unsafe_allow_html=True,
    )
    if subtitle:
        st.markdown(f'<p class="pa-page-sub">{subtitle}</p>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════
if page == "Dashboard":
    _ph("📊", "Dashboard", f"Good to see you, {user['email'].split('@')[0]}.")

    # Metrics row
    with st.container(border=True):
        st.markdown("##### At a Glance")
        db = Session()
        try:
            linked_count = db.query(LinkedAccount).filter(LinkedAccount.owner_id == uid).count()
        finally:
            db.close()
        c1, c2, c3 = st.columns(3)
        sync_h = user.get("email_sync_hours") or 24
        c1.metric("📬 Email Sync",   f"Every {sync_h}h")
        c2.metric("📨 Daily Digest", user["notify_time"])
        c3.metric("📂 Accounts",     1 + linked_count)

    # Run manually
    with st.container(border=True):
        st.markdown("##### Sync Now")
        send_email_opt = st.checkbox("Send today's schedule to my email after syncing")
        if st.button("▶  Run Sync", type="primary", use_container_width=True):
            with st.spinner("Syncing…"):
                _run_payload = {"user_id": uid, "send_email": send_email_opt}
                if user.get("gmail_query"):
                    _run_payload["gmail_query"] = user["gmail_query"]
                res, err = _post("/api/run-assistant", _run_payload)
            if err:
                st.error("Something went wrong. Please try again.")
            else:
                n_mail = res['emails_processed']
                n_evt  = res['events_created']
                if n_evt:
                    st.success(f"Sync complete — {n_evt} new event(s) added to your calendar.")
                else:
                    st.success(f"Sync complete — {n_mail} email(s) reviewed, nothing new to add.")
                if res.get("details"):
                    with st.expander("View details"):
                        for item in res["details"]:
                            ico = "🗓️" if item["event_created"] else "📧"
                            col = INTENT_COLOR.get(item["intent"], "b-gray")
                            st.markdown(
                                f"{ico} **{item['subject'] or '(no subject)'}** "
                                f"<span class='badge {col}'>{item['intent'] or '?'}</span>"
                                f"<br><small style='color:#888'>{item['summary'] or ''}</small>",
                                unsafe_allow_html=True,
                            )

    # Today's schedule
    with st.container(border=True):
        hc1, hc2 = st.columns([6, 1])
        with hc1:
            st.markdown("##### 📅 Today's Schedule")
        with hc2:
            if st.button("🔄 Refresh", key="dash_refresh"):
                data, _ = _get("/api/schedule", user_id=uid)
                st.session_state["schedule"] = (data or {}).get("schedule", "")

        if "schedule" not in st.session_state:
            data, _ = _get("/api/schedule", user_id=uid)
            st.session_state["schedule"] = (data or {}).get("schedule", "")

        sched = st.session_state.get("schedule", "")
        if sched:
            st.markdown(sched)
        else:
            st.info("No events scheduled for today.")

# ══════════════════════════════════════════════════════════════════
# CALENDAR
# ══════════════════════════════════════════════════════════════════
elif page == "Calendar":
    _ph("�", "Calendar", "Your schedule at a glance.")

    cal_l, cal_r = st.columns([1, 1], gap="large")

    with cal_l:
        with st.container(border=True):
            ch1, ch2 = st.columns([5, 1])
            with ch1:
                st.markdown("##### 📅 Today's Events")
            with ch2:
                if st.button("🔄", key="cal_refresh", help="Refresh"):
                    data, _ = _get("/api/schedule", user_id=uid)
                    st.session_state["schedule"] = (data or {}).get("schedule", "")
            sched = st.session_state.get("schedule", "")
            if sched:
                st.markdown(sched)
            else:
                st.info("No events today.")

    with cal_r:
        with st.container(border=True):
            st.markdown("##### ➕ Add New Event")
            with st.form("new_event"):
                evt_title = st.text_input("Title", placeholder="Team Standup")
                evt_desc  = st.text_area(
                    "Description (include date/time)",
                    placeholder="Daily standup tomorrow at 10 AM",
                    height=110,
                )
                if st.form_submit_button("Create Event", use_container_width=True, type="primary"):
                    if evt_title:
                        res, err = _post("/api/create-event", {
                            "user_id": uid, "subject": evt_title, "description": evt_desc,
                        })
                        if err:
                            st.error("Could not create event. Please try again.")
                        else:
                            st.toast("Event created.", icon="✅")
                            data, _ = _get("/api/schedule", user_id=uid)
                            st.session_state["schedule"] = (data or {}).get("schedule", "")
                            st.rerun()
                    else:
                        st.error("Title is required.")

# ══════════════════════════════════════════════════════════════════
# PREFERENCES
# ══════════════════════════════════════════════════════════════════
elif page == "Preferences":
    _ph("🔧", "Preferences", "Manage your notification and account settings.")

    pref_l, pref_r = st.columns([3, 2], gap="large")

    with pref_l:
        with st.container(border=True):
            st.markdown("##### 🔔 Notification Settings")
            with st.form("prefs"):
                h, m = map(int, user.get("notify_time", "07:00").split(":"))
                notify_time  = st.time_input("Daily notification time", value=datetime.time(h, m))
                tz           = st.selectbox(
                    "Timezone", options=TIMEZONES,
                    index=TIMEZONES.index(user.get("timezone", "UTC"))
                    if user.get("timezone") in TIMEZONES else 0,
                )
                notify_email = st.text_input(
                    "Notification email",
                    value=user.get("notify_email") or "",
                    placeholder="you@example.com",
                )
                gmail_query_val = st.text_input(
                    "Gmail search query",
                    value=user.get("gmail_query") or cfg.get("gmail_query", ""),
                    placeholder="subject:meeting OR subject:appointment",
                    help="Emails matching this query are scanned during each sync.",
                )
                email_sync_hours_val = st.number_input(
                    "Sync interval (hours)",
                    min_value=1, max_value=720,
                    value=int(user.get("email_sync_hours") or 24),
                    step=1,
                    help="How often the system auto-syncs your emails and updates your calendar. "
                         "Each run also fetches only emails from within this time window.",
                )
                if st.form_submit_button("💾 Save Preferences", use_container_width=True, type="primary"):
                    nt_str = notify_time.strftime("%H:%M")
                    try:
                        r = requests.post(
                            f"{API}/preferences",
                            params={
                                "user_id": uid, "notify_time": nt_str,
                                "timezone": tz, "notify_email": notify_email,
                                "gmail_query": gmail_query_val,
                                "email_sync_hours": int(email_sync_hours_val),
                            },
                            timeout=10,
                        )
                        r.raise_for_status()
                        st.session_state["user"].update({
                            "notify_time": nt_str, "timezone": tz,
                            "notify_email": notify_email, "gmail_query": gmail_query_val,
                            "email_sync_hours": int(email_sync_hours_val),
                        })
                        st.toast("Settings saved.", icon="✅")
                    except Exception:
                        st.toast("Could not save settings. Please try again.", icon="❌")

    with pref_r:
        with st.container(border=True):
            st.markdown("##### 📋 Current Settings")
            st.markdown(f"**Notify Time:** &nbsp;`{user.get('notify_time', '—')}`", unsafe_allow_html=True)
            st.markdown(f"**Timezone:** &nbsp;`{user.get('timezone', '—')}`", unsafe_allow_html=True)
            notify_val = user.get("notify_email") or "_not set_"
            st.markdown(f"**Notify Email:** &nbsp;{notify_val}", unsafe_allow_html=True)
            query_val = user.get("gmail_query") or cfg.get("gmail_query") or "_default_"
            st.markdown(f"**Gmail Query:** &nbsp;`{query_val}`", unsafe_allow_html=True)
            st.markdown(f"**Sync Interval:** &nbsp;`Every {user.get('email_sync_hours', 24)}h`", unsafe_allow_html=True)
            st.markdown(f"**Account:** &nbsp;{user.get('email', '—')}", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# ACCOUNTS
# ══════════════════════════════════════════════════════════════════
elif page == "Accounts":
    _ph("🔗", "Connected Accounts", "Manage the Gmail accounts synced to your assistant.")

    if st.button("🔄 Refresh", key="accs_refresh"):
        st.session_state.pop("linked_accounts", None)

    if "linked_accounts" not in st.session_state:
        _la_data, _ = _get("/linked-accounts", user_id=uid)
        st.session_state["linked_accounts"] = _la_data or []

    linked_accounts = st.session_state["linked_accounts"]

    with st.container(border=True):
        st.markdown("##### 👤 Primary Account")
        st.markdown(
            f'<div class="acc-row">'
            f'<div><strong>{user["email"]}</strong>'
            f'<span class="badge b-blue" style="margin-left:8px">Primary</span></div>'
            f'<span style="color:#22c55e;font-size:0.82rem;font-weight:600">✓ Active</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with st.container(border=True):
        st.markdown("##### 🔗 Linked Accounts")
        if not linked_accounts:
            st.info("No linked accounts yet. Add one below.")
        else:
            for _la in linked_accounts:
                lc1, lc2 = st.columns([5, 1])
                with lc1:
                    st.markdown(
                        f'<div style="padding:6px 0"><strong>{_la["email"]}</strong></div>',
                        unsafe_allow_html=True,
                    )
                with lc2:
                    if st.button("Remove", key=f"del_{_la['id']}", type="secondary"):
                        _r = requests.delete(
                            f"{API}/linked-accounts/{_la['id']}",
                            params={"user_id": uid}, timeout=10,
                        )
                        if _r.ok:
                            st.toast("Account removed.", icon="✅")
                            st.session_state.pop("linked_accounts", None)
                            st.rerun()
                        else:
                            st.toast("Could not remove account. Please try again.", icon="❌")
    with st.container(border=True):
        st.markdown("##### ➕ Add Account")
        st.caption("Connect another Gmail account to sync all your emails in one place.")
        st.markdown(
            f'<a href="{API}/link-account?owner_id={uid}" target="_self" style="text-decoration:none;">'
            '<button style="background:#34a853;color:white;border:none;padding:10px 22px;'
            'border-radius:8px;cursor:pointer;font-size:0.95rem;font-weight:600;">'
            '➕ Connect Gmail Account</button></a>',
            unsafe_allow_html=True,
        )

