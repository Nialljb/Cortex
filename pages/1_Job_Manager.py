import streamlit as st
import os
from hpc_client_ssh import HPCSSHClient

st.set_page_config(page_title="Job Manager", page_icon="🤖", layout="wide")

st.title("NAN Job Manager")

# Check connection
if not st.session_state.get("connected", False) or not st.session_state.get("client"):
    st.error("❌ Not connected to HPC cluster. Please connect using the sidebar.")
    st.stop()

client = st.session_state.client
username = st.session_state.username

try:
    hpc_username = client.get_username()  # or however your client stores this
except:
    # Fallback if client doesn't have this method
    hpc_username = st.session_state.get('hpc_username', 'username')

# Initialize job history
if "job_history" not in st.session_state:
    st.session_state.job_history = []

# Create tabs
tab1, tab2, tab3 = st.tabs(["🐳 Apptainer", "🔧 Scripts", "🔄 Workflows"])



def submit_batch_apptainer_jobs(
    client,
    bids_dir,
    output_dir,
    derivatives_dir,
    subject_filter,
    session_filter,
    container_config,
    selected_container,
    cpus,
    mem,
    gpus,
    time,
    work_dir,
    output_log_dir,
    bind_paths,
    custom_command=None,
    dry_run=False
):
    """
    Submit batch Apptainer jobs based on BIDS directory structure.
    
    Scans the BIDS directory for subjects/sessions and submits jobs
    to the SLURM scheduler.
    """
    import os
    import re
    from pathlib import Path
    from datetime import datetime
    
    job_list = []
    processed_sessions = 0
    skipped_sessions = 0
    failed_sessions = 0
    status = st.empty()
    
    # Parse subject filter
    if subject_filter:
        subjects_to_process = [s.strip() for s in subject_filter.split(',')]
    else:
        subjects_to_process = None
    
    # Check if BIDS directory exists ON THE HPC (not locally!)
    try:
        # Use client to check if directory exists on HPC
        dir_contents = client.list_directory(bids_dir)
        st.write(f"✅ Found BIDS directory on HPC: {bids_dir}")
    except Exception as e:
        st.error(f"BIDS directory does not exist on HPC: {bids_dir}")
        st.error(f"Error: {e}")
        return []
    
    # Find all subjects from the directory listing
    subjects = sorted([item for item in dir_contents if item.startswith('sub-')])
    
    if not subjects:
        st.warning(f"⚠️ No BIDS-format subjects found in directory")
        st.write("BIDS format requires subject directories to start with 'sub-'")
        
        # Show what's actually in the directory
        st.write(f"📂 Found {len(dir_contents)} items in directory:")
        
        # Create columns for better display
        cols = st.columns(3)
        for idx, item in enumerate(dir_contents[:30]):  # Show first 30 items
            with cols[idx % 3]:
                st.write(f"📁 {item}")
        
        if len(dir_contents) > 30:
            st.write(f"... and {len(dir_contents) - 30} more items")
        
        # Offer option to proceed anyway if there are directories
        if dir_contents:
            st.write("---")
            st.write("💡 **Non-BIDS directory detected**")
            
            use_non_bids = st.checkbox(
                f"Process all {len(dir_contents)} subdirectories as subjects (not BIDS compliant)?",
                help="This will treat each subdirectory as a subject, ignoring BIDS naming conventions"
            )
            
            if use_non_bids:
                st.info("⚠️ Running in non-BIDS mode. Directory structure may not match expected format.")
                subjects = dir_contents
            else:
                return []
        else:
            return []
    
    st.write(f"📊 Found {len(subjects)} subjects")
    
    # Show subjects being processed
    with st.expander("View subjects", expanded=False):
        for subj in subjects:
            st.write(f"  • {subj}")
    
    # Iterate through subjects
    for subject in subjects:
        subject_path = f"{bids_dir}/{subject}"
        
        # Apply subject filter
        if subjects_to_process and subject not in subjects_to_process:
            continue
        
        # Handle BIDS root processing (like fMRIPrep)
        if container_config["input_type"] == "bids_root":
            status.text(f"Processing... {subject}")
            
            try:
                # For these pipelines, we submit one job per subject
                if subject.startswith('sub-'):
                    subject_id = subject.replace('sub-', '')
                else:
                    subject_id = subject
                
                if custom_command:
                    command = custom_command.format(
                        bids_dir=bids_dir,
                        output_dir=output_dir,
                        subject=subject_id
                    )
                else:
                    command = container_config["command_template"].format(
                        bids_dir=bids_dir,
                        output_dir=output_dir,
                        subject=subject_id
                    )
                
                time_fmt = '%Y%m%d_%H%M%S'
                job_name = f"{container_config['output_name']}_{subject}_{datetime.now().strftime(time_fmt)}"
                log_file = f"{output_log_dir}/{job_name}.out"
                
                job_info = {
                    "subject": subject,
                    "command": command,
                    "job_name": job_name
                }
                
                if not dry_run:
                    # Submit job via HPC client
                    job = client.submit_apptainer_job(
                        image_path=container_config["image_path"],
                        command=command,
                        job_name=job_name,
                        work_dir=work_dir,
                        cpus=cpus,
                        mem=mem,
                        gpus=gpus,
                        time=time,
                        output_log=log_file,
                        bind_paths=bind_paths
                    )
                    job_info["job_id"] = job["job_id"]
                
                job_list.append(job_info)
                processed_sessions += 1
                
            except Exception as e:
                st.error(f"❌ Error processing {subject}: {e}")
                failed_sessions += 1
            
            continue
        
        # Find sessions for this subject
        try:
            subject_contents = client.list_directory(subject_path)
            sessions = sorted([d for d in subject_contents if d.startswith('ses-')])
        except Exception as e:
            st.warning(f"Could not list directory {subject_path}: {e}")
            skipped_sessions += 1
            continue
        
        # If no sessions, look directly in subject directory
        if not sessions:
            sessions = [None]  # Process at subject level
            st.write(f"  📁 {subject}: No sessions found, checking subject directory directly")
        else:
            st.write(f"  📁 {subject}: Found {len(sessions)} sessions")
        
        for session in sessions:
            if session is None:
                session_path = subject_path
                session_label = "no_session"
            else:
                session_path = f"{subject_path}/{session}"
                session_label = session
            
            # Apply session filter
            if session_filter and session and session_filter not in session:
                skipped_sessions += 1
                continue
            
            status.text(f"Processing... {subject}/{session_label}")
            
            inputfile = None
            input_filepath = None
            
            try:
                # Determine where to look for input files
                if container_config["input_type"] == "acquisition":
                    # Look in raw BIDS data
                    if container_config["input_subdir"]:
                        search_path = f"{session_path}/{container_config['input_subdir']}"
                    else:
                        search_path = session_path
                    
                    # List files in the search path on HPC
                    try:
                        file_list = client.list_directory(search_path)
                    except Exception as e:
                        st.write(f"    ⏭️ Skipping {subject}/{session_label}: '{container_config['input_subdir']}' directory not found")
                        skipped_sessions += 1
                        continue
                    
                    # Find files matching pattern
                    nii_files = [f for f in file_list if f.endswith('.nii.gz') or f.endswith('.nii')]
                    
                    if not nii_files:
                        st.write(f"    ⏭️ Skipping {subject}/{session_label}: No .nii/.nii.gz files found")
                        skipped_sessions += 1
                        continue
                    
                    for filename in nii_files:
                        if re.search(container_config["input_pattern"], filename):
                            inputfile = filename
                            input_filepath = f"{search_path}/{filename}"
                            break
                    
                    if not inputfile:
                        st.write(f"    ⏭️ Skipping {subject}/{session_label}: No files matching pattern '{container_config['input_pattern']}'")
                        st.write(f"       Available files: {nii_files[:3]}")
                        skipped_sessions += 1
                        continue
                        
                elif container_config["input_type"] == "derivatives":
                    # Look in derivatives directory
                    if not derivatives_dir:
                        st.warning(f"⏭️ Derivatives directory not specified")
                        skipped_sessions += 1
                        continue
                    
                    # Construct path to derivatives
                    deriv_path = f"{derivatives_dir}/{container_config['requires_derivative']}/{subject}"
                    if session:
                        deriv_path = f"{deriv_path}/{session}"
                    
                    if container_config["input_subdir"]:
                        deriv_path = f"{deriv_path}/{container_config['input_subdir']}"
                    
                    # Check if path exists on HPC
                    try:
                        file_list = client.list_directory(deriv_path)
                    except Exception as e:
                        st.write(f"    ⏭️ Skipping {subject}/{session_label}: No {container_config['requires_derivative']} output found")
                        skipped_sessions += 1
                        continue
                    
                    # Find matching file
                    nii_files = [f for f in file_list if f.endswith('.nii.gz') or f.endswith('.nii')]
                    
                    for filename in nii_files:
                        if re.search(container_config["input_pattern"], filename):
                            inputfile = filename
                            input_filepath = f"{deriv_path}/{filename}"
                            break
                    
                    if not inputfile:
                        st.write(f"    ⏭️ Skipping {subject}/{session_label}: No matching file in {container_config['requires_derivative']} output")
                        skipped_sessions += 1
                        continue
                
                # Prepare job submission
                if inputfile and input_filepath:
                    # Create subject/session specific output directory
                    if session:
                        session_output_dir = f"{output_dir}/{subject}/{session}"
                    else:
                        session_output_dir = f"{output_dir}/{subject}"
                    
                    # Format command
                    if custom_command:
                        command = custom_command.format(
                            input_file=input_filepath,
                            output_dir=session_output_dir,
                            subject=subject,
                            session=session if session else ""
                        )
                    else:
                        command = container_config["command_template"].format(
                            input_file=input_filepath,
                            output_dir=session_output_dir,
                            subject=subject,
                            session=session if session else ""
                        )
                    
                    time_fmt = '%Y%m%d_%H%M%S'
                    job_name = f"{container_config['output_name']}_{subject}_{session_label}_{datetime.now().strftime(time_fmt)}"
                    log_file = f"{output_log_dir}/{job_name}.out"
                    
                    job_info = {
                        "subject": subject,
                        "session": session_label,
                        "input_file": input_filepath,
                        "command": command,
                        "job_name": job_name
                    }
                    
                    if not dry_run:
                        # Submit job via HPC client
                        job = client.submit_apptainer_job(
                            image_path=container_config["image_path"],
                            command=command,
                            job_name=job_name,
                            work_dir=work_dir,
                            cpus=cpus,
                            mem=mem,
                            gpus=gpus,
                            time=time,
                            output_log=log_file,
                            bind_paths=bind_paths
                        )
                        job_info["job_id"] = job["job_id"]
                    
                    job_list.append(job_info)
                    processed_sessions += 1
                    st.write(f"    ✅ Prepared job for {subject}/{session_label}: {inputfile}")
                    
            except Exception as e:
                st.error(f"❌ Error processing {subject}/{session_label}: {e}")
                import traceback
                st.code(traceback.format_exc())
                failed_sessions += 1
    
    # Clear status and show summary
    status.empty()
    
    if dry_run:
        st.info(
            f"\n🔍 Dry Run Summary:\n"
            f"   ✅ Jobs to submit: {processed_sessions}\n"
            f"   ⏭️ Sessions to skip: {skipped_sessions}\n"
            f"   ❌ Sessions with errors: {failed_sessions}\n"
            f"   📋 Total jobs: {len(job_list)}"
        )
    else:
        st.info(
            f"\n📊 Summary:\n"
            f"   ✅ Jobs submitted: {processed_sessions}\n"
            f"   ⏭️ Sessions skipped: {skipped_sessions}\n"
            f"   ❌ Sessions failed: {failed_sessions}\n"
            f"   📋 Total job IDs: {len(job_list)}"
        )
    
    return job_list

