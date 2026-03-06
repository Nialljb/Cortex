# Cortex

## Purpose

Cortex is a Streamlit web portal for running neuroimaging analysis pipelines on an HPC Slurm cluster (KCL NaN cluster). Users sign in via SSH, select a BIDS-structured project, then compose and submit a pipeline of analysis modules (Apptainer/Singularity containers) as Slurm batch jobs.

The primary development goal is a **module selection workflow**: for a given project, the user picks which modules (e.g. MRR, SuperSynth, GAMBAS, BabySeg) to run, in what order, and with what input/output wiring. Some modules depend on prior modules having completed — e.g. SuperSynth can be configured to consume MRR output, Circumference requires GAMBAS output. The system must represent and enforce these dependency relationships.

## Documentation

- **[docs/external_setup.md](docs/external_setup.md)** — Guide for building Apptainer containers, registering new modules, deploying `.sif` files to the HPC, and scheduling the auto-trigger (cron / GitHub Actions / Slurm self-scheduling).

## Project Overview

### Current Pages
- **Home.py** — SSH connection / authentication (password or key), session management, navigation hub; global project selector in sidebar
- **pages/1_Workflows.py** — Pipeline Configuration (saved per-project module selection + resource overrides); Manual Trigger (submit configured pipeline); Pipeline Status dashboard
- **pages/2_Visualize_Data.py** — Data visualisation
- **pages/3_Download_Data.py** — Browse and download files from HPC
- **pages/4_Projects.py** — Indexed BIDS file browser; loads flat JSON index from HPC, filters via pandas; "Rebuild Index" triggers SSH walk

### Module System (existing, in Job_Manager)
Modules are defined in `CONTAINER_CONFIGS` dict. Key fields per module:
- `image_path` — Apptainer `.sif` image path on HPC
- `command_template` — command run inside container (with `{input_file}`, `{output_dir}`, `{subject}`, `{session}` placeholders)
- `input_type` — `"acquisition"` (raw BIDS), `"derivatives"` (prior pipeline output), or `"bids_root"`
- `input_pattern` — regex to match input files
- `input_subdir` — BIDS subdirectory (e.g. `"anat"`)
- `requires_derivative` — name of the upstream module whose output is used as input (or `None`)
- `output_name` — used to construct `derivatives/<output_name>/` output path

### Target Architecture: Unified Workflows + Global Project Context

**Refactoring goals (in priority order):**

1. **Merge Apptainer + Workflows + Scripts → single "Workflows" page**
   - Remove separate Apptainer, Workflows, and Scripts tabs from Job Manager
   - Replace with a single unified **Workflows** section with two sub-sections:
     - **Pipeline Configuration** — define pipelines per project (modules, parameters, dependencies); this config is saved and used by the auto-trigger
     - **Manual Trigger** — kept for ad-hoc use; submits the configured pipeline immediately for selected subjects/sessions
   - **Auto-trigger** runs outside Streamlit (cron job, GitHub Action, or daily bash script) — reads project pipeline config and submits new subjects not yet in `pipeline_status.json`
   - Pipeline status view must remain accessible and prominent

2. **Global project selector**
   - Add a project selector in the sidebar (or app top) that persists across all pages via `st.session_state`
   - All pages read from shared project context — no per-page independent selectors

3. **Replace the Projects data browser (`4_Projects.py`) with an indexed file browser**
   - Current browser makes live SSH calls per directory interaction — too slow and laggy for a usable UX
   - Replace with a **database-indexed approach**: a background indexer (cron or on-demand) walks the BIDS project tree over SSH and writes a lightweight index (e.g. SQLite or JSON) to the HPC or locally
   - The Streamlit file browser then queries the index rather than making live SSH calls, making navigation near-instant
   - Index schema: `{project, subject, session, modality, filename, size, mtime}` — flat table, filterable/searchable via `st.dataframe`
   - Index refresh can be triggered on demand from the UI (button → SSH walk → rewrite index) or by the same daily cron that runs auto-trigger

**What must not change:**
- Home.py login/auth flow — leave intact
- Pipeline status functionality — preserve and keep prominent
- All backend logic: job submission, status polling, SSH handling (`HPCSSHClient`)
- Slurm job chaining via `--dependency=afterok:<job_id>`

Dependency information already exists implicitly in `requires_derivative` — the workflow builder should make this explicit and user-configurable.

