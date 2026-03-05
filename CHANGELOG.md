# Changelog

All significant changes to Cortex are recorded here.
Format: `## YYYY-MM-DD` heading, then one entry per change with file(s) and reason.

---

## 2026-03-05

### Pipeline manifest & workflow system
- **`hpc_client_ssh.py`** — added `read_pipeline_manifest()`, `write_pipeline_manifest()`, `poll_job_statuses()`: persistent JSON status tracking per project stored at `<project>/.cortex/pipeline_status.json` on the HPC.
- **`hpc_client_ssh.py`** — added `dependency_job_ids` param to `submit_apptainer_job()`: appends `#SBATCH --dependency=afterok:<ids>` to the Slurm script for automatic job chaining.
- **`pages/1_Job_Manager.py`** — extracted `CONTAINER_CONFIGS` into `_build_container_configs()` at module level so both Tab 1 and Tab 3 share the same module registry. Added SuperSynth as a commented template for future use.
- **`pages/1_Job_Manager.py`** — added `resolve_submission_order()`: topological sort (Kahn's algorithm) ensuring upstream modules are submitted before downstream dependents.
- **`pages/1_Job_Manager.py`** — added `refresh_manifest_statuses()`: polls Slurm (`sacct`/`squeue`) for all in-flight job IDs and updates manifest statuses in place.
- **`pages/1_Job_Manager.py`** — replaced Tab 3 ("coming soon" stub) with a working Pipeline Workflow Builder: project selection, module checkboxes with dependency labels, subject/session filters, dry-run mode, Slurm `afterok` chaining on submit, persistent manifest write. Added Pipeline Status dashboard below: colour-coded table (queued/running/complete/failed) with Slurm refresh and per-subject detail expander.

### Bug fixes
- **`pages/1_Job_Manager.py`** — fixed `bids_root` input type in workflow submission: previously fell through to the `acquisition`/`derivatives` input-file search before building the command, leaving `input_file = None`. Now handled as an early branch that builds the command directly and skips file search.
- **`pages/4_Data_Explorer.py`** — deleted: old duplicate of `4_Projects.py`; was creating a second sidebar entry in Streamlit.
- **`pages/2_Visualize_Data.py`** — removed four debug `st.write()` statements left in `get_projects()` that were printing raw SSH output to users.