# ============================================================================
# TAB 1: APPTAINER
# ============================================================================
with tab1:
    st.header("Submit Batch Apptainer Jobs")
    st.write("Run containerized applications on the HPC cluster.")
    

    # Define available containers with their configurations
    CONTAINER_CONFIGS = {
        "DebugTest": {
            "image_path": f"/home/{hpc_username}/repos/debug_test.sif",
            "command_template": "python /app/test_script.py --input {input_file} --output {output_dir} --subject {subject} --session {session}",
            "input_type": "acquisition",
            "input_pattern": r".*\.nii\.gz$",
            "input_subdir": "anat",
            "requires_derivative": None,
            "output_name": "debug_test",
            "default_cpus": 1,
            "default_mem": "2G",
            "default_gpus": 0,
            "default_time": "00:10:00",
            "description": "Debug test container for workflow validation"
        },
        "BabySeg": {
            "image_path": f"/home/{hpc_username}/images/babyseg.sif",
            "command_template": "python /app/run_babyseg.py --input {input_file} --output {output_dir}",
            "input_type": "acquisition",  # or "derivatives"
            "input_pattern": r".*_T2w\.nii\.gz$",
            "input_subdir": "anat",  # subdirectory within session (anat, func, dwi, etc.)
            "requires_derivative": None,  # None if raw data, or name of required pipeline
            "output_name": "babyseg",
            "default_cpus": 8,
            "default_mem": "32G",
            "default_gpus": 0,
            "default_time": "04:00:00",
            "description": "Infant brain segmentation"
        },
        "GAMBAS": {
            "image_path": f"/home/{hpc_username}/images/gambas.sif",
            "command_template": "python /app/run_gambas.py --input {input_file} --output {output_dir}",
            "input_type": "acquisition",
            "input_pattern": r".*_T2w\.nii\.gz$",
            "input_subdir": "anat",
            "requires_derivative": None,
            "output_name": "gambas",
            "default_cpus": 4,
            "default_mem": "16G",
            "default_gpus": 0,
            "default_time": "02:00:00",
            "description": "Brain tissue segmentation"
        },
        "Circumference": {
            "image_path": f"/home/{hpc_username}/images/circumference.sif",
            "command_template": "python /app/run_circumference.py --input {input_file} --output {output_dir}",
            "input_type": "derivatives",
            "input_pattern": r"(.*_mrr\.nii\.gz|.*_ResCNN\.nii\.gz|.*_T2w_gambas\.nii\.gz)$",
            "input_subdir": "anat",
            "requires_derivative": "gambas",  # Requires GAMBAS output
            "output_name": "circumference",
            "default_cpus": 4,
            "default_mem": "16G",
            "default_gpus": 0,
            "default_time": "01:00:00",
            "description": "Head circumference measurement (requires GAMBAS)"
        },
        "MRR": {
            "image_path": f"/home/{hpc_username}/images/mrr.sif",
            "command_template": "python /app/run_mrr.py --input {input_file} --output {output_dir}",
            "input_type": "acquisition",
            "input_pattern": r".*_T2w\.nii\.gz$",
            "input_subdir": "anat",
            "requires_derivative": None,
            "output_name": "mrr",
            "default_cpus": 4,
            "default_mem": "24G",
            "default_gpus": 0,
            "default_time": "03:00:00",
            "description": "MRI reconstruction and registration"
        },
        "fMRIPrep": {
            "image_path": f"/home/{hpc_username}/images/fmriprep.sif",
            "command_template": "fmriprep {bids_dir} {output_dir} participant --participant-label {subject}",
            "input_type": "bids_root",  # Uses entire BIDS directory
            "input_pattern": None,
            "input_subdir": None,
            "requires_derivative": None,
            "output_name": "fmriprep",
            "default_cpus": 8,
            "default_mem": "32G",
            "default_gpus": 0,
            "default_time": "24:00:00",
            "description": "fMRI preprocessing pipeline"
        }
    }
    
    # Container selection
    selected_container = st.selectbox(
        "Select Container",
        options=list(CONTAINER_CONFIGS.keys()),
        format_func=lambda x: f"{x} - {CONTAINER_CONFIGS[x]['description']}",
        help="Choose the containerized application to run"
    )
    
    config = CONTAINER_CONFIGS[selected_container]
    
    # Show info about input requirements
    if config["requires_derivative"]:
        st.info(f"⚠️ Note: The {selected_container} container requires {config['requires_derivative'].upper()} outputs as input. Ensure that {config['requires_derivative'].upper()} has been run on the sessions.")
    else:
        if config["input_type"] == "acquisition":
            st.info(f"ℹ️ This container will process raw acquisition data matching pattern: `{config['input_pattern']}`")
        elif config["input_type"] == "bids_root":
            st.info(f"ℹ️ This container processes entire BIDS datasets per subject")
    

    # Move project selection OUTSIDE the form so it can update dynamically
    try:
        project_dirs = client.list_project_directories()
        if project_dirs:
            selected_project = st.selectbox(
                "Select Project",
                options=project_dirs,
                help="Projects found in ~/projects/",
                key="selected_project"
            )
            # Construct bids_dir based on selected project
            bids_dir = f"/home/{hpc_username}/projects/{selected_project}"
            
            # # Debug output (can remove later)
            # st.write(f"🔍 Debug - selected_project: {selected_project}")
            # st.write(f"🔍 Debug - hpc_username: {hpc_username}")
            # st.write(f"🔍 Debug - Final bids_dir: {bids_dir}")
            
            selected_project_available = True
        else:
            st.warning("No projects found in ~/projects/")
            # Fallback to manual input
            bids_dir = st.text_input(
                "BIDS Directory", 
                f"/home/{hpc_username}/projects/remoteTest",
                key="manual_bids_dir"
            )
            selected_project = None
            selected_project_available = False
    except Exception as e:
        st.warning(f"Could not load projects: {e}")
        # Fallback to manual input
        bids_dir = st.text_input(
            "BIDS Directory", 
            f"/home/{hpc_username}/projects/remoteTest", 
            help="Path to your BIDS dataset root directory",
            key="fallback_bids_dir"
        )
        selected_project = None
        selected_project_available = False

    # Now create the form with the updated bids_dir
    with st.form("apptainer_batch_form"):
        st.subheader("Data Selection")
        
        # Display the selected paths (read-only info) - REMOVE the text_input here
        st.info(f"📁 BIDS Directory: `{bids_dir}`")
        
        # Remove this section completely if project was selected above:
        # DON'T INCLUDE THIS:
        # bids_dir = st.text_input("BIDS Directory", "/home/k2252514/projects/remoteTest")
        
        # Derivatives directory (for pipelines that need previous outputs)
        if config["requires_derivative"]:
            default_derivatives = f"{bids_dir}/derivatives"
            derivatives_dir = st.text_input(
                "Derivatives Directory",
                value=default_derivatives,
                help="Path to derivatives directory containing previous pipeline outputs"
            )
        else:
            derivatives_dir = None
        
        # Subject/Session filtering
        col1, col2 = st.columns(2)
        with col1:
            subject_filter = st.text_input(
                "Subject Filter (optional)",
                placeholder="e.g., sub-01, sub-02",
                help="Comma-separated list of subjects to process (leave empty for all)"
            )
        with col2:
            session_filter = st.text_input(
                "Session Filter (optional)",
                placeholder="e.g., ses-01",
                help="Filter sessions by label (leave empty to process all)"
            )
        
        # Output directory - computed from bids_dir
        default_output = f"{bids_dir}/derivatives/{config['output_name']}"
        output_dir = st.text_input(
            "Output Directory",
            value=default_output,
            help="Where to save the processing outputs"
        )
    

        
        # Advanced options
        with st.expander("Job Configuration", expanded=False):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                cpus = st.number_input("CPUs", min_value=1, max_value=64, value=config["default_cpus"])
            with col2:
                mem = st.text_input("Memory", config["default_mem"])
            with col3:
                gpus = st.number_input("GPUs", min_value=0, max_value=8, value=config["default_gpus"])
            with col4:
                time = st.text_input("Time Limit", config["default_time"])
            
            default_work_dir = f"{bids_dir}/work/{selected_container.lower()}"
            work_dir = st.text_input(
                "Working Directory", 
                value=default_work_dir,
                help="Temporary working directory for the job"
            )
            
            default_log_dir = f"{bids_dir}/logs/{selected_container.lower()}"
            output_log_dir = st.text_input(
                "Log Directory",
                value=default_log_dir,
                help="Directory to save SLURM logs"
            )
            
            # Bind paths for Apptainer
            bind_paths = st.text_area(
                "Additional Bind Paths (optional)",
                placeholder="/data,/scratch,/tmp",
                help="Comma-separated list of paths to bind into the container"
            )
            
            # Custom command override (optional)
            use_custom_command = st.checkbox("Use custom command template")
            if use_custom_command:
                custom_command = st.text_area(
                    "Custom Command Template",
                    config["command_template"],
                    help="Override the default command template. Use {input_file}, {output_dir}, {subject}, {session} as placeholders"
                )
            else:
                custom_command = None
        
        # Dry run option
        dry_run = st.checkbox(
            "Dry run (show jobs without submitting)",
            value=False,
            help="Preview what jobs would be submitted without actually submitting them"
        )
        

        # Custom CSS for the submit button
        st.html("""
        <style>
        .stForm button, .stButton>button {
            background: #1a73e8 !important;
            color: white !important;
            border: 1px solid #1666c1 !important;
            border-radius: 12px !important;
            padding: 0.55rem 1.3rem !important;
            font-weight: 500 !important;
            font-size: 0.95rem !important;

            box-shadow: 0 2px 4px rgba(0,0,0,0.08) !important;
            transition: background 0.25s ease, transform 0.2s ease !important;
        }

        .stForm button:hover, .stButton>button:hover {
            background: #1966d2 !important;
            transform: translateY(-1px) !important;
        }

        .stForm button:active, .stButton>button:active {
            background: #155bbf !important;
            transform: translateY(0px) !important;
        }
        </style>
        """)


        submit = st.form_submit_button("Submit Batch Jobs", use_container_width=True)
        
        if submit:
            if not bids_dir or not output_dir:
                st.error("❌ Please enter BIDS directory and output directory")
            else:
                try:
                    with st.spinner("Scanning BIDS directory and preparing jobs..."):
                        job_list = submit_batch_apptainer_jobs(
                            client=client,
                            bids_dir=bids_dir,
                            output_dir=output_dir,
                            derivatives_dir=derivatives_dir if config["requires_derivative"] else None,
                            subject_filter=subject_filter,
                            session_filter=session_filter,
                            container_config=config,
                            selected_container=selected_container,
                            cpus=cpus,
                            mem=mem,
                            gpus=gpus,
                            time=time,
                            work_dir=work_dir,
                            output_log_dir=output_log_dir,
                            bind_paths=bind_paths,
                            custom_command=custom_command,
                            dry_run=dry_run
                        )
                    
                    if not dry_run:
                        # Store jobs in session state
                        for job_info in job_list:
                            st.session_state.job_history.append({
                                "job_id": job_info["job_id"],
                                "type": "Apptainer",
                                "name": f"{selected_container}_{job_info['subject']}_{job_info.get('session', '')}"
                            })
                        
                        st.success(f"✅ Successfully submitted {len(job_list)} jobs")
                    else:
                        st.info(f"🔍 Dry run complete: {len(job_list)} jobs would be submitted")
                    
                    # Show job details
                    with st.expander("View Job Details", expanded=True):
                        for job_info in job_list:
                            if dry_run:
                                st.write(f"**Would submit:** {job_info['subject']}/{job_info.get('session', 'N/A')}")
                            else:
                                st.write(f"**Job ID:** {job_info['job_id']} - {job_info['subject']}/{job_info.get('session', 'N/A')}")
                            st.code(job_info['command'], language='bash')
                            st.divider()
                            
                except Exception as e:
                    st.error(f"❌ Failed to submit batch jobs: {e}")
                    import traceback
                    st.code(traceback.format_exc())