## Tech Stack
- Language: Python 3.11
- Modelling: scikit-learn (polynomial OLS fallback), PCNtoolkit BLR (preferred, not yet installed)
- Data: pandas, numpy, scipy
- Reports: reportlab, matplotlib
- Portal: Streamlit
- Tests: run with `pytest` (add coverage when test suite is established)

## Architecture

### Pipeline Flow
```
User (browser)
  → Home.py (SSH auth via Paramiko → HPCSSHClient)
  → [Global sidebar project selector] → st.session_state["selected_project"]
  → pages/1_Workflows.py
      Tab 1 (Pipeline Configuration): module selection + resource overrides → saved to .cortex/pipeline_config.json
      Tab 2 (Manual Trigger): load saved config → subject/session filters → submit with Slurm afterok chaining
      Tab 3 (Pipeline Status): manifest table + Slurm refresh
  → pages/2_Visualize_Data.py — data visualisation
  → pages/3_Download_Data.py — file download
  → pages/4_Projects.py — indexed BIDS file browser (index at $HOME/.cortex/bids_index.json)

Auto-trigger (Phase 3 — external):
  scripts/cortex_trigger.sh → reads .cortex/pipeline_config.json + pipeline_status.json → sbatch new subjects
```

### Key Design Decisions
- All HPC filesystem access goes through `HPCSSHClient` (`hpc_client_ssh.py`) — no direct local filesystem assumptions
- BIDS convention: projects live at `~/projects/<project>/sub-<id>/ses-<id>/<modality>/`; derivatives at `<project>/derivatives/<module_name>/`
- Module dependency expressed via `requires_derivative` field — upstream output dir becomes downstream input dir
- Job chaining via Slurm `--dependency=afterok:<job_id>` (to be implemented in Workflows tab)
- Session state (`st.session_state`) carries connection, project selection, and job history across pages

### Directory Structure
```
Cortex/
├── Home.py                  # Auth, connection, navigation hub
├── hpc_client_ssh.py        # SSH/SFTP wrapper (HPCSSHClient)
├── pages/
│   ├── 1_Job_Manager.py     # Batch job submission + workflow builder
│   ├── 2_Visualize_Data.py  # Visualisation
│   ├── 3_Download_Data.py   # File download
│   └── 4_Projects.py        # BIDS project browser
├── utils/
│   ├── bids.py              # Shared BIDS filesystem helpers
│   ├── bids_index.py        # BIDS index builder for file browser
│   ├── hpc_io.py            # SFTP JSON read/write helpers
│   ├── modules.py           # Module registry + dependency resolution
│   └── sidebar.py           # Global project selector
├── config.yaml.template     # Config template
└── requirements.txt
```




## Commands
```bash
streamlit run Home.py          # Start the app (typically http://localhost:8501)
pytest                         # Run tests
```


## Conventions
- All paths: `Path(__file__).resolve().parent.parent` — no hardcoded absolute paths
- Naming: `snake_case` functions and variables, `PascalCase` classes
- No `print()` for logging — use Python `logging` module
- No raw SQL — all data manipulation via pandas
- Volume units: always mL internally; convert at ingest boundary only
- Commits: one logical change per commit (Conventional Commits style encouraged)

## Behaviour Rules
- Only edit files relevant to the stated task (scope guard)
- Ask before refactoring any file over 200 lines
- Never suppress linting or type errors without explanation
- Never hardcode paths, credentials, or magic numbers without a named constant + comment
- Do not add dependencies outside the approved list without discussion
- Write tests before adding new model features (not required for minor bug fixes)
- Declare the "why" in comments for any non-obvious statistical or clinical decision

## Do Not Touch
- `hpc_client_ssh.py` — stable SSH client; changes require careful testing against live cluster


## To Do

### Bugs
- [ ] **`hpc_client_ssh.py`**: replace `print()` in `_run()` and `read_pipeline_manifest()` with `logging.debug/warning` — violates no-print convention and creates console noise
- [x] **`3_Download_Data.py`**: hardcoded `/home/{username}/` prefix on lines 59 & 83 — fixed; now uses `$HOME`-resolved `home_dir` cached in session state
- [x] **`2_Visualize_Data.py`**: `~/projects/...` path bug fixed — now uses `$HOME`-resolved `home_dir` from session state
- [ ] **`hpc_client_ssh.py`**: cache `home_dir` at connect time (`self.home_dir = self._run("echo $HOME").strip()`) so all pages share one SSH call instead of repeating it

