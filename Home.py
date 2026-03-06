import streamlit as st
import os
import time
from hpc_client_ssh import HPCSSHClient
from utils.sidebar import clear_project_state, get_project_list
from utils.bids import count_subjects_and_sessions
from utils.hpc_io import read_json_from_hpc

st.set_page_config(
    page_title="Home",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

def inject_dashboard_styles() -> None:
    st.markdown(
        """
        <style>
        .cortex-topbar {
            background: #161b22;
            border: 1px solid #2a3444;
            border-radius: 8px;
            padding: 10px 14px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }
        .cortex-logo {
            font-size: 11px;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: #4fc3f7;
            font-weight: 600;
        }
        .cortex-badge {
            border: 1px solid #2a3444;
            border-radius: 4px;
            padding: 3px 8px;
            font-size: 11px;
            color: #cdd9e5;
            background: #1c2230;
        }
        .cortex-panel {
            background: #161b22;
            border: 1px solid #2a3444;
            border-radius: 8px;
            overflow: hidden;
            margin-bottom: 12px;
        }
        .cortex-panel-header {
            padding: 9px 12px;
            border-bottom: 1px solid #2a3444;
            background: #1c2230;
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: #768a9e;
            font-weight: 600;
        }
        .cortex-panel-body {
            padding: 12px;
        }
        .cortex-stat {
            background: #1c2230;
            border: 1px solid #2a3444;
            border-radius: 6px;
            padding: 10px;
        }
        .cortex-stat-label {
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #768a9e;
            margin-bottom: 6px;
        }
        .cortex-stat-value {
            font-size: 24px;
            font-weight: 600;
            color: #cdd9e5;
            line-height: 1;
        }
        .cortex-good { color: #81c784; }
        .cortex-warn { color: #ffb74d; }
        .cortex-bad { color: #f06292; }
        .cortex-linkcard-title {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 4px;
        }
        .cortex-linkcard-text {
            color: #768a9e;
            font-size: 13px;
            margin-bottom: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_dashboard_styles()

# Security configuration
SESSION_TIMEOUT_SECONDS = 1800  # 30 minutes
MAX_LOGIN_ATTEMPTS = 3
LOCKOUT_DURATION_SECONDS = 300  # 5 minutes
ALLOWED_HOSTS = ["login1.nan.kcl.ac.uk", "login2.nan.kcl.ac.uk"]  # Whitelist

# Initialize session state
if "client" not in st.session_state:
    st.session_state.client = None
if "connected" not in st.session_state:
    st.session_state.connected = False
if "login_attempts" not in st.session_state:
    st.session_state.login_attempts = 0
if "lockout_until" not in st.session_state:
    st.session_state.lockout_until = 0
if "last_activity" not in st.session_state:
    st.session_state.last_activity = time.time()
if "selected_project" not in st.session_state:
    st.session_state.selected_project = None

# Check session timeout
if st.session_state.connected:
    time_inactive = time.time() - st.session_state.last_activity
    if time_inactive > SESSION_TIMEOUT_SECONDS:
        if st.session_state.client:
            st.session_state.client.close()
        st.session_state.client = None
        st.session_state.connected = False
        st.warning("⏱️ Session expired due to inactivity")
        st.rerun()
    else:
        # Update last activity time
        st.session_state.last_activity = time.time()

# Sidebar connection settings
st.sidebar.title("🧠 HPC Manager")
st.sidebar.divider()

st.sidebar.header("🔑 Connection")

# Connection status indicator
if st.session_state.connected and st.session_state.client:
    st.sidebar.success("✅ Connected")
    inactive_time = int(time.time() - st.session_state.last_activity)
    timeout_remaining = SESSION_TIMEOUT_SECONDS - inactive_time
    st.sidebar.caption(f"Session timeout: {timeout_remaining // 60}m {timeout_remaining % 60}s")
    
    if st.sidebar.button("Disconnect", use_container_width=True):
        if st.session_state.client:
            st.session_state.client.close()
        st.session_state.client = None
        st.session_state.connected = False
        st.session_state.login_attempts = 0  # Reset on manual disconnect
        clear_project_state()
        st.rerun()

else:
    st.sidebar.info("Not connected")
    
    # Check if locked out
    if time.time() < st.session_state.lockout_until:
        wait_time = int(st.session_state.lockout_until - time.time())
        st.sidebar.error(f"🔒 Too many failed attempts\nWait {wait_time // 60}m {wait_time % 60}s")
        st.stop()
    
    # Connection form
    hostname = st.sidebar.selectbox(
        "Hostname",
        ALLOWED_HOSTS,
        help="Select your HPC cluster"    
    )
    username = st.sidebar.text_input(
        "Username",
        value=os.getenv("USER", ""),
        help="Your HPC username"
    )
    
    # Authentication method selection
    auth_method = st.sidebar.radio(
        "Authentication Method",
        ["Password", "SSH Key"],
        help="Choose how to authenticate"
    )
    
    if auth_method == "Password":
        st.sidebar.info("🔐 Password authentication")
        password = st.sidebar.text_input(
            "Password",
            type="password",
            help="Your HPC password (not stored)"
        )
        
        if st.sidebar.button("Connect", use_container_width=True):
            if not username or not password:
                st.sidebar.error("❌ Enter username and password")
            else:
                try:
                    with st.spinner("Connecting..."):
                        # Password is used here and immediately cleared by client
                        client = HPCSSHClient(hostname, username, password=password)
                        st.session_state.client = client
                        st.session_state.connected = True
                        st.session_state.hostname = hostname
                        st.session_state.username = username
                        st.session_state.login_attempts = 0
                        st.session_state.last_activity = time.time()
                    st.success(f"✅ Connected to {hostname}")
                    st.rerun()
                except Exception as e:
                    st.session_state.login_attempts += 1
                    remaining = MAX_LOGIN_ATTEMPTS - st.session_state.login_attempts
                    
                    if st.session_state.login_attempts >= MAX_LOGIN_ATTEMPTS:
                        st.session_state.lockout_until = time.time() + LOCKOUT_DURATION_SECONDS
                        st.error(f"🔒 Too many failed attempts. Locked for {LOCKOUT_DURATION_SECONDS // 60} minutes.")
                    else:
                        st.error(f"❌ Connection failed: {e}\n{remaining} attempts remaining")
    
    else:  # SSH Key
        st.sidebar.info("🔑 SSH key authentication")
        key_path = st.sidebar.text_input(
            "SSH Key Path",
            value="~/.ssh/id_rsa",
            help="Path to your private SSH key"
        )
        
        if st.sidebar.button("Connect", use_container_width=True):
            if not username:
                st.sidebar.error("❌ Enter username")
            else:
                try:
                    with st.spinner("Connecting..."):
                        client = HPCSSHClient(hostname, username, key_path=key_path)
                        st.session_state.client = client
                        st.session_state.connected = True
                        st.session_state.hostname = hostname
                        st.session_state.username = username
                        st.session_state.login_attempts = 0
                        st.session_state.last_activity = time.time()
                    st.success(f"✅ Connected to {hostname}")
                    st.rerun()
                except Exception as e:
                    st.session_state.login_attempts += 1
                    remaining = MAX_LOGIN_ATTEMPTS - st.session_state.login_attempts
                    
                    if st.session_state.login_attempts >= MAX_LOGIN_ATTEMPTS:
                        st.session_state.lockout_until = time.time() + LOCKOUT_DURATION_SECONDS
                        st.error(f"🔒 Too many failed attempts. Locked for {LOCKOUT_DURATION_SECONDS // 60} minutes.")
                    else:
                        st.error(f"❌ Connection failed: {e}\n{remaining} attempts remaining")

# Main page content
st.markdown(
    """
    <div class="cortex-topbar">
      <div class="cortex-logo">Cortex <span style="color:#768a9e;">Neuro Pipeline Dashboard</span></div>
      <div class="cortex-badge">NaN Cluster</div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown("## Project Landing")
st.caption("Select one active project and use it across Workflows, Visualize, and Download.")

if st.session_state.connected:
    st.markdown(
        f"<div class='cortex-badge'>● Connected as {st.session_state.username}@{st.session_state.hostname}</div>",
        unsafe_allow_html=True,
    )

    client = st.session_state.client
    projects = get_project_list(client)

    st.markdown("<div class='cortex-panel'><div class='cortex-panel-header'>Active Project</div><div class='cortex-panel-body'>", unsafe_allow_html=True)
    c_proj, c_refresh = st.columns([5, 1])
    with c_proj:
        if projects:
            current = st.session_state.get("selected_project")
            default_idx = projects.index(current) if current in projects else 0
            home_widget_key = "_home_selected_project"
            desired_project = projects[default_idx]
            if st.session_state.get(home_widget_key) != desired_project:
                st.session_state[home_widget_key] = desired_project

            selected_project = st.selectbox(
                "Active Project",
                options=projects,
                key=home_widget_key,
                help="This selection is shared across all pages.",
            )
            st.session_state["selected_project"] = selected_project
        else:
            selected_project = None
            st.warning("No projects found in `~/projects/`.")

    with c_refresh:
        st.write("")
        if st.button("Refresh", use_container_width=True):
            get_project_list(client, refresh=True)
            st.rerun()
    st.markdown("</div></div>", unsafe_allow_html=True)

    if selected_project:
        if "_home_dir" not in st.session_state:
            st.session_state["_home_dir"] = client._run("echo $HOME").strip()
        home_dir = st.session_state["_home_dir"]
        project_path = f"{home_dir}/projects/{selected_project}"
        config_path = f"{project_path}/.cortex/pipeline_config.json"

        with st.spinner("Loading project summary..."):
            num_subjects, num_sessions = count_subjects_and_sessions(client, project_path)
            pipeline_config = read_json_from_hpc(client, config_path)
            configured_modules = pipeline_config.get("modules", [])
            manifest = client.read_pipeline_manifest(project_path)

        status_counts = {"queued": 0, "running": 0, "complete": 0, "failed": 0}
        for modules in manifest.values():
            for info in modules.values():
                status = info.get("status")
                if status in status_counts:
                    status_counts[status] += 1

        st.markdown("<div class='cortex-panel'><div class='cortex-panel-header'>Project Summary</div><div class='cortex-panel-body'>", unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown(
                f"<div class='cortex-stat'><div class='cortex-stat-label'>Project</div><div class='cortex-stat-value' style='font-size:18px'>{selected_project}</div></div>",
                unsafe_allow_html=True,
            )
        with m2:
            st.markdown(
                f"<div class='cortex-stat'><div class='cortex-stat-label'>Subjects</div><div class='cortex-stat-value'>{num_subjects}</div></div>",
                unsafe_allow_html=True,
            )
        with m3:
            st.markdown(
                f"<div class='cortex-stat'><div class='cortex-stat-label'>Sessions</div><div class='cortex-stat-value'>{num_sessions}</div></div>",
                unsafe_allow_html=True,
            )
        with m4:
            st.markdown(
                f"<div class='cortex-stat'><div class='cortex-stat-label'>Configured Modules</div><div class='cortex-stat-value'>{len(configured_modules)}</div></div>",
                unsafe_allow_html=True,
            )

        s1, s2, s3, s4 = st.columns(4)
        with s1:
            st.markdown(
                f"<div class='cortex-stat'><div class='cortex-stat-label'>Queued</div><div class='cortex-stat-value cortex-warn'>{status_counts['queued']}</div></div>",
                unsafe_allow_html=True,
            )
        with s2:
            st.markdown(
                f"<div class='cortex-stat'><div class='cortex-stat-label'>Running</div><div class='cortex-stat-value'>{status_counts['running']}</div></div>",
                unsafe_allow_html=True,
            )
        with s3:
            st.markdown(
                f"<div class='cortex-stat'><div class='cortex-stat-label'>Complete</div><div class='cortex-stat-value cortex-good'>{status_counts['complete']}</div></div>",
                unsafe_allow_html=True,
            )
        with s4:
            st.markdown(
                f"<div class='cortex-stat'><div class='cortex-stat-label'>Failed</div><div class='cortex-stat-value cortex-bad'>{status_counts['failed']}</div></div>",
                unsafe_allow_html=True,
            )
        st.markdown("</div></div>", unsafe_allow_html=True)

        if configured_modules:
            st.caption(f"Pipeline configuration: {' → '.join(configured_modules)}")
        else:
            st.caption("No pipeline modules configured yet.")

    st.markdown("<div class='cortex-panel'><div class='cortex-panel-header'>Navigation</div><div class='cortex-panel-body'>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("<div class='cortex-linkcard-title'>🔄 Workflows</div>", unsafe_allow_html=True)
        st.markdown("<div class='cortex-linkcard-text'>Configure module pipelines and review pipeline status.</div>", unsafe_allow_html=True)
        if st.button("Open Workflows", use_container_width=True):
            st.switch_page("pages/1_Workflows.py")

    with col2:
        st.markdown("<div class='cortex-linkcard-title'>📊 Visualize Data</div>", unsafe_allow_html=True)
        st.markdown("<div class='cortex-linkcard-text'>Explore data structure and quick visual summaries.</div>", unsafe_allow_html=True)
        if st.button("Open Visualize", use_container_width=True):
            st.switch_page("pages/2_Visualize_Data.py")

    with col3:
        st.markdown("<div class='cortex-linkcard-title'>📥 Download Data</div>", unsafe_allow_html=True)
        st.markdown("<div class='cortex-linkcard-text'>Browse remote output folders and download files locally.</div>", unsafe_allow_html=True)
        if st.button("Open Download", use_container_width=True):
            st.switch_page("pages/3_Download_Data.py")
    st.markdown("</div></div>", unsafe_allow_html=True)

else:
    st.info("👈 Please connect to your HPC cluster using the sidebar to get started.")
    
    st.markdown("""
    ### Getting Started
    
    1. **Connect to HPC**
       - Enter your hostname (e.g., `login1.nan.kcl.ac.uk`)
       - Enter your username
       - Provide your SSH key path
       - Click Connect
    
    2. **Manage Jobs**
       - Submit Apptainer containers
       - Run pre-configured nodes
       - Create multi-step workflows
       - Monitor job status
    
    3. **Download Results**
       - Browse output directories
       - Download files to local machine
       - Batch download multiple files
    
    4. **Visualize Data**
       - Create plots and charts
       - Interactive data exploration
       - Export visualizations
    """)