# ============================================================================
# TAB 2: Scripts
# ============================================================================
with tab2:
    st.header("Run Pre-configured Script")
    st.write("Execute pipeline scripts with specific configurations.")
    
    # Script definitions
    scripts = {
        "Structural Segmentation": f"/home/{username}/scripts/run_segmentation.sh",
        "DTI Pipeline": f"/home/{username}/scripts/run_dti.sh",
        "fMRI Preprocessing": f"/home/{username}/scripts/run_fmri.sh",
        "Hello World": f"/home/{username}/scripts/hello_world.sh",
    }
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        selected_script = st.selectbox(
            "Select Script",
            options=list(scripts.keys()),
            help="Choose a pre-configured pipeline script to run"
        )
        
        # Get project directories
        try:
            project_dirs = client.list_project_directories()
            if project_dirs:
                selected_project = st.selectbox(
                    "Select Project",
                    options=project_dirs,
                    help="Projects found in ~/projects/"
                )
            else:
                st.warning("No projects found in ~/projects/")
                selected_project = st.text_input("Project Name", "my_project")
        except Exception as e:
            st.warning(f"Could not load projects: {e}")
            selected_project = st.text_input("Project Name", "my_project")
    
    with col2:
        st.info(f"**Script:** `{scripts[selected_script]}`")
        st.info(f"**Project Path:** `~/projects/{selected_project}`")
    
    if st.button("👾 Submit Script Job", use_container_width=True):
        script = scripts[selected_script]
        job_name = selected_script.replace(" ", "_")
        
        try:
            with st.spinner("Submitting script job..."):
                job = client.submit_job(script, job_name=job_name)
            st.session_state.job_id = job["job_id"]
            st.session_state.job_history.append({
                "job_id": job["job_id"],
                "type": "Script",
                "name": selected_script,
                "project": selected_project
            })
            st.success(f"✅ Submitted job {job['job_id']}")
        except Exception as e:
            st.error(f"❌ Failed to submit job: {e}")