### Code Quality
- [x] **`utils/session.py`**: deleted — `check_connection()` / `require_connection()` were unused; each page has its own inline connection guard
- [ ] **`submit_batch_apptainer_jobs()`**: stale local imports (`import os`, `import re`, `from pathlib import Path`, `from datetime import datetime`) inside function body — now redundant with module-level imports
- [x] **Duplicated BIDS helpers**: moved to `utils/bids.py`; `2_Visualize_Data.py` imports from there; `4_Projects.py` was fully rewritten and no longer uses these helpers
- [x] **Tab 2 (Scripts) in Job Manager**: removed with `1_Job_Manager.py` (dead code, scripts didn't exist)
- [x] **`import pandas as pd`** inside Tab 3 status dashboard: `1_Job_Manager.py` deleted; `1_Workflows.py` imports pandas at the tab level inside the `with tab_status:` block (acceptable — pandas is only needed there)

### Features to Add
- [ ] **Pipeline status in `4_Projects.py`**: read `.cortex/pipeline_status.json` and show per-session module status icons in the session list table
- [ ] **Job cancellation**: `scancel <job_id>` button next to queued/running rows in the workflow status dashboard
- [ ] **Retry failed jobs**: button in status dashboard to resubmit only entries with `status == "failed"`
- [ ] **Image path validation**: before submitting, verify `.sif` exists on HPC (`test -f <path>`) and surface a clear error
- [ ] **Derivatives browser in `3_Download_Data.py`**: allow browsing `derivatives/<module>/` paths, not just `<project>/<subdir>/output/`
- [ ] **Batch download**: implement the stub in `3_Download_Data.py`
- [ ] **SuperSynth module**: uncomment template in `CONTAINER_CONFIGS` once `image_path` and `command_template` are confirmed

### Refactoring Tasks
- [x] **Global project selector**: `utils/sidebar.py` created; `render_project_selector()` called from `Home.py` and `1_Job_Manager.py`; `clear_project_state()` called on disconnect — per-page selectors still present in Job Manager tabs, to be removed when page is unified
- [x] **Unify Workflows page**: `pages/1_Workflows.py` created; `pages/1_Job_Manager.py` deleted; three tabs: Pipeline Configuration, Manual Trigger, Pipeline Status; Scripts tab removed (dead code)
- [x] **Pipeline config persistence**: pipeline config saved to `.cortex/pipeline_config.json` via `utils/hpc_io.write_json_to_hpc()`; auto-loaded on project switch; read by Manual Trigger tab
- [x] **Auto-trigger script**: `scripts/cortex_trigger.py` (Python, ~300 lines) + `scripts/cortex_trigger.sh` (cron wrapper); reads `.cortex/pipeline_config.json`, refreshes Slurm statuses via `sacct`, submits new/unprocessed subjects with `sbatch` + `afterok` chaining; flags: `--dry-run`, `--retry-failed`, `--verbose`
- [x] **Indexed file browser**: `utils/bids_index.py` created; single `find` walk → flat JSON index at `$HOME/.cortex/bids_index.json`; `4_Projects.py` rewritten as pandas `st.dataframe` browser with project/type/subject/session/modality/filename filters; "Rebuild Index" button triggers SSH walk on demand
- [x] **Extract shared BIDS helpers**: `utils/bids.py` created; `2_Visualize_Data.py` updated to import from there; `~/projects/` path bug fixed

### Features to Remove / Already Fixed
- [x] `pages/4_Data_Explorer.py` — old duplicate page causing second sidebar entry (deleted)
- [x] Debug `st.write()` statements in `2_Visualize_Data.py:get_projects()` (removed)
- [x] `bids_root` workflow branch bug — `input_file` was `None` when command was built (fixed)
- [ ] `example_useage.py`, `database_setup_example.py`, `secure_auth_example.py` at project root — scratch files, not part of the app; move to `examples/` or delete


## Changelog
- Every code change must be recorded in `CHANGELOG.md` at the project root.
- Group entries under the current date heading (`## YYYY-MM-DD`).
- Each entry: what changed, which file(s), and why (the problem it solved).


