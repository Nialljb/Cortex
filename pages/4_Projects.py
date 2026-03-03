import streamlit as st
import pandas as pd
from datetime import datetime
from functools import lru_cache

st.set_page_config(
    page_title="Projects",
    page_icon="📁",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize cache in session state
if 'data_cache' not in st.session_state:
    st.session_state.data_cache = {}

# Helper functions
def get_cached_or_fetch(cache_key, fetch_func):
    """Cache results to avoid redundant SSH calls."""
    if cache_key in st.session_state.data_cache:
        return st.session_state.data_cache[cache_key]
    
    result = fetch_func()
    st.session_state.data_cache[cache_key] = result
    return result

def clear_cache():
    """Clear the data cache."""
    st.session_state.data_cache = {}

def get_projects(client):
    """Get list of projects from ~/projects directory."""
    def fetch():
        try:
            result = client._run("find $HOME/projects -maxdepth 1 -mindepth 1 -type d -exec basename {{}} \\;")
            if result:
                projects = [p.strip() for p in result.split('\n') if p.strip()]
                return sorted(projects)
            return []
        except Exception as e:
            st.error(f"Error fetching projects: {e}")
            return []
    
    return get_cached_or_fetch('projects_list', fetch)

def count_subjects_and_sessions(client, project_path):
    """Count the number of subjects and sessions in a project."""
    try:
        # Count subjects (first-level directories)
        result_subjects = client._run(
            f"find {project_path} -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l"
        )
        num_subjects = int(result_subjects.strip()) if result_subjects else 0
        
        # Count sessions (second-level directories)
        result_sessions = client._run(
            f"find {project_path} -maxdepth 2 -mindepth 2 -type d 2>/dev/null | wc -l"
        )
        num_sessions = int(result_sessions.strip()) if result_sessions else 0
        
        return num_subjects, num_sessions
    except Exception as e:
        return 0, 0

def get_subjects(client, project_path):
    """Get list of subjects in a project."""
    try:
        result = client._run(f"find {project_path} -maxdepth 1 -mindepth 1 -type d -exec basename {{}} \\;")
        if result:
            subjects = [s.strip() for s in result.split('\n') if s.strip()]
            return sorted(subjects)
        return []
    except Exception as e:
        return []

def get_sessions(client, subject_path):
    """Get list of sessions for a subject."""
    try:
        result = client._run(f"find {subject_path} -maxdepth 1 -mindepth 1 -type d -exec basename {{}} \\;")
        if result:
            sessions = [s.strip() for s in result.split('\n') if s.strip()]
            return sorted(sessions)
        return []
    except Exception as e:
        return []

def get_acquisitions(client, session_path):
    """Get list of acquisition directories in a session."""
    try:
        result = client._run(f"find {session_path} -maxdepth 1 -mindepth 1 -type d -exec basename {{}} \\;")
        if result:
            acquisitions = [a.strip() for a in result.split('\n') if a.strip()]
            return sorted(acquisitions)
        return []
    except Exception as e:
        return []

def get_files_in_directory(client, directory_path):
    """Get list of files in a directory with their sizes and modification times."""
    try:
        # Use simple ls -lh (most reliable)
        result = client._run(f"ls -lh {directory_path}")
        
        if not result:
            return []
        
        # Parse ls -lh output
        files = []
        for line in result.split('\n'):
            line = line.strip()
            
            # Skip empty lines and total line
            if not line or line.startswith('total'):
                continue
            
            # Only process file lines (starting with -)
            if not line.startswith('-'):
                continue
            
            # Split by whitespace
            parts = line.split()
            
            # ls -lh format: permissions links owner group size month day time filename
            # Example: -rw-------. 1 k2252514 k2252514 842K Nov 18 13:50 sub-HYPE00_ses-HFC_acq-iso_T2w.nii.gz
            if len(parts) >= 9:
                size = parts[4]
                month = parts[5]
                day = parts[6]
                time = parts[7]
                filename = ' '.join(parts[8:])  # Handle filenames with spaces
                
                if filename not in ['.', '..']:
                    files.append({
                        'name': filename,
                        'size': size,
                        'modified': f"{month} {day} {time}",
                        'path': f"{directory_path}/{filename}"
                    })
        
        return files
    except Exception as e:
        st.error(f"Error getting files: {e}")
        import traceback
        st.code(traceback.format_exc())
        return []

def get_file_content(client, file_path, max_lines=100):
    """Get file content for viewing."""
    try:
        # Check file size first
        size_result = client._run(f"stat -f%z {file_path} 2>/dev/null || stat -c%s {file_path} 2>/dev/null")
        file_size = int(size_result.strip()) if size_result else 0
        
        # If file is too large, only show first N lines
        if file_size > 1000000:  # 1MB
            result = client._run(f"head -n {max_lines} {file_path}")
            return result, True  # True indicates truncated
        else:
            result = client._run(f"cat {file_path}")
            return result, False
    except Exception as e:
        return f"Error reading file: {e}", False

# Initialize session state for navigation
if 'current_view' not in st.session_state:
    st.session_state.current_view = 'projects'  # projects, sessions, acquisitions, file
if 'selected_project' not in st.session_state:
    st.session_state.selected_project = None
if 'selected_subject' not in st.session_state:
    st.session_state.selected_subject = None
if 'selected_session' not in st.session_state:
    st.session_state.selected_session = None
if 'selected_acquisition' not in st.session_state:
    st.session_state.selected_acquisition = None
if 'selected_file' not in st.session_state:
    st.session_state.selected_file = None

# Main page
col1, col2 = st.columns([4, 1])
with col1:
    st.title("📁 Projects")
with col2:
    if st.button("🔄 Refresh", help="Clear cache and reload data"):
        clear_cache()
        st.rerun()

# Check connection
if not st.session_state.get("connected") or not st.session_state.get("client"):
    st.warning("⚠️ No HPC connection. Please connect via the Home page.")
    if st.button("Go to Home", use_container_width=True):
        st.switch_page("Home.py")
    st.stop()

client = st.session_state.client

# Breadcrumb navigation
breadcrumbs = ["Projects"]
if st.session_state.selected_project:
    breadcrumbs.append(st.session_state.selected_project)
if st.session_state.selected_subject:
    breadcrumbs.append(st.session_state.selected_subject)
if st.session_state.selected_session:
    breadcrumbs.append(st.session_state.selected_session)
if st.session_state.selected_acquisition:
    breadcrumbs.append(st.session_state.selected_acquisition)
if st.session_state.selected_file:
    breadcrumbs.append(st.session_state.selected_file)

# Display breadcrumb with clickable navigation
cols = st.columns(len(breadcrumbs) + (len(breadcrumbs) - 1))
for idx, crumb in enumerate(breadcrumbs):
    col_idx = idx * 2
    with cols[col_idx]:
        if idx == 0:
            if st.button("🏠 " + crumb, key=f"breadcrumb_{idx}"):
                st.session_state.current_view = 'projects'
                st.session_state.selected_project = None
                st.session_state.selected_subject = None
                st.session_state.selected_session = None
                st.session_state.selected_acquisition = None
                st.session_state.selected_file = None
                st.rerun()
        elif idx == 1:
            if st.button(crumb, key=f"breadcrumb_{idx}"):
                st.session_state.current_view = 'sessions'
                st.session_state.selected_subject = None
                st.session_state.selected_session = None
                st.session_state.selected_acquisition = None
                st.session_state.selected_file = None
                st.rerun()
        elif idx == 2:
            if st.button(crumb, key=f"breadcrumb_{idx}"):
                st.session_state.current_view = 'sessions'
                st.session_state.selected_session = None
                st.session_state.selected_acquisition = None
                st.session_state.selected_file = None
                st.rerun()
        elif idx == 3:
            if st.button(crumb, key=f"breadcrumb_{idx}"):
                st.session_state.current_view = 'acquisitions'
                st.session_state.selected_acquisition = None
                st.session_state.selected_file = None
                st.rerun()
        elif idx == 4:
            if st.button(crumb, key=f"breadcrumb_{idx}"):
                st.session_state.current_view = 'acquisitions'
                st.session_state.selected_file = None
                st.rerun()
        else:
            st.write(f"**{crumb}**")
    
    # Add separator
    if idx < len(breadcrumbs) - 1 and col_idx + 1 < len(cols):
        with cols[col_idx + 1]:
            st.write("›")

st.markdown("---")

# PROJECTS VIEW
if st.session_state.current_view == 'projects':
    st.subheader("All Projects")
    
    with st.spinner("Loading projects..."):
        projects = get_projects(client)
    
    if not projects:
        st.info("No projects found in ~/projects directory")
        st.stop()
    
    # Get absolute home directory path
    home_dir = client._run("echo $HOME").strip()
    
    # Create a table of projects with summary stats
    project_data = []
    progress_bar = st.progress(0)
    
    for idx, project in enumerate(projects):
        project_path = f"{home_dir}/projects/{project}"
        num_subjects, num_sessions = count_subjects_and_sessions(client, project_path)
        project_data.append({
            'Project': project,
            'Subjects': num_subjects,
            'Sessions': num_sessions
        })
        progress_bar.progress((idx + 1) / len(projects))
    
    progress_bar.empty()
    
    df = pd.DataFrame(project_data)
    
    st.write("👆 Click on a project to view its sessions")
    
    # Display as a table with clickable rows
    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Project": st.column_config.TextColumn("Project", width="large"),
            "Subjects": st.column_config.NumberColumn("Subjects", width="small"),
            "Sessions": st.column_config.NumberColumn("Sessions", width="small")
        }
    )
    
    # Handle row selection
    if event.selection.rows:
        selected_idx = event.selection.rows[0]
        selected_project = df.iloc[selected_idx]['Project']
        st.session_state.selected_project = selected_project
        st.session_state.current_view = 'sessions'
        st.rerun()

# SESSIONS VIEW (Subject/Session list)
elif st.session_state.current_view == 'sessions':
    st.subheader(f"Sessions in {st.session_state.selected_project}")
    
    # Get absolute home directory path
    home_dir = client._run("echo $HOME").strip()
    project_path = f"{home_dir}/projects/{st.session_state.selected_project}"
    
    with st.spinner("Loading subjects and sessions..."):
        subjects = get_subjects(client, project_path)
    
    if not subjects:
        st.info("No subjects found in this project")
        st.stop()
    
    # Build session data
    session_data = []
    progress_bar = st.progress(0)
    
    for idx, subject in enumerate(subjects):
        subject_path = f"{project_path}/{subject}"
        sessions = get_sessions(client, subject_path)
        
        for session in sessions:
            session_path = f"{subject_path}/{session}"
            acquisitions = get_acquisitions(client, session_path)
            
            session_data.append({
                'Subject': subject,
                'Session': session,
                'Acquisitions': len(acquisitions)
            })
        
        progress_bar.progress((idx + 1) / len(subjects))
    
    progress_bar.empty()
    
    if not session_data:
        st.info("No sessions found")
        st.stop()
    
    df = pd.DataFrame(session_data)
    
    st.write("👆 Click on a row to view acquisitions")
    
    # Display table with selection
    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Subject": st.column_config.TextColumn("Subject", width="medium"),
            "Session": st.column_config.TextColumn("Session", width="medium"),
            "Acquisitions": st.column_config.NumberColumn("Acquisitions", width="small")
        }
    )
    
    # Handle row selection
    if event.selection.rows:
        selected_idx = event.selection.rows[0]
        selected_row = df.iloc[selected_idx]
        st.session_state.selected_subject = selected_row['Subject']
        st.session_state.selected_session = selected_row['Session']
        st.session_state.current_view = 'acquisitions'
        st.rerun()

# ACQUISITIONS VIEW
elif st.session_state.current_view == 'acquisitions':
    st.subheader(f"Acquisitions: {st.session_state.selected_subject} / {st.session_state.selected_session}")
    
    # Get the absolute home directory path first
    home_dir = client._run("echo $HOME").strip()
    session_path = f"{home_dir}/projects/{st.session_state.selected_project}/{st.session_state.selected_subject}/{st.session_state.selected_session}"
    
    with st.spinner("Loading acquisitions..."):
        acquisitions = get_acquisitions(client, session_path)
    
    if not acquisitions:
        st.warning("No acquisition subdirectories found in this session")
        st.info("Checking for files directly in session folder...")
        
        # Check if there are files directly in the session folder
        files = get_files_in_directory(client, session_path)
        
        if files:
            st.success(f"Found {len(files)} file(s) directly in session folder")
            
            # Display files
            for idx, file_info in enumerate(files):
                col1, col2, col3, col4 = st.columns([3, 1, 2, 1])
                
                with col1:
                    if st.button(f"📄 {file_info['name']}", key=f"file_session_{idx}"):
                        st.session_state.selected_acquisition = "session_root"
                        st.session_state.selected_file = file_info['name']
                        st.session_state.selected_file_path = file_info['path']
                        st.session_state.current_view = 'file'
                        st.rerun()
                
                with col2:
                    st.text(file_info['size'])
                
                with col3:
                    st.text(file_info['modified'])
        else:
            st.info("No files found in this session")
        
        st.stop()
    
    # Display acquisitions as expandable sections
    for acquisition in acquisitions:
        with st.expander(f"📂 {acquisition}", expanded=True):
            acquisition_path = f"{session_path}/{acquisition}"
            
            # Debug info
            with st.spinner(f"Loading files from {acquisition}..."):
                files = get_files_in_directory(client, acquisition_path)
            
            if files:
                st.success(f"Found {len(files)} file(s)")
                
                # Display files
                for idx, file_info in enumerate(files):
                    col1, col2, col3, col4 = st.columns([3, 1, 2, 1])
                    
                    with col1:
                        if st.button(f"📄 {file_info['name']}", key=f"file_{acquisition}_{idx}"):
                            st.session_state.selected_acquisition = acquisition
                            st.session_state.selected_file = file_info['name']
                            st.session_state.selected_file_path = file_info['path']
                            st.session_state.current_view = 'file'
                            st.rerun()
                    
                    with col2:
                        st.text(file_info['size'])
                    
                    with col3:
                        st.text(file_info['modified'])
                    
                    with col4:
                        st.text("")
            else:
                # Show debug info
                st.warning("No files found")
                
                # Try alternative listing method
                with st.expander("🔍 Debug Info"):
                    st.code(f"Path: {acquisition_path}")
                    
                    # Try simple ls (capture both stdout and stderr)
                    debug_result = client._run(f"ls -lh {acquisition_path}")
                    st.text("Directory listing (ls -lh):")
                    st.code(debug_result if debug_result else "Empty result")
                    
                    # Try without -lh
                    debug_result2 = client._run(f"ls {acquisition_path}")
                    st.text("Directory listing (ls):")
                    st.code(debug_result2 if debug_result2 else "Empty result")
                    
                    # Try with find
                    debug_result3 = client._run(f"find {acquisition_path} -type f")
                    st.text("Files (find):")
                    st.code(debug_result3 if debug_result3 else "Empty result")
                    
                    # Check if path exists
                    exists_check = client._run(f"test -d {acquisition_path} && echo 'EXISTS' || echo 'NOT FOUND'")
                    st.text(f"Path exists: {exists_check}")

# FILE VIEW
elif st.session_state.current_view == 'file':
    st.subheader(f"File: {st.session_state.selected_file}")
    
    file_path = st.session_state.selected_file_path
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.info(f"📂 Path: `{file_path}`")
    with col2:
        if st.button("⬅️ Back to Acquisitions"):
            st.session_state.current_view = 'acquisitions'
            st.session_state.selected_file = None
            st.rerun()
    
    # File viewer
    with st.spinner("Loading file..."):
        content, truncated = get_file_content(client, file_path)
    
    if truncated:
        st.warning("⚠️ File is large. Showing first 100 lines only.")
    
    # Determine file type and display accordingly
    file_ext = st.session_state.selected_file.split('.')[-1].lower()
    
    if file_ext in ['txt', 'log', 'sh', 'py', 'json', 'yaml', 'yml', 'md']:
        st.code(content, language=file_ext if file_ext in ['py', 'json', 'yaml', 'sh'] else None)
    elif file_ext in ['jpg', 'jpeg', 'png', 'gif']:
        st.info("Image preview not available via SSH. Use Download Data page to view images locally.")
    elif file_ext in ['nii', 'nii.gz', 'dicom', 'dcm']:
        st.info("Medical imaging file. Use specialized viewers or download to view.")
    else:
        st.text_area("File Content", content, height=400)

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray; font-size: 0.8em;'>
    💡 Navigate through your project hierarchy using the breadcrumbs above
    </div>
    """,
    unsafe_allow_html=True
)