# ============================================================================
# TAB 3: WORKFLOWS
# ============================================================================
with tab3:
    st.header("Multi-Step Workflows")
    st.write("Chain multiple jobs together with dependencies.")
    
    st.info("🚧 Workflow feature coming soon! This will allow you to create complex pipelines with multiple dependent jobs.")
    
    st.markdown("""
    ### Planned Features:
    - **Job Dependencies**: Chain jobs so they run in sequence
    - **Parallel Execution**: Run multiple independent jobs simultaneously
    - **Conditional Logic**: Branch workflows based on results
    - **Workflow Templates**: Save and reuse common workflows
    - **Visual Pipeline Builder**: Drag-and-drop interface for creating workflows
    """)
    
    # Placeholder for future workflow builder
    with st.expander("Example Workflow Structure"):
        st.code("""
        workflow:
          name: "MRI Processing Pipeline"
          steps:
            - id: preprocessing
              type: node
              node: "Structural Segmentation"
              
            - id: dti
              type: node
              node: "DTI Pipeline"
              depends_on: [preprocessing]
              
            - id: fmri
              type: node
              node: "fMRI Preprocessing"
              depends_on: [preprocessing]
        """, language="yaml")

# ============================================================================
# JOB MONITORING SECTION
# ============================================================================
st.divider()
st.header("📊 Job Monitoring")

col1, col2 = st.columns([2, 1])

with col1:
    if "job_id" in st.session_state:
        job_id = st.session_state.job_id
        
        if st.button("🔄 Check Job Status", use_container_width=True):
            try:
                status = client.job_status(job_id)
                
                status_colors = {
                    "RUNNING": "🟢",
                    "PENDING": "🟡",
                    "COMPLETED": "✅",
                    "FAILED": "❌",
                    "CANCELLED": "🚫"
                }
                
                status_icon = status_colors.get(status, "⚪")
                st.info(f"{status_icon} Job **{job_id}** status: **{status}**")
            except Exception as e:
                st.error(f"Failed to check status: {e}")
    else:
        st.info("No active job. Submit a job to monitor its status.")

with col2:
    if st.session_state.job_history:
        st.metric("Total Jobs Submitted", len(st.session_state.job_history))
    else:
        st.metric("Total Jobs Submitted", 0)

# Job history
if st.session_state.job_history:
    with st.expander("📜 Job History", expanded=False):
        for idx, job in enumerate(reversed(st.session_state.job_history[-10:])):
            st.text(f"{idx+1}. Job {job['job_id']} - {job['type']}: {job['name']}")