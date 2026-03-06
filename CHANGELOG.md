# Changelog

All significant changes to Cortex are recorded here.
Format: `## YYYY-MM-DD` heading, then one entry per change with file(s) and reason.

---

## 2026-03-06

### Bug fixes: path hardcoding + dead code removal
- **`pages/3_Download_Data.py`** — replaced hardcoded `/home/{username}/projects/` (lines 59 & 83) with `home_dir` resolved from `$HOME` via `client._run("echo $HOME")` cached in session state; matches the fix applied to `2_Visualize_Data.py`. Renamed local `home_dir` variable to `local_home` to avoid shadowing the HPC path.
- **`utils/session.py`** — deleted; `check_connection()` and `require_connection()` were defined but never imported by any page. Each page has its own inline connection guard that handles the UI messaging correctly.

### Phase 5: Shared BIDS helpers + Visualize Data cleanup
- **`utils/bids.py`** — new module: `get_projects`, `count_subjects_and_sessions`, `get_subjects`, `get_sessions`, `get_acquisitions`, `get_files_in_directory`; extracted from `2_Visualize_Data.py`; no Streamlit dependencies so callers handle UI errors. All helpers use `$HOME`-expanded paths.
- **`pages/2_Visualize_Data.py`** — removed ~105 lines of duplicated BIDS helper definitions; imports from `utils.bids` instead. Replaced per-page project selector with `render_project_selector()` + `st.session_state["selected_project"]`. Fixed `~/projects/` path bug (SSH commands do not expand `~`) — now uses `$HOME`-resolved `home_dir` from session state.

### Phase 3: Auto-trigger script
- **`scripts/cortex_trigger.py`** — new standalone script: scans all projects under `~/projects/` that have a `.cortex/pipeline_config.json`, resolves new/unprocessed subjects×sessions, submits Slurm jobs via `sbatch` with `afterok` chaining, and updates `.cortex/pipeline_status.json`. Flags: `--dry-run`, `--retry-failed`, `--verbose`, `--projects-dir`. Imports `utils.modules` directly, so the module registry is shared with the Streamlit app. Pre-pass Slurm status refresh (`sacct`) prevents resubmitting in-flight jobs.
- **`scripts/cortex_trigger.sh`** — thin bash wrapper that activates the venv (if present), calls `cortex_trigger.py`, and appends a timestamped run header to `~/.cortex/trigger.log`. Drop-in cron target.

### Phase 4: Indexed file browser
- **`utils/bids_index.py`** — new module: `build_index(client, home_dir)` runs a single `find` command over `~/projects/` and parses paths into flat records `{project, type, subject, session, modality, filename, size, mtime, path}`. Handles both raw BIDS and `derivatives/<module>/` paths. `load_index` / `save_index` persist via `utils/hpc_io` SFTP helpers.
- **`pages/4_Projects.py`** — full rewrite: replaced ~500-line click-through browser (live SSH per click) with a pandas `st.dataframe` browser backed by the index. Single "Rebuild Index" button triggers the SSH walk; all filtering (project, type, subject, session, modality, filename search) runs in-memory on the cached DataFrame. Selecting a row shows a file detail panel with the full HPC path. Global project selector pre-filters the project column.

### Phase 2: Unified Workflows page
- **`utils/hpc_io.py`** — new module: `read_json_from_hpc(client, path)` and `write_json_to_hpc(client, path, data)` using SFTP; shared by the Workflows page and future auto-trigger script.
- **`utils/modules.py`** — new module: `build_container_configs(hpc_user)` (moved from `1_Job_Manager.py`) and `resolve_submission_order(selected_modules, container_configs)` (refactored to take config as parameter); centralises the module registry for reuse by the auto-trigger script.
- **`pages/1_Workflows.py`** — new unified page replacing `1_Job_Manager.py`; three tabs: Pipeline Configuration (module selection + resource overrides, saved to `.cortex/pipeline_config.json`), Manual Trigger (reads saved config, submits with Slurm `afterok` chaining), Pipeline Status (manifest table + Slurm refresh).
- **`pages/1_Job_Manager.py`** — deleted; replaced entirely by `pages/1_Workflows.py`. All Slurm submission, chaining, and status logic preserved.
- **`utils/sidebar.py`** — `clear_project_state()` extended to also clear `_home_dir` and `_config_project` cached session keys on disconnect.
- **`Home.py`** — nav card and feature description updated to reference Workflows page; `st.switch_page` target updated.

### Global project selector
- **`utils/sidebar.py`** — new module: `render_project_selector(client)` renders a project dropdown in the sidebar, caches the project list in `st.session_state["_project_list"]` to avoid repeated SSH calls, and writes the selection to `st.session_state["selected_project"]` shared across all pages. `clear_project_state()` clears both keys on disconnect.
- **`Home.py`** — initialises `selected_project = None` in session state; calls `render_project_selector()` in the sidebar when connected; calls `clear_project_state()` on disconnect to reset project context.
- **`pages/1_Job_Manager.py`** — imports and calls `render_project_selector()` so the global selector is visible on the Job Manager page.

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
