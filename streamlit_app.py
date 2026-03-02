"""Streamlit UI - Personal Assistant (multi-user, backed by FastAPI)."""

import datetime
import requests
import streamlit as st

# --- Page config (must be first) ---
st.set_page_config(
    page_title="Personal Assistant",
    page_icon="PA",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Global styles ---
st.markdown("""
<style>
.block-container { padding-top: 1.4rem; padding-bottom: 1rem; }
.stMetric        { background:#f8f9fb; border-radius:8px; padding:8px; }
.badge { display:inline-block; padding:2px 9px; border-radius:12px;
         font-size:.75rem; font-weight:600; margin-left:4px; }
.b-blue   { background:#dbeafe; color:#1d4ed8; }
.b-green  { background:#dcfce7; color:#15803d; }
.b-yellow { background:#fef9c3; color:#a16207; }
.b-red    { background:#fee2e2; color:#b91c1c; }
.b-gray   { background:#f1f5f9; color:#475569; }
</style>
""", unsafe_allow_html=True)

# --- Constants ---
API = "http://localhost:8000"

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
        return None, "API server is offline. Run `python run.py` first."
    except Exception as e:
        return None, str(e)

def _post(path, payload):
    try:
        r = requests.post(f"{API}{path}", json=payload, timeout=60)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.ConnectionError:
        return None, "API server is offline. Run `python run.py` first."
    except Exception as e:
        return None, str(e)

"""Sidebar with sign-in and status."""
with st.sidebar:
    st.title("Personal Assistant")
    st.divider()

    # Server health check
    health, err = _get("/")
    if err:
        st.error("API offline. Run: python run.py")
        st.stop()
    st.success("API running")
    st.divider()

    # --- Sign-in section ---
    st.subheader("Sign In")
    st.markdown(
        f'<a href="{API}/signup" target="_blank">'
        '<button style="width:100%;background:#4285F4;color:white;border:none;'
        'padding:8px;border-radius:6px;cursor:pointer;font-size:14px;">'
        'Sign in with Google</button></a>',
        unsafe_allow_html=True,
    )
    st.caption("After sign-in, copy the **user_id** shown on the page and paste below.")

    user_id_input = st.text_input(
        "Your User ID",
        value=st.session_state.get("user_id", ""),
        placeholder="Paste user_id here...",
    )

    if user_id_input and user_id_input != st.session_state.get("user_id"):
        status, err = _get("/status", user_id=user_id_input)
        if err or not status:
            st.error("User not found. Please sign in first.")
        else:
            st.session_state["user_id"] = user_id_input
            st.session_state["user"]    = status
            st.rerun()

    if st.session_state.get("user"):
        u = st.session_state["user"]
        st.success(u["email"])
        st.caption(f"Notify: **{u['notify_time']}** ({u['timezone']})")
        st.caption(u.get("notify_email") or "No notification email set")
        if st.button("Sign out", use_container_width=True):
            st.session_state.clear()
            st.rerun()


# --- Require login ---
if not st.session_state.get("user_id"):
    st.info("Sign in with Google using the sidebar to get started.")
    st.stop()

uid  = st.session_state["user_id"]
user = st.session_state["user"]

# Fetch config once
if "cfg" not in st.session_state:
    cfg, _ = _get("/api/config")
    st.session_state["cfg"] = cfg or {}
cfg = st.session_state["cfg"]

# --- Tabs ---
t_dash, t_email, t_cal, t_prefs = st.tabs(
    ["Dashboard", "Emails", "Calendar", "Preferences"]
)

# --- DASHBOARD ---
with t_dash:

    # Stats row
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Notify Time",   user["notify_time"])
    c2.metric("Timezone",      user["timezone"])
    c3.metric("Max Emails",    cfg.get("gmail_max_results", "-"))
    c4.metric("Event Duration", f"{cfg.get('default_event_duration','-')} min")

    st.divider()

    # Run assistant
    col_a, col_b = st.columns([2, 1])
    with col_a:
        send_email_opt = st.checkbox(
            "Send me today's schedule by email after running",
            value=False,
        )
    with col_b:
        run_btn = st.button("Run Assistant Now", use_container_width=True, type="primary")

    if run_btn:
        with st.spinner("Fetching emails, analysing with Gemini, creating events..."):
            res, err = _post("/api/run-assistant", {
                "user_id":    uid,
                "send_email": send_email_opt,
            })
        if err:
            st.error(err)
        else:
            st.success(
                f"Done - **{res['emails_processed']}** emails processed, "
                f"**{res['events_created']}** events added to calendar."
            )
            if res.get("details"):
                with st.expander("See email details"):
                    for item in res["details"]:
                        icon  = "[CAL]" if item["event_created"] else "[MAIL]"
                        color = INTENT_COLOR.get(item["intent"], "b-gray")
                        st.markdown(
                            f"{icon} **{item['subject'] or '(no subject)'}** "
                            f'<span class="badge {color}">{item["intent"] or "?"}</span><br>'
                            f'<small>{item["summary"] or ""}</small>',
                            unsafe_allow_html=True,
                        )

    st.divider()

    # Today's schedule
    st.subheader("Today's Schedule")
    if st.button("Load / Refresh Schedule"):
        data, err = _get("/api/schedule", user_id=uid)
        if err:
            st.error(err)
        else:
            st.session_state["schedule"] = data.get("schedule", "")

    # Auto-load on first visit
    if "schedule" not in st.session_state:
        data, err = _get("/api/schedule", user_id=uid)
        if not err:
            st.session_state["schedule"] = data.get("schedule", "")

    sched = st.session_state.get("schedule", "")
    if sched:
        for line in sched.strip().split("\n"):
            if line.strip():
                st.markdown(line)
    else:
        st.info("No events scheduled for today.")

# --- EMAILS ---
with t_email:
    st.header("Emails")
    st.caption("Fetches your Gmail messages and runs Gemini analysis on each one.")

    qcol, ncol = st.columns([3, 1])
    with qcol:
        query = st.text_input(
            "Gmail search query",
            value=cfg.get("gmail_query",
                          "subject:meeting OR subject:appointment OR subject:scheduled"),
        )
    with ncol:
        max_r = st.number_input(
            "Max results", min_value=1, max_value=100,
            value=int(cfg.get("gmail_max_results", 20)),
        )

    if st.button("Fetch & Analyse", use_container_width=True, type="primary"):
        with st.spinner("Fetching and analysing emails with Gemini..."):
            data, err = _post("/api/fetch-emails", {
                "user_id": uid, "query": query, "max_results": int(max_r),
            })
        if err:
            st.error(err)
        else:
            st.session_state["emails"] = data

    st.divider()

    emails_data = st.session_state.get("emails")
    if emails_data:
        st.success(f"**{emails_data['count']}** email(s) found")
        for i, em in enumerate(emails_data["emails"]):
            intent  = em.get("intent", "")
            color   = INTENT_COLOR.get(intent, "b-gray")
            with st.container(border=True):
                hdr, btn_col = st.columns([5, 1])
                with hdr:
                    st.markdown(
                        f"**{em['subject'] or '(no subject)'}** "
                        f'<span class="badge {color}">{intent or "Unknown"}</span>',
                        unsafe_allow_html=True,
                    )
                    st.caption(
                        f"From: {em.get('from_') or '-'} &nbsp;|&nbsp; "
                        f"Date: {em.get('date') or '-'} &nbsp;|&nbsp; "
                        f"Attachments: {em.get('attachments', 0)}"
                    )
                with btn_col:
                    if intent == "Event Scheduling":
                        if st.button("Add", key=f"add_{i}", help="Add to calendar"):
                            res, err = _post("/api/create-event", {
                                "user_id":     uid,
                                "subject":     em["subject"],
                                "description": em.get("body_preview", ""),
                            })
                            st.success("Added!") if not err else st.error(err)

                if em.get("summary"):
                    st.markdown(f"Note: {em['summary']}")
                if em.get("suggested_action"):
                    st.markdown(f"Action: {em['suggested_action']}")
                with st.expander("Preview"):
                    st.text(em.get("body_preview") or "-")
    else:
        st.info("Click **Fetch & Analyse** to load your emails.")



# --- CALENDAR ---
with t_cal:
    st.header("Calendar")
    view_col, create_col = st.columns(2)

    with view_col:
        st.subheader("Today's Events")
        if st.button("Refresh", key="cal_refresh"):
            data, err = _get("/api/schedule", user_id=uid)
            if err:
                st.error(err)
            else:
                st.session_state["schedule"] = data.get("schedule", "")

        sched = st.session_state.get("schedule", "")
        if sched:
            for line in sched.strip().split("\n"):
                if line.strip():
                    st.markdown(line)
        else:
            st.info("No events today. Click Refresh.")

    with create_col:
        st.subheader("Add New Event")
        with st.form("new_event"):
            evt_title = st.text_input(
                "Title", placeholder="e.g., Team Standup"
            )
            evt_desc = st.text_area(
                "Description / when is it?",
                placeholder="e.g., Daily standup tomorrow at 10 AM",
                height=100,
                help="Include a date/time - it will be parsed automatically.",
            )
            if st.form_submit_button("Create Event", use_container_width=True, type="primary"):
                if not evt_title:
                    st.error("Please enter a title.")
                else:
                    res, err = _post("/api/create-event", {
                        "user_id":     uid,
                        "subject":     evt_title,
                        "description": evt_desc,
                    })
                    if err:
                        st.error(err)
                    else:
                        st.success(res["message"])
                        # Refresh schedule
                        data, _ = _get("/api/schedule", user_id=uid)
                        if data:
                            st.session_state["schedule"] = data.get("schedule", "")
                        st.rerun()


# --- PREFERENCES ---
with t_prefs:
    st.header("Preferences")
    st.markdown("Change when and where you receive your daily schedule.")

    current_time = user.get("notify_time", "07:00")
    h, m = map(int, current_time.split(":"))

    with st.form("prefs"):
        notify_time = st.time_input(
            "Daily notification time",
            value=datetime.time(h, m),
            help="You will receive an email with today's schedule at this time every day.",
        )
        tz = st.selectbox(
            "Timezone",
            options=TIMEZONES,
            index=TIMEZONES.index(user.get("timezone", "UTC"))
                  if user.get("timezone") in TIMEZONES else 0,
        )
        notify_email = st.text_input(
            "Notification email address",
            value=user.get("notify_email") or "",
            placeholder="you@gmail.com",
        )
        saved = st.form_submit_button("Save", use_container_width=True, type="primary")

    if saved:
        nt_str = notify_time.strftime("%H:%M")
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
        if r.ok:
            st.success("Preferences saved!")
            st.session_state["user"]["notify_time"]  = nt_str
            st.session_state["user"]["timezone"]     = tz
            st.session_state["user"]["notify_email"] = notify_email
            st.rerun()
        else:
            st.error(f"Failed: {r.text}")

