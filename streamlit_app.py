"""Streamlit frontend for Personal Assistant."""
import streamlit as st
import requests
import json
from datetime import datetime

# Page config
st.set_page_config(
    page_title="Personal Assistant",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Styling
st.markdown("""
    <style>
    .main {
        padding: 0rem 1rem;
    }
    .stButton > button {
        width: 100%;
        border-radius: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

# API base URL
API_BASE_URL = "http://localhost:8000"

# Session state
if "api_status" not in st.session_state:
    st.session_state.api_status = None


def check_api_health():
    """Check if API is running."""
    try:
        response = requests.get(f"{API_BASE_URL}/", timeout=5)
        return response.status_code == 200
    except:
        return False


def fetch_config():
    """Fetch current configuration from API."""
    try:
        response = requests.get(f"{API_BASE_URL}/api/config", timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Failed to fetch config: {str(e)}")
        return None


def run_full_assistant(gmail_query, max_results, send_whatsapp):
    """Run the full assistant workflow."""
    try:
        with st.spinner("Running assistant workflow..."):
            response = requests.post(
                f"{API_BASE_URL}/api/run-assistant",
                json={
                    "gmail_query": gmail_query,
                    "max_results": max_results,
                    "send_whatsapp": send_whatsapp,
                },
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        st.error(f"Error running assistant: {str(e)}")
        return None


def fetch_emails(query, max_results):
    """Fetch emails from Gmail."""
    try:
        with st.spinner("Fetching emails..."):
            response = requests.post(
                f"{API_BASE_URL}/api/fetch-emails",
                json={"query": query, "max_results": max_results},
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        st.error(f"Error fetching emails: {str(e)}")
        return None


def get_schedule():
    """Get today's schedule."""
    try:
        with st.spinner("Fetching schedule..."):
            response = requests.get(
                f"{API_BASE_URL}/api/schedule",
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        st.error(f"Error fetching schedule: {str(e)}")
        return None


def create_event(subject, description):
    """Create a calendar event."""
    try:
        with st.spinner("Creating event..."):
            response = requests.post(
                f"{API_BASE_URL}/api/create-event",
                json={"subject": subject, "description": description},
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        st.error(f"Error creating event: {str(e)}")
        return None


# Header
st.title("📋 Personal Assistant Dashboard")
st.markdown("Manage your emails, calendar events, and daily schedule")

# Check API status
if not check_api_health():
    st.error(
        "❌ **API is not running!**\n\n"
        "Please start the FastAPI backend:\n"
        "```bash\npython app.py\n```\n"
        "or\n"
        "```bash\nuvicorn app:app --reload\n```"
    )
    st.stop()

st.success("✅ API is running")

# Fetch config once and store in session state
if "config" not in st.session_state:
    st.session_state.config = fetch_config()

config = st.session_state.config

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuration")

    if config:
        st.subheader("Current Settings")
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Timezone", config.get("timezone", "N/A"))
            st.metric("Event Duration (min)", config.get("default_event_duration", "N/A"))
        
        with col2:
            st.metric("Calendar ID", config.get("calendar_id", "N/A")[:20] + "...")
            st.metric("Max Emails", config.get("gmail_max_results", "N/A"))

# Main content
tab1, tab2, tab3, tab4 = st.tabs(
    ["🏠 Dashboard", "📧 Emails", "📅 Create Event", "⚙️ Advanced"]
)

# Tab 1: Dashboard
with tab1:
    st.header("Dashboard")
    
    if not config:
        st.error("⚠️ Failed to load configuration. Please check if the API is running.")
        st.stop()
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("▶️ Run Full Assistant", use_container_width=True, key="run_full"):
            result = run_full_assistant(config["gmail_query"], config["gmail_max_results"], True)
            if result:
                st.success(f"✅ {result.get('message', 'Success')}")
                st.write(f"📧 Emails processed: {result.get('emails_processed', 0)}")
                st.write(f"📅 Events created: {result.get('events_created', 0)}")
    
    with col2:
        if st.button("📅 Get Today's Schedule", use_container_width=True, key="get_schedule"):
            result = get_schedule()
            if result:
                st.session_state.schedule_result = result
    
    with col3:
        if st.button("🔄 Refresh", use_container_width=True, key="refresh"):
            st.rerun()
    
    st.divider()
    
    st.subheader("Today's Schedule")
    if "schedule_result" in st.session_state and st.session_state.schedule_result:
        result = st.session_state.schedule_result
        if result.get("schedule"):
            for event in result["schedule"]:
                # Handle both dict and string event formats
                if isinstance(event, dict):
                    with st.container(border=True):
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.write(f"**{event.get('summary', 'Untitled')}**")
                            st.caption(f"📍 {event.get('start', 'TBD')} - {event.get('end', 'TBD')}")
                        with col2:
                            st.write(event.get('description', 'No description'))
                elif isinstance(event, str):
                    # If event is a string, display it directly
                    with st.container(border=True):
                        st.write(event)
        else:
            st.info("No events scheduled for today")
    else:
        st.info("Click 'Get Today's Schedule' to load events")

# Tab 2: Emails
with tab2:
    st.header("Email Management")
    
    if not config:
        st.error("⚠️ Failed to load configuration. Please check if the API is running.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            gmail_query = st.text_input(
                "Gmail Search Query",
                value=config.get("gmail_query", "subject:meeting OR subject:appointment"),
                help="Use Gmail search syntax",
            )
        with col2:
            max_results = st.number_input(
                "Max Results",
                min_value=1,
                max_value=100,
                value=config.get("gmail_max_results", 20),
            )
        
        if st.button("🔍 Fetch Emails", use_container_width=True, key="fetch_emails"):
            result = fetch_emails(gmail_query, int(max_results))
            if result:
                st.session_state.emails_result = result
        
        st.divider()
        
        if "emails_result" in st.session_state and st.session_state.emails_result:
            result = st.session_state.emails_result
            st.success(f"Found {result.get('count', 0)} emails")
            
            for email in result.get("emails", []):
                with st.container(border=True):
                    st.write(f"**{email.get('subject', 'No Subject')}**")
                    st.caption(f"From: {email.get('sender', 'Unknown')}")
                    with st.expander("View Body"):
                        st.write(email.get("body", "No content"))
        else:
            st.info("Click 'Fetch Emails' to load messages")

# Tab 3: Create Event
with tab3:
    st.header("Create Calendar Event")
    
    subject = st.text_input(
        "Event Subject",
        placeholder="e.g., Team Meeting, Client Call",
    )
    
    description = st.text_area(
        "Event Description",
        placeholder="Event details and notes...",
        height=120,
    )
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Create Event", use_container_width=True, key="create_event"):
            if subject:
                result = create_event(subject, description)
                if result:
                    st.success("Event created successfully!")
                    st.json(result)
            else:
                st.error("Please enter an event subject")
    
    with col2:
        if st.button("🔄 Clear", use_container_width=True, key="clear_form"):
            st.rerun()

# Tab 4: Advanced
with tab4:
    st.header("Advanced Settings")
    
    if not config:
        st.error("⚠️ Failed to load configuration. Please check if the API is running.")
    else:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Custom Assistant Run")
            custom_query = st.text_area(
                "Custom Gmail Query",
                value=config.get("gmail_query", ""),
                height=100,
            )
            custom_max = st.slider("Custom Max Results", 1, 100, config.get("gmail_max_results", 20))
            send_whatsapp = st.checkbox("Send WhatsApp Notification", value=True)
            
            if st.button("▶️ Run Custom", use_container_width=True):
                result = run_full_assistant(custom_query, custom_max, send_whatsapp)
                if result:
                    st.success("✅ Workflow completed")
                    st.json(result)
        
        with col2:
            st.subheader("API Information")
            st.write(f"**API Base URL:** `{API_BASE_URL}`")
            st.write(f"**Status:** ✅ Running")
            
            if st.button("📊 View API Docs", use_container_width=True):
                st.write(f"Visit [Swagger UI]({API_BASE_URL}/docs)")
            
            st.divider()
            st.subheader("Current Configuration")
            st.json(config)
