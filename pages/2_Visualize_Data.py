import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

from utils.sidebar import render_project_selector
from utils.bids import (
    get_projects,
    count_subjects_and_sessions,
    get_subjects,
    get_sessions,
    get_acquisitions,
    get_files_in_directory,
)

st.set_page_config(
    page_title="Visualize Data",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

def create_tree_diagram(subjects_data):
    """Create a treemap visualization of subjects and sessions."""
    data = []
    for subject, sessions in subjects_data.items():
        for session in sessions:
            data.append({
                'Subject': subject,
                'Session': session,
                'Count': 1
            })
    
    if not data:
        return None
    
    df = pd.DataFrame(data)
    fig = px.treemap(
        df,
        path=['Subject', 'Session'],
        values='Count',
        title='Subject and Session Distribution',
        color='Count',
        color_continuous_scale='Viridis'
    )
    fig.update_layout(height=500)
    
    return fig

def create_session_bar_chart(subjects_data):
    """Create a bar chart showing sessions per subject."""
    if not subjects_data:
        return None
    
    session_counts = {subject: len(sessions) for subject, sessions in subjects_data.items()}
    
    fig = go.Figure(data=[
        go.Bar(
            x=list(session_counts.keys()),
            y=list(session_counts.values()),
            marker_color='indianred',
            text=list(session_counts.values()),
            textposition='auto',
        )
    ])
    fig.update_layout(
        title="Sessions per Subject",
        xaxis_title="Subject",
        yaxis_title="Number of Sessions",
        height=400,
        showlegend=False
    )
    
    return fig

# Main page
st.title("📊 Visualize Data")

# Check connection
if not st.session_state.get("connected") or not st.session_state.get("client"):
    st.warning("⚠️ No HPC connection. Please connect via the Home page.")
    if st.button("Go to Home", use_container_width=True):
        st.switch_page("Home.py")
    st.stop()

client = st.session_state.client

# Sidebar: global project selector
render_project_selector(client)

# Cache home dir to avoid repeated SSH calls
if "_home_dir" not in st.session_state:
    st.session_state["_home_dir"] = client._run("echo $HOME").strip()
home_dir = st.session_state["_home_dir"]

selected_project = st.session_state.get("selected_project")
if not selected_project:
    st.info("Select a project from the sidebar to get started.")
    st.stop()

project_path = f"{home_dir}/projects/{selected_project}"

# Display project summary
with st.spinner("Loading project summary..."):
    num_subjects, num_sessions = count_subjects_and_sessions(client, project_path)

# Summary metrics at the top
st.markdown("---")
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="📁 Project", value=selected_project)
with col2:
    st.metric(label="👥 Subjects", value=num_subjects)
with col3:
    st.metric(label="📊 Sessions", value=num_sessions)

st.markdown("---")

# Get subjects for detailed view
subjects = get_subjects(client, project_path)

if not subjects:
    st.info("No subjects found in this project.")
    st.stop()

# Tabs for different views
tab1, tab2, tab3 = st.tabs(["🗂️ Browser", "📈 Visualizations", "📋 Details"])

with tab1:
    st.subheader("Data Browser")
    st.write("Navigate through your project's hierarchical structure.")
    
    # Subject selection
    selected_subject = st.selectbox(
        "Select Subject:",
        options=[""] + subjects,
        key="viz_subject_selector",
        help="Choose a subject to view its sessions"
    )
    
    if selected_subject:
        subject_path = f"{project_path}/{selected_subject}"
        
        # Get sessions for selected subject
        with st.spinner(f"Loading sessions for {selected_subject}..."):
            sessions = get_sessions(client, subject_path)
        
        if sessions:
            st.success(f"✅ Found {len(sessions)} session(s) for **{selected_subject}**")
            
            # Session selection
            selected_session = st.selectbox(
                "Select Session:",
                options=[""] + sessions,
                key="viz_session_selector",
                help="Choose a session to view its acquisitions"
            )
            
            if selected_session:
                session_path = f"{subject_path}/{selected_session}"
                
                # Get acquisitions
                with st.spinner(f"Loading acquisitions for {selected_session}..."):
                    acquisitions = get_acquisitions(client, session_path)
                
                if acquisitions:
                    st.success(f"✅ Found {len(acquisitions)} acquisition(s) in **{selected_session}**")
                    
                    # Acquisition selection
                    selected_acquisition = st.selectbox(
                        "Select Acquisition:",
                        options=[""] + acquisitions,
                        key="viz_acquisition_selector",
                        help="Choose an acquisition to view its files"
                    )
                    
                    if selected_acquisition:
                        acquisition_path = f"{session_path}/{selected_acquisition}"
                        
                        # Get files
                        with st.spinner(f"Loading files from {selected_acquisition}..."):
                            files = get_files_in_directory(client, acquisition_path)
                        
                        if files:
                            st.success(f"✅ Found {len(files)} file(s) in **{selected_acquisition}**")
                            
                            # Display files in a table
                            df_files = pd.DataFrame(files)
                            st.dataframe(
                                df_files,
                                use_container_width=True,
                                hide_index=True,
                                column_config={
                                    "name": st.column_config.TextColumn("File Name", width="large"),
                                    "size": st.column_config.TextColumn("Size", width="small"),
                                    "modified": st.column_config.TextColumn("Modified", width="medium")
                                }
                            )
                            
                            # Show full path
                            st.info(f"📂 Full path: `{acquisition_path}`")
                        else:
                            st.info("No files found in this acquisition.")
                else:
                    st.info("No acquisition directories found in this session.")
        else:
            st.info("No sessions found for this subject.")

