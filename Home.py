import streamlit as st
import os
import time
from hpc_client_ssh import HPCSSHClient
from utils.sidebar import render_project_selector, clear_project_state

st.set_page_config(
    page_title="Home",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🏠 Home")

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

    render_project_selector(st.session_state.client)

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
st.title("🧠 HPC Slurm Job Manager")
st.write("Welcome to the HPC Slurm Job Manager - manage your cluster jobs with ease.")

if st.session_state.connected:
    st.success(f"Connected to **{st.session_state.hostname}** as **{st.session_state.username}**")

    st.divider()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown("### 🔄 Workflows")
        st.write("Configure analysis pipelines, submit jobs to the HPC cluster, and monitor pipeline status.")
        if st.button("Go to Workflows", use_container_width=True):
            st.switch_page("pages/1_Workflows.py")

    with col2:
        st.markdown("### 📊 Visualize Data")
        st.write("Visualize and analyze your results with interactive plots and dashboards.")
        if st.button("Go to Visualize", use_container_width=True):
            st.switch_page("pages/2_Visualize_Data.py")

    with col3:
        st.markdown("### 📥 Download Data")
        st.write("Download results and outputs from your HPC jobs to your local machine.")
        if st.button("Go to Download", use_container_width=True):
            st.switch_page("pages/3_Download_Data.py")

    # with col4:
    #     st.markdown("### 📚 Data Explorer")
    #     st.write("Explore and visualize your data files interactively.")
    #     if st.button("Go to Data Explorer", use_container_width=True):
    #         st.switch_page("pages/4_Data_Explorer.py")

    with col4:
        st.markdown("### 📚 Data Explorer")
        st.write("Explore and visualize your data files interactively.")
        if st.button("Go to Data Explorer", use_container_width=True):
            st.switch_page("pages/4_Projects.py")


    st.divider()

    st.divider()
    st.markdown("""
    ## 🧠 NaN Slurm Job Manager

    A comprehensive interface for managing high-performance computing jobs on Slurm clusters.

    ### Features

    #### 🔄 Workflows
    - **Pipeline Configuration**: Define which modules to run and their resource allocations per project
    - **Manual Trigger**: Submit the configured pipeline immediately for selected subjects/sessions
    - **Slurm Chaining**: Modules with dependencies are automatically chained with `afterok`
    - **Pipeline Status**: Track job status per subject/session across all modules

    #### 📥 Download Data
    - **Smart File Browser**: Navigate remote directories with ease
    - **Batch Downloads**: Download multiple files at once
    - **Auto-detection**: Automatically find output files from your jobs
    - **Progress Tracking**: Monitor download progress for large files

    #### 📊 Visualize Data
    - **Interactive Plots**: Create dynamic visualizations of your results
    - **Data Exploration**: Browse and analyze datasets
    - **Export Options**: Save visualizations in multiple formats
    - **Custom Dashboards**: Build personalized analytics views

    ### Quick Start

    1. Connect to your HPC cluster using the sidebar
    2. Navigate to Job Manager to submit jobs
    3. Monitor job status in real-time
    4. Download results when complete
    5. Visualize and analyze your data

    ### Need Help?

    - Check the documentation for each page
    - View example workflows in the Workflow tab
    - Contact support if you encounter issues
    """)

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