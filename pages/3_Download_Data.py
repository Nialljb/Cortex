import streamlit as st
import os
from utils.sidebar import render_project_selector

st.set_page_config(page_title="Download Data", page_icon="📥", layout="wide")

st.title("📥 Download Data")

# Check connection
if not st.session_state.get("connected", False) or not st.session_state.get("client"):
    st.error("❌ Not connected to HPC cluster. Please connect using the sidebar.")
    st.stop()

client = st.session_state.client

render_project_selector(client)

if "_home_dir" not in st.session_state:
    st.session_state["_home_dir"] = client._run("echo $HOME").strip()
home_dir = st.session_state["_home_dir"]

st.write("Download files and results from your HPC jobs.")

# ============================================================================
# OUTPUT DIRECTORY BROWSER
# ============================================================================
st.header("📂 Browse Output Directory")

# Get project and node from job history if available
recent_job = st.session_state.get("job_history", [])[-1] if st.session_state.get("job_history") else None

if recent_job and "project" in recent_job:
    default_project = recent_job["project"]
    default_node = recent_job["name"].lower().replace(" ", "_")
else:
    default_project = None
    default_node = None

col1, col2 = st.columns([1, 1])

with col1:
    selected_project = st.session_state.get("selected_project")
    if not selected_project and default_project:
        st.session_state["selected_project"] = default_project
        selected_project = default_project

    if selected_project:
        st.info(f"Active project: `{selected_project}`")
    else:
        st.warning("Select a project from the sidebar to continue.")

with col2:
    # Node/directory selection
    if selected_project:
        try:
            # List subdirectories in the project
            project_path = f"{home_dir}/projects/{selected_project}"
            subdirs_result = client._run(f"ls -d {project_path}/*/ 2>/dev/null | xargs -n 1 basename")
            subdirs = [d.strip() for d in subdirs_result.splitlines() if d.strip()]
            
            if subdirs:
                default_subdir_idx = subdirs.index(default_node) if default_node in subdirs else 0
                selected_subdir = st.selectbox(
                    "Select Directory",
                    options=subdirs,
                    index=default_subdir_idx,
                    help="Subdirectories in the project"
                )
            else:
                selected_subdir = st.text_input("Directory Name", default_node or "output")
        except Exception as e:
            st.warning(f"Could not load directories: {e}")
            selected_subdir = st.text_input("Directory Name", default_node or "output")
    else:
        selected_subdir = ""

# ============================================================================
# FILE BROWSER
# ============================================================================
if selected_project and selected_subdir:
    remote_output_dir = f"{home_dir}/projects/{selected_project}/{selected_subdir}/output"
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.info(f"📂 Output directory: `{remote_output_dir}`")
    with col2:
        if st.button("🔄 Refresh Files", use_container_width=True):
            st.rerun()
    
    try:
        # List files in the output directory
        files_result = client._run(f"ls -lh {remote_output_dir} 2>/dev/null || echo ''")
        
        if files_result and not files_result.startswith("ls:"):
            lines = files_result.splitlines()[1:]  # Skip 'total' line
            files_data = []
            
            for line in lines:
                parts = line.split()
                if len(parts) >= 9:
                    files_data.append({
                        "permissions": parts[0],
                        "size": parts[4],
                        "date": f"{parts[5]} {parts[6]} {parts[7]}",
                        "name": " ".join(parts[8:])
                    })
            
            if files_data:
                st.subheader("Available Files")
                
                # Display files as selectable options
                for idx, file in enumerate(files_data):
                    col1, col2, col3, col4 = st.columns([3, 1, 2, 1])
                    
                    with col1:
                        st.text(f"📄 {file['name']}")
                    with col2:
                        st.text(file['size'])
                    with col3:
                        st.text(file['date'])
                    with col4:
                        if st.button("⬇️", key=f"download_{idx}"):
                            st.session_state.selected_file = file['name']
                            st.session_state.remote_path = f"{remote_output_dir}/{file['name']}"
                            st.rerun()
            else:
                st.warning("No files found in output directory")
        else:
            st.warning("Output directory not found or empty")
    except Exception as e:
        st.error(f"Could not list files: {e}")

# ============================================================================
# DOWNLOAD SECTION
# ============================================================================
st.divider()
st.header("⬇️ Download File")

# Pre-fill if a file was selected
if "remote_path" in st.session_state:
    default_remote = st.session_state.remote_path
    del st.session_state.remote_path
else:
    default_remote = ""

remote_path = st.text_input(
    "Remote File Path",
    value=default_remote,
    help="Full path to the file on HPC cluster"
)

if remote_path:
    st.caption(f"📍 Remote: `{remote_path}`")

# Local save path
local_home = os.path.expanduser("~")
download_dir = os.path.join(local_home, "Downloads")
default_filename = os.path.basename(remote_path) if remote_path else "download"

local_path = st.text_input(
    "Save As (Local Path)",
    value=os.path.join(download_dir, default_filename),
    help="Where to save the file locally"
)

# Download button
if st.button("📥 Download File", disabled=not remote_path, use_container_width=True, type="primary"):
    try:
        local_dir = os.path.dirname(local_path)
        if local_dir:
            os.makedirs(local_dir, exist_ok=True)
        
        with st.spinner(f"Downloading {os.path.basename(remote_path)}..."):
            client.download_results(remote_path, local_path)
        
        st.success(f"✅ Downloaded successfully!")
        st.info(f"📂 Saved to: `{local_path}`")
        
        if os.path.exists(local_path):
            file_size = os.path.getsize(local_path)
            st.metric("File Size", f"{file_size / (1024*1024):.2f} MB")
    except Exception as e:
        st.error(f"❌ Download failed: {e}")

# ============================================================================
# BATCH DOWNLOAD
# ============================================================================
st.divider()
st.header("📦 Batch Download")

st.info("🚧 Batch download feature coming soon! Download multiple files at once.")