with tab2:
    st.subheader("Data Visualizations")
    st.write("Visual representations of your project's data structure.")
    
    # Collect data for visualization
    with st.spinner("Building visualization data..."):
        subjects_data = {}
        
        # Limit to first 20 subjects for performance
        display_subjects = subjects[:20]
        if len(subjects) > 20:
            st.info(f"📊 Showing visualizations for first 20 of {len(subjects)} subjects for performance.")
        
        progress_bar = st.progress(0)
        for idx, subject in enumerate(display_subjects):
            subject_path = f"{project_path}/{subject}"
            sessions = get_sessions(client, subject_path)
            if sessions:
                subjects_data[subject] = sessions
            progress_bar.progress((idx + 1) / len(display_subjects))
        progress_bar.empty()
    
    if subjects_data:
        # Create treemap
        st.markdown("#### Hierarchical View")
        fig_tree = create_tree_diagram(subjects_data)
        if fig_tree:
            st.plotly_chart(fig_tree, use_container_width=True)
        
        st.markdown("---")
        
        # Session count per subject bar chart
        st.markdown("#### Session Distribution")
        fig_bar = create_session_bar_chart(subjects_data)
        if fig_bar:
            st.plotly_chart(fig_bar, use_container_width=True)
        
        # Summary statistics
        st.markdown("---")
        st.markdown("#### Summary Statistics")
        col1, col2, col3, col4 = st.columns(4)
        
        total_sessions = sum(len(sessions) for sessions in subjects_data.values())
        avg_sessions = total_sessions / len(subjects_data) if subjects_data else 0
        max_sessions = max(len(sessions) for sessions in subjects_data.values()) if subjects_data else 0
        min_sessions = min(len(sessions) for sessions in subjects_data.values()) if subjects_data else 0
        
        with col1:
            st.metric("Total Sessions", total_sessions)
        with col2:
            st.metric("Avg Sessions/Subject", f"{avg_sessions:.1f}")
        with col3:
            st.metric("Max Sessions", max_sessions)
        with col4:
            st.metric("Min Sessions", min_sessions)
    else:
        st.info("No data available for visualization.")

with tab3:
    st.subheader("Detailed Information")
    st.write("Expandable view of all subjects, sessions, and acquisitions.")
    
    # Search/filter functionality
    search_term = st.text_input(
        "🔍 Search subjects:",
        placeholder="Type to filter subjects...",
        help="Filter the subject list by name"
    )
    
    # Filter subjects based on search
    filtered_subjects = [s for s in subjects if search_term.lower() in s.lower()] if search_term else subjects
    
    if search_term and not filtered_subjects:
        st.warning(f"No subjects found matching '{search_term}'")
    else:
        st.info(f"Showing {len(filtered_subjects)} of {len(subjects)} subjects")
        
        # Create expandable sections for each subject
        for subject in filtered_subjects:
            with st.expander(f"👤 {subject}", expanded=False):
                subject_path = f"{project_path}/{subject}"
                
                with st.spinner("Loading..."):
                    sessions = get_sessions(client, subject_path)
                
                if sessions:
                    st.write(f"**Number of sessions:** {len(sessions)}")
                    
                    # Show sessions in a more structured way
                    for session in sessions:
                        session_path = f"{subject_path}/{session}"
                        acquisitions = get_acquisitions(client, session_path)
                        
                        with st.container():
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.write(f"📅 **{session}**")
                            with col2:
                                st.write(f"*{len(acquisitions)} acquisition(s)*")
                            
                            if acquisitions:
                                # Show acquisitions as comma-separated list
                                acq_display = ", ".join(acquisitions[:5])
                                if len(acquisitions) > 5:
                                    acq_display += f" ... +{len(acquisitions) - 5} more"
                                st.write(f"  └─ {acq_display}")
                else:
                    st.info("No sessions found for this subject.")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray; font-size: 0.8em;'>
    💡 Tip: Use the Browser tab to explore individual files, Visualizations for overview, and Details for comprehensive listing.
    </div>
    """,
    unsafe_allow_html=True
)