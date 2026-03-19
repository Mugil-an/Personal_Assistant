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
  :root {
                        --pa-bg: var(--background-color);
                        --pa-panel: var(--secondary-background-color);
                        --pa-panel-alt: color-mix(in srgb, var(--secondary-background-color) 85%, var(--background-color));
                        --pa-text: var(--text-color);
                        --pa-muted: color-mix(in srgb, var(--text-color) 56%, transparent);
                        --pa-line: color-mix(in srgb, var(--text-color) 16%, transparent);
            --pa-brand: #1e7bff;
            --pa-brand-2: #0da3c8;
            --pa-brand-dark: #145fca;
            --pa-success: #16a34a;
            --pa-warning: #f97316;
            --pa-danger: #dc2626;
                        --pa-shadow: 0 8px 22px rgba(0, 0, 0, 0.18);
                        --pa-sidebar: linear-gradient(180deg, color-mix(in srgb, var(--secondary-background-color) 92%, var(--background-color)) 0%, var(--secondary-background-color) 100%);
                        --pa-hero: linear-gradient(145deg, color-mix(in srgb, var(--secondary-background-color) 80%, var(--background-color)) 0%, var(--secondary-background-color) 100%);
  }

  [data-testid="stAppViewContainer"] {
      background:
        radial-gradient(circle at 12% -8%, rgba(13, 163, 200, 0.14), transparent 36%),
        radial-gradient(circle at 88% 0%, rgba(15, 95, 214, 0.14), transparent 42%),
        var(--pa-bg);
  }

  [data-testid="stSidebar"] {
      border-right: 1px solid var(--pa-line);
      background: var(--pa-sidebar);
  }

  [data-testid="stSidebar"] * {
      color: var(--pa-text) !important;
  }

  [data-testid="stSidebar"] .stButton > button {
      width: 100%;
      text-align: left;
      justify-content: flex-start;
      border-radius: 10px;
      border: 1px solid var(--pa-line);
      background: color-mix(in srgb, var(--pa-panel) 78%, transparent);
      color: var(--pa-text) !important;
      box-shadow: none;
      padding: 0.52rem 0.7rem;
  }

  [data-testid="stSidebar"] .stButton > button[kind="primary"] {
      background: linear-gradient(145deg, var(--pa-brand) 0%, var(--pa-brand-dark) 100%) !important;
      border-color: var(--pa-brand-dark) !important;
      color: #ffffff !important;
      box-shadow: 0 8px 18px rgba(30, 123, 255, 0.22);
  }

  [data-testid="stSidebar"] .stButton > button[kind="secondary"] {
      background: color-mix(in srgb, var(--pa-panel) 84%, transparent) !important;
      border-color: var(--pa-line) !important;
      color: var(--pa-text) !important;
  }

  [data-testid="stSidebar"] .stButton > button:hover {
      transform: translateY(0);
      border-color: color-mix(in srgb, var(--pa-brand) 45%, var(--pa-line));
      box-shadow: 0 6px 14px rgba(30, 123, 255, 0.14);
  }

  .block-container {
      max-width: 1200px;
      padding: 2.3rem 2.1rem 1.4rem !important;
  }

  h1, h2, h3, h4, h5, h6, p, label, span, div {
      color: var(--pa-text);
  }

  [data-testid="stAppViewContainer"] p,
  [data-testid="stAppViewContainer"] li,
  [data-testid="stAppViewContainer"] small {
      color: var(--pa-text);
  }

  [data-testid="stVerticalBlock"] > div {
      animation: paRise 0.42s ease both;
  }

  [data-testid="stVerticalBlock"] > div:nth-child(1) { animation-delay: 0.02s; }
  [data-testid="stVerticalBlock"] > div:nth-child(2) { animation-delay: 0.08s; }
  [data-testid="stVerticalBlock"] > div:nth-child(3) { animation-delay: 0.14s; }
  [data-testid="stVerticalBlock"] > div:nth-child(4) { animation-delay: 0.20s; }
  [data-testid="stVerticalBlock"] > div:nth-child(5) { animation-delay: 0.26s; }

  @keyframes paRise {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
  }

  [data-testid="stMetric"] {
      background: linear-gradient(180deg, var(--pa-panel) 0%, var(--pa-panel-alt) 100%);
      border-radius: 14px;
      padding: 1rem 1.1rem;
      border: 1px solid var(--pa-line);
      box-shadow: var(--pa-shadow);
  }

  [data-testid="stMetricValue"] {
      font-size: 1.35rem;
      color: var(--pa-text);
  }

  [data-testid="stMetricLabel"] {
      color: var(--pa-muted);
      font-weight: 600;
  }

  div[data-testid="stForm"],
  div[data-testid="stContainer"] {
      border-radius: 14px;
  }

  .stButton > button,
  .stDownloadButton > button,
  [data-testid="baseButton-primary"],
  [data-testid="baseButton-secondary"] {
      border-radius: 10px;
      border: 1px solid rgba(30, 123, 255, 0.28);
      transition: all 0.18s ease;
      font-weight: 600;
  }

  button[kind="primary"] {
      background: var(--pa-brand) !important;
      border-color: var(--pa-brand-dark) !important;
      color: #ffffff !important;
  }

    .stForm .stFormSubmitButton > button[kind="primary"],
    .stFormSubmitButton > button[kind="primary"],
    div[data-testid="stFormSubmitButton"] > button,
    div[data-testid="stFormSubmitButton"] button,
    div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] > button,
    div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button {
      background: var(--pa-brand) !important;
      border-color: var(--pa-brand-dark) !important;
      color: #ffffff !important;
      box-shadow: 0 8px 18px rgba(30, 123, 255, 0.2);
  }

  button[kind="primary"]:hover {
      background: var(--pa-brand-dark) !important;
  }

    .stForm .stFormSubmitButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button[kind="primary"]:hover,
    div[data-testid="stFormSubmitButton"] > button:hover,
    div[data-testid="stFormSubmitButton"] button:hover,
    div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] > button:hover,
    div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button:hover {
      background: var(--pa-brand-dark) !important;
      border-color: var(--pa-brand-dark) !important;
  }

  .stButton > button:hover,
  .stDownloadButton > button:hover,
  [data-testid="baseButton-primary"]:hover,
  [data-testid="baseButton-secondary"]:hover {
      transform: translateY(-1px);
      box-shadow: 0 8px 18px rgba(30, 123, 255, 0.2);
      border-color: rgba(30, 123, 255, 0.4);
  }

  .pa-page-header {
      padding: 1rem 1.05rem;
      border-radius: 14px;
      border: 1px solid var(--pa-line);
      box-shadow: var(--pa-shadow);
    background: linear-gradient(115deg, var(--pa-panel) 0%, var(--pa-panel-alt) 100%);
      margin-bottom: 0.25rem;
      display: flex;
      align-items: center;
      gap: 0.65rem;
  }

  .pa-page-title {
      font-size: 1.5rem;
      font-weight: 800;
      margin: 0;
      letter-spacing: 0.2px;
  }

  .pa-page-sub {
      color: var(--pa-muted);
      font-size: 0.9rem;
      margin: 0.35rem 0 1.3rem;
      padding-left: 0.2rem;
  }

  .pa-auth-hero {
      text-align: center;
      padding: 4.2rem 1rem;
      border: 1px solid var(--pa-line);
      border-radius: 16px;
      box-shadow: var(--pa-shadow);
    background: var(--pa-hero);
      max-width: 780px;
      margin: 2rem auto 0;
  }

  .pa-auth-title {
      font-size: 2.2rem;
      font-weight: 850;
      margin-bottom: 0.55rem;
    color: var(--pa-text);
      letter-spacing: 0.2px;
  }

  .pa-auth-sub {
      color: var(--pa-muted);
      font-size: 1rem;
      max-width: 550px;
      margin: 0 auto;
      line-height: 1.45;
  }

  .pa-user-card {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 8px;
      margin-bottom: 2px;
      border-radius: 10px;
      border: 1px solid var(--pa-line);
    background: color-mix(in srgb, var(--pa-panel) 78%, transparent);
  }

  .pa-avatar {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: linear-gradient(160deg, var(--pa-brand) 0%, var(--pa-brand-2) 100%);
      color: white;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 1rem;
      flex-shrink: 0;
  }

  .pa-user-name { font-weight: 650; font-size: 0.9rem; line-height: 1.2; }
  .pa-user-email { color: var(--pa-muted); font-size: 0.74rem; }

  .badge {
      display: inline-block;
      padding: 2px 10px;
      border-radius: 20px;
      font-size: 0.72rem;
      font-weight: 700;
      margin-left: 6px;
      border: 1px solid rgba(0, 0, 0, 0.06);
  }

  .b-blue   { background:#d8ecff; color:#0b55b5; }
  .b-green  { background:#dcfce7; color:#127a3a; }
  .b-yellow { background:#ffedd5; color:#c2410c; }
  .b-red    { background:#fee2e2; color:#b91c1c; }
  .b-gray   { background:#e2e8f0; color:#334155; }

  .pa-icon {
      width: 28px;
      height: 28px;
      border-radius: 8px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: #ffffff;
      font-size: 0.92rem;
      font-weight: 700;
      box-shadow: 0 7px 16px rgba(2, 16, 49, 0.22);
      border: 1px solid rgba(255, 255, 255, 0.08);
  }

  .i-blue { background: linear-gradient(145deg, #1e7bff 0%, #0da3c8 100%); }
  .i-green { background: linear-gradient(145deg, #16a34a 0%, #15803d 100%); }
  .i-orange { background: linear-gradient(145deg, #f97316 0%, #ea580c 100%); }
  .i-red { background: linear-gradient(145deg, #ef4444 0%, #b91c1c 100%); }

  .pa-kpi-strip {
      display: grid;
      grid-template-columns: repeat(4, minmax(120px, 1fr));
      gap: 0.65rem;
      margin-bottom: 0.95rem;
  }

  .pa-kpi-card {
      border: 1px solid var(--pa-line);
      border-radius: 12px;
      padding: 0.75rem 0.8rem;
      background: linear-gradient(180deg, var(--pa-panel) 0%, var(--pa-panel-alt) 100%);
      box-shadow: var(--pa-shadow);
  }

  .pa-kpi-label {
      font-size: 0.73rem;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      color: var(--pa-muted);
      margin-bottom: 0.2rem;
      font-weight: 700;
  }

  .pa-kpi-value {
      font-size: 1.05rem;
      font-weight: 800;
      color: var(--pa-text);
      line-height: 1.25;
  }

  .pa-kpi-trend {
      margin-top: 0.18rem;
      font-size: 0.76rem;
      font-weight: 650;
  }

  .trend-up { color: var(--pa-success); }
  .trend-mid { color: var(--pa-warning); }
  .trend-down { color: var(--pa-danger); }

  .pa-table-head {
      display: grid;
      gap: 10px;
      grid-template-columns: 2.7fr 1.3fr 1.1fr 1.4fr 1fr;
      margin-bottom: 0.45rem;
      color: var(--pa-muted);
      font-size: 0.76rem;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      font-weight: 700;
      padding: 0 0.2rem;
  }

  .pa-row-sep {
      border-top: 1px solid var(--pa-line);
      margin: 0.38rem 0 0.45rem;
  }

  .pa-cell-meta {
      color: var(--pa-muted);
      font-size: 0.75rem;
      margin-top: 0.1rem;
  }

  .acc-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.82rem 1rem;
      border-radius: 10px;
    background: linear-gradient(180deg, var(--pa-panel) 0%, var(--pa-panel-alt) 100%);
      border: 1px solid var(--pa-line);
      margin-bottom: 0.55rem;
  }

  .g-signin {
      display: inline-flex;
      align-items: center;
      gap: 10px;
    background: var(--pa-panel);
    color: var(--pa-text);
      border: 1px solid rgba(24, 49, 95, 0.15);
      padding: 11px 24px;
      border-radius: 10px;
      cursor: pointer;
      font-size: 0.95rem;
      font-weight: 600;
      text-decoration: none;
      width: 100%;
      justify-content: center;
      margin-top: 8px;
      box-sizing: border-box;
      transition: all 0.2s ease;
  }

  .g-signin:hover {
      background: var(--pa-panel-alt);
      color: var(--pa-brand-dark);
      border-color: rgba(30, 123, 255, 0.4);
      box-shadow: 0 8px 18px rgba(30, 123, 255, 0.16);
  }

  .pa-link-btn {
      background: var(--pa-brand);
      color: white !important;
      border: none;
      padding: 10px 22px;
      border-radius: 10px;
      cursor: pointer;
      font-size: 0.95rem;
      font-weight: 600;
      transition: all 0.2s ease;
  }

  .pa-link-btn:hover {
      background: var(--pa-brand-dark);
  }

  @media (max-width: 900px) {
      .block-container {
          padding: 1.2rem 1rem 1.1rem !important;
      }
      .pa-page-title {
          font-size: 1.2rem;
      }
      .pa-auth-title {
          font-size: 1.65rem;
      }
      .pa-kpi-strip {
          grid-template-columns: repeat(2, minmax(120px, 1fr));
      }
      .pa-table-head {
          display: none;
      }
  }
</style>
""", unsafe_allow_html=True)

# --- Constants ---
API = os.getenv("API_BASE_URL", "http://localhost:8000")
PUBLIC_API = os.getenv("PUBLIC_API_BASE_URL", API)

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

CATEGORY_COLOR = {
    "Event": "b-blue",
    "Promotion": "b-yellow",
    "Personal": "b-green",
    "Important": "b-red",
}

PRIORITY_COLOR = {
    "High": "b-red",
    "Medium": "b-yellow",
    "Low": "b-gray",
}

# --- API helpers ---

def _get(path, **params):
    try:
        r = requests.get(f"{API}{path}", params=params, timeout=15)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.ConnectionError:
        return None, "API server is offline"
    except requests.exceptions.HTTPError as e:
        try:
            detail = r.json().get("detail")
        except Exception:
            detail = None
        return None, detail or str(e)
    except Exception as e:
        return None, str(e)

def _post(path, payload):
    try:
        # Long-running sync can exceed 60s when parsing many emails.
        r = requests.post(f"{API}{path}", json=payload, timeout=(10, 300))
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.ConnectionError:
        return None, "API server is offline"
    except requests.exceptions.ReadTimeout:
        return None, "Request timed out while server is still processing. Please wait and retry in a moment."
    except requests.exceptions.HTTPError as e:
        try:
            detail = r.json().get("detail")
        except Exception:
            detail = None
        return None, detail or str(e)
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
PAGES     = ["Dashboard", "Calendar", "Preferences", "Senders", "Accounts"]
PAGE_ICON = {"Dashboard": "◈", "Calendar": "◴", "Preferences": "⚙", "Senders": "◎", "Accounts": "⛓"}

with st.sidebar:
    st.markdown("## Personal Assistant")
    st.caption("Automation cockpit for email and calendar")
    st.divider()

    health, err = _get("/")
    if err:
        st.error("Service unavailable. Please try again later.")
        st.stop()


    if not st.session_state.get("user"):
        st.markdown("### Sign In")
        st.markdown(
            f'<a class="g-signin" href="{PUBLIC_API}/signup">'
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
        "<div class='pa-auth-hero'>"
        "<div class='pa-auth-title'>Personal Assistant</div>"
        "<div class='pa-auth-sub'>Sign in from the sidebar to control Gmail sync, calendar scheduling, and your daily planning workflow from one place.</div>"
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
def _icon_chip(symbol: str, tone: str = "blue") -> str:
    return f"<span class='pa-icon i-{tone}'>{symbol}</span>"


def _kpi_strip(items: list[dict]):
    cards = []
    for item in items:
        cards.append(
            f"<div class='pa-kpi-card'>"
            f"<div class='pa-kpi-label'>{item['label']}</div>"
            f"<div class='pa-kpi-value'>{item['value']}</div>"
            f"<div class='pa-kpi-trend {item['trend_class']}'>{item['trend']}</div>"
            f"</div>"
        )
    st.markdown(f"<div class='pa-kpi-strip'>{''.join(cards)}</div>", unsafe_allow_html=True)


def _ph(icon, title, subtitle=""):
    st.markdown(
        f'<div class="pa-page-header">'
        f"{icon}"
        f'<span class="pa-page-title">{title}</span></div>',
        unsafe_allow_html=True,
    )
    if subtitle:
        st.markdown(f'<p class="pa-page-sub">{subtitle}</p>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════
if page == "Dashboard":
    _ph(_icon_chip("◈", "blue"), "Dashboard", f"Good to see you, {user['email'].split('@')[0]}.")

    # Fetch linked accounts via API if not already in session state
    if "linked_accounts" not in st.session_state:
        _la_data, _err = _get("/linked-accounts", user_id=uid)
        st.session_state["linked_accounts"] = _la_data or []
        if _err:
                st.error(f"Sync failed: {err}")

    linked_count = len(st.session_state.get("linked_accounts", []))
    sync_h = int(user.get("email_sync_hours") or 24)
    digest_hour = int((user.get("notify_time") or "07:00").split(":")[0])
    account_total = 1 + linked_count
    tz_value = user.get("timezone") or "UTC"

    _kpi_strip([
        {
            "label": "Sync Interval",
            "value": f"Every {sync_h}h",
            "trend": "▲ Fast" if sync_h <= 6 else ("→ Stable" if sync_h <= 24 else "▼ Slower"),
            "trend_class": "trend-up" if sync_h <= 6 else ("trend-mid" if sync_h <= 24 else "trend-down"),
        },
        {
            "label": "Digest Window",
            "value": user.get("notify_time", "07:00"),
            "trend": "▲ Morning" if digest_hour < 11 else "→ Scheduled",
            "trend_class": "trend-up" if digest_hour < 11 else "trend-mid",
        },
        {
            "label": "Total Accounts",
            "value": str(account_total),
            "trend": "▲ Multi-account" if account_total > 1 else "→ Single account",
            "trend_class": "trend-up" if account_total > 1 else "trend-mid",
        },
        {
            "label": "Timezone",
            "value": tz_value,
            "trend": "→ Active profile",
            "trend_class": "trend-mid",
        },
    ])

    # Metrics row
    with st.container(border=True):
        st.markdown(f"##### {_icon_chip('◍', 'blue')} At a Glance", unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("📬 Email Sync",   f"Every {sync_h}h")
        c2.metric("📨 Daily Digest", user["notify_time"])
        c3.metric("📂 Accounts",     1 + linked_count)

    # Run manually
    with st.container(border=True):
        st.markdown(f"##### {_icon_chip('▶', 'green')} Sync Now", unsafe_allow_html=True)
        send_email_opt = st.checkbox("Send today's schedule to my email after syncing")
        if st.button("▶  Run Sync", type="primary", use_container_width=True):
            with st.spinner("Syncing…"):
                _run_payload = {"user_id": uid, "send_email": send_email_opt}
                if user.get("gmail_query"):
                    _run_payload["gmail_query"] = user["gmail_query"]
                res, err = _post("/api/run-assistant", _run_payload)
            if err:
                st.error(f"Sync failed: {err}")
            else:
                n_mail = int(res.get("emails_processed", len(res.get("details", []))))
                n_evt  = int(res.get("events_created", 0))
                if n_evt:
                    st.success(f"Sync complete — {n_evt} new event(s) added to your calendar.")
                elif n_mail > 0:
                    st.success(f"Sync complete — {n_mail} email(s) reviewed. Only important/scheduled emails are added to calendar.")
                else:
                    st.info(
                        "✓ Sync complete. No emails found in your mailbox.\n\n"
                        "Tip: Use the **Senders** page to prioritize important senders."
                    )
                if res.get("details"):
                    with st.expander("View details"):
                        details = sorted(
                            res["details"],
                            key=lambda item: item.get("priority_score", 0),
                            reverse=True,
                        )
                        for item in details:
                            ico = "🗓️" if item["event_created"] else "📧"
                            intent_col = INTENT_COLOR.get(item["intent"], "b-gray")
                            category_col = CATEGORY_COLOR.get(item.get("category"), "b-gray")
                            priority_col = PRIORITY_COLOR.get(item.get("priority"), "b-gray")
                            st.markdown(
                                f"{ico} **{item['subject'] or '(no subject)'}** "
                                f"<span class='badge {priority_col}'>{item.get('priority') or '?'}</span>"
                                f"<span class='badge {category_col}'>{item.get('category') or '?'}</span>"
                                f"<span class='badge {intent_col}'>{item['intent'] or '?'}</span>"
                                f"<br><small style='color:#888'>{item['summary'] or ''}</small>",
                                unsafe_allow_html=True,
                            )

    # Today's schedule
    with st.container(border=True):
        hc1, hc2 = st.columns([6, 1])
        with hc1:
            st.markdown(f"##### {_icon_chip('◷', 'orange')} Today's Schedule", unsafe_allow_html=True)
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
    _ph(_icon_chip("◴", "blue"), "Calendar", "Your schedule at a glance.")

    cal_l, cal_r = st.columns([1, 1], gap="large")

    with cal_l:
        with st.container(border=True):
            ch1, ch2 = st.columns([5, 1])
            with ch1:
                st.markdown(f"##### {_icon_chip('◷', 'orange')} Today's Events", unsafe_allow_html=True)
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
            st.markdown(f"##### {_icon_chip('+', 'green')} Add New Event", unsafe_allow_html=True)
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
    _ph(_icon_chip("⚙", "orange"), "Preferences", "Manage your notification and account settings.")

    pref_l, pref_r = st.columns([3, 2], gap="large")

    with pref_l:
        with st.container(border=True):
            st.markdown(f"##### {_icon_chip('◉', 'orange')} Notification Settings", unsafe_allow_html=True)
            with st.form("prefs"):
                h, m = map(int, user.get("notify_time", "07:00").split(":"))
                default_notify_email = (user.get("notify_email") or user.get("email") or "").strip()
                default_query_value = (user.get("gmail_query") or cfg.get("gmail_query") or "").strip()
                notify_time  = st.time_input("Daily notification time", value=datetime.time(h, m))
                tz           = st.selectbox(
                    "Timezone", options=TIMEZONES,
                    index=TIMEZONES.index(user.get("timezone", "UTC"))
                    if user.get("timezone") in TIMEZONES else 0,
                )
                notify_email = st.text_input(
                    "Notification email",
                    value=default_notify_email,
                    placeholder="you@example.com",
                )
                gmail_query_val = st.text_input(
                    "Gmail search query",
                    value=default_query_value,
                    placeholder="scheduled",
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
                    notify_email_to_save = (notify_email or user.get("email") or "").strip()
                    gmail_query_to_save = (gmail_query_val or "").strip()
                    try:
                        r = requests.post(
                            f"{API}/preferences",
                            params={
                                "user_id": uid, "notify_time": nt_str,
                                "timezone": tz, "notify_email": notify_email_to_save,
                                "gmail_query": gmail_query_to_save,
                                "email_sync_hours": int(email_sync_hours_val),
                            },
                            timeout=10,
                        )
                        r.raise_for_status()
                        st.session_state["user"].update({
                            "notify_time": nt_str, "timezone": tz,
                            "notify_email": notify_email_to_save,
                            "gmail_query": gmail_query_to_save,
                            "email_sync_hours": int(email_sync_hours_val),
                        })
                        st.toast("Settings saved.", icon="✅")
                    except Exception:
                        st.toast("Could not save settings. Please try again.", icon="❌")

    with pref_r:
        with st.container(border=True):
            st.markdown(f"##### {_icon_chip('≡', 'blue')} Current Settings", unsafe_allow_html=True)
            st.markdown(f"**Notify Time:** &nbsp;`{user.get('notify_time', '—')}`", unsafe_allow_html=True)
            st.markdown(f"**Timezone:** &nbsp;`{user.get('timezone', '—')}`", unsafe_allow_html=True)
            notify_val = (user.get("notify_email") or user.get("email") or "_not set_")
            st.markdown(f"**Notify Email:** &nbsp;{notify_val}", unsafe_allow_html=True)
            query_val = (user.get("gmail_query") or cfg.get("gmail_query") or "").strip() or "all emails (default)"
            st.markdown(f"**Gmail Query:** &nbsp;`{query_val}`", unsafe_allow_html=True)
            st.markdown(f"**Sync Interval:** &nbsp;`Every {user.get('email_sync_hours', 24)}h`", unsafe_allow_html=True)
            st.markdown(f"**Account:** &nbsp;{user.get('email', '—')}", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# SENDERS
# ══════════════════════════════════════════════════════════════════
elif page == "Senders":
    _ph(_icon_chip("◎", "green"), "Sender Priorities", "Mark important email senders so you can prioritize them.")

    if st.button("🔄 Refresh Senders", key="senders_refresh"):
        st.session_state.pop("senders_list", None)

    if "senders_list" not in st.session_state:
        _senders_data, _err = _get("/api/senders", user_id=uid)
        if _err:
            st.error(f"Could not fetch senders: {_err}")
            st.session_state["senders_list"] = []
        else:
            st.session_state["senders_list"] = (_senders_data or {}).get("senders", [])

    senders_list = st.session_state.get("senders_list", [])

    if not senders_list:
        st.info("No senders found yet. Run a sync to fetch emails and discover senders.")
    else:
        with st.container(border=True):
            st.markdown(f"##### {_icon_chip('≣', 'green')} Found {len(senders_list)} Unique Sender(s)", unsafe_allow_html=True)
            st.markdown(
                "<div class='pa-table-head'><span>Sender</span><span>Domain</span><span>Current</span><span>Excluded</span><span>Set Priority</span><span>Action</span></div>",
                unsafe_allow_html=True,
            )

            for i, sender_obj in enumerate(senders_list):
                sender_email = sender_obj.get("email", "")
                current_priority = sender_obj.get("priority", "medium")
                is_excluded = bool(sender_obj.get("excluded", False))
                sender_domain = sender_email.split("@")[-1] if "@" in sender_email else "-"
                current_label = current_priority.capitalize()
                current_badge = PRIORITY_COLOR.get(current_label, "b-gray")
                
                col1, col2, col3, col4, col5, col6 = st.columns([3, 1.35, 1.15, 1.1, 1.4, 1])
                
                with col1:
                    st.markdown(f"**{sender_email}**")
                    st.markdown("<div class='pa-cell-meta'>Sender profile</div>", unsafe_allow_html=True)
                with col2:
                    st.markdown(f"**{sender_domain}**")
                with col3:
                    st.markdown(f"<span class='badge {current_badge}'>{current_label}</span>", unsafe_allow_html=True)
                
                with col4:
                    excluded_selected = st.checkbox(
                        "Exclude",
                        value=is_excluded,
                        key=f"exclude_{i}_{sender_email}",
                        label_visibility="collapsed",
                    )

                with col5:
                    priority_options = ["High", "Medium", "Low"]
                    current_idx = {"high": 0, "medium": 1, "low": 2}.get(current_priority.lower(), 1)
                    selected = st.selectbox(
                        "Priority",
                        options=priority_options,
                        index=current_idx,
                        key=f"priority_{i}_{sender_email}",
                        label_visibility="collapsed",
                    )
                
                with col6:
                    if st.button("Save", key=f"save_{i}_{sender_email}", use_container_width=True):
                        _err = None
                        _update_res, _err = _post(
                            "/api/sender-priorities",
                            {
                                "user_id": uid,
                                "sender": sender_email,
                                "priority": selected.lower(),
                            }
                        )
                        if _err:
                            st.toast(f"Could not update {sender_email}: {_err}", icon="❌")
                        _filter_res, _filter_err = _post(
                            "/api/sender-filters",
                            {
                                "user_id": uid,
                                "sender": sender_email,
                                "excluded": bool(excluded_selected),
                            }
                        )
                        if _filter_err:
                            st.toast(f"Could not update exclusion for {sender_email}: {_filter_err}", icon="❌")

                        if not _err and not _filter_err:
                            st.toast(f"✓ {sender_email} updated", icon="✅")
                            st.session_state.pop("senders_list", None)
                            st.rerun()

                st.markdown("<div class='pa-row-sep'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# ACCOUNTS
# ══════════════════════════════════════════════════════════════════
elif page == "Accounts":
    _ph(_icon_chip("⛓", "blue"), "Connected Accounts", "Manage the Gmail accounts synced to your assistant.")

    if st.button("🔄 Refresh", key="accs_refresh"):
        st.session_state.pop("linked_accounts", None)

    if "linked_accounts" not in st.session_state:
        _la_data, _ = _get("/linked-accounts", user_id=uid)
        st.session_state["linked_accounts"] = _la_data or []

    linked_accounts = st.session_state["linked_accounts"]

    with st.container(border=True):
        st.markdown(f"##### {_icon_chip('◉', 'blue')} Primary Account", unsafe_allow_html=True)
        p1, p2, p3 = st.columns([4, 1.3, 1.3])
        with p1:
            st.markdown(f"**{user['email']}**")
            st.markdown("<div class='pa-cell-meta'>Owner profile</div>", unsafe_allow_html=True)
        with p2:
            st.markdown("<span class='badge b-blue'>Primary</span>", unsafe_allow_html=True)
        with p3:
            st.markdown("<span class='badge b-green'>Active</span>", unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown(f"##### {_icon_chip('≣', 'blue')} Linked Accounts", unsafe_allow_html=True)
        if not linked_accounts:
            st.info("No linked accounts yet. Add one below.")
        else:
            st.markdown(
                "<div class='pa-table-head'><span>Account</span><span>Domain</span><span>Role</span><span>Status</span><span>Action</span></div>",
                unsafe_allow_html=True,
            )
            for _la in linked_accounts:
                email = _la.get("email", "")
                domain = email.split("@")[-1] if "@" in email else "-"
                lc1, lc2, lc3, lc4, lc5 = st.columns([2.7, 1.3, 1.1, 1.4, 1])
                with lc1:
                    st.markdown(f"**{email}**")
                    st.markdown(f"<div class='pa-cell-meta'>Linked ID: {_la.get('id', '-')}</div>", unsafe_allow_html=True)
                with lc2:
                    st.markdown(f"**{domain}**")
                with lc3:
                    st.markdown("<span class='badge b-gray'>Linked</span>", unsafe_allow_html=True)
                with lc4:
                    st.markdown("<span class='badge b-green'>Active</span>", unsafe_allow_html=True)
                with lc5:
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
                st.markdown("<div class='pa-row-sep'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(f"##### {_icon_chip('+', 'green')} Add Account", unsafe_allow_html=True)
        st.caption("Connect another Gmail account to sync all your emails in one place.")
        st.markdown(
            f'<a href="{PUBLIC_API}/link-account?owner_id={uid}" target="_self" style="text-decoration:none;">'
            '<button class="pa-link-btn">'
            '➕ Connect Gmail Account</button></a>',
            unsafe_allow_html=True,
        )
