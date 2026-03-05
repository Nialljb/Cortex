# Cortex

## Purpose

Cortex is a Streamlit web portal for running neuroimaging analysis pipelines on an HPC Slurm cluster (KCL NaN cluster). Users sign in via SSH, select a BIDS-structured project, then compose and submit a pipeline of analysis modules (Apptainer/Singularity containers) as Slurm batch jobs.

The primary development goal is a **module selection workflow**: for a given project, the user picks which modules (e.g. MRR, SuperSynth, GAMBAS, BabySeg) to run, in what order, and with what input/output wiring. Some modules depend on prior modules having completed — e.g. SuperSynth can be configured to consume MRR output, Circumference requires GAMBAS output. The system must represent and enforce these dependency relationships.

## Project Overview

### Current Pages
- **Home.py** — SSH connection / authentication (password or key), session management, navigation hub
- **pages/1_Job_Manager.py** — Submit Apptainer container jobs batch per subject/session, with module configs (MRR, GAMBAS, BabySeg, Circumference, fMRIPrep, etc.); Scripts tab; Workflows tab (stub)
- **pages/2_Visualize_Data.py** — Data visualisation
- **pages/3_Download_Data.py** — Browse and download files from HPC
- **pages/4_Projects.py** — Hierarchical BIDS project browser (project → subject → session → acquisition → file)

### Module System (existing, in Job_Manager)
Modules are defined in `CONTAINER_CONFIGS` dict. Key fields per module:
- `image_path` — Apptainer `.sif` image path on HPC
- `command_template` — command run inside container (with `{input_file}`, `{output_dir}`, `{subject}`, `{session}` placeholders)
- `input_type` — `"acquisition"` (raw BIDS), `"derivatives"` (prior pipeline output), or `"bids_root"`
- `input_pattern` — regex to match input files
- `input_subdir` — BIDS subdirectory (e.g. `"anat"`)
- `requires_derivative` — name of the upstream module whose output is used as input (or `None`)
- `output_name` — used to construct `derivatives/<output_name>/` output path

### Target Feature: Project-Level Workflow Builder (Tab 3 — Workflows)
Allow a signed-in user to:
1. Select a project from `~/projects/`
2. Browse and select one or more modules to form a pipeline
3. Specify inter-module dependencies (e.g. SuperSynth input = MRR output)
4. Validate the dependency graph (detect cycles, missing prerequisites)
5. Submit the full workflow as Slurm jobs with `--dependency=afterok:<job_id>` chaining
6. Monitor pipeline status per subject/session

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
  → 4_Projects.py (browse BIDS hierarchy via SSH)
  → 1_Job_Manager.py
      Tab 1 (Apptainer): select module → scan subjects/sessions → submit_apptainer_job() per subject
      Tab 2 (Scripts): run pre-configured shell scripts
      Tab 3 (Workflows): [TARGET] compose multi-module pipeline with dependency graph → submit with Slurm afterok chaining
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
│   └── session.py           # Session state helpers
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
- [ ] **`3_Download_Data.py`**: hardcoded `/home/{username}/` prefix on lines 59 & 83 — breaks on clusters where home is not `/home/`. Use `$HOME` or `client.home_dir`
- [ ] **`2_Visualize_Data.py`**: `~/projects/...` path on line 210 passed to SSH commands — use `$HOME` for consistency
- [ ] **`hpc_client_ssh.py`**: cache `home_dir` at connect time (`self.home_dir = self._run("echo $HOME").strip()`) so all pages share one SSH call instead of repeating it

### Code Quality
- [ ] **`utils/session.py`**: `check_connection()` / `require_connection()` exist but are unused — either adopt them in all pages or delete the file
- [ ] **`submit_batch_apptainer_jobs()`**: stale local imports (`import os`, `import re`, `from pathlib import Path`, `from datetime import datetime`) inside function body — now redundant with module-level imports
- [ ] **Duplicated BIDS helpers**: `get_projects()`, `get_subjects()`, `get_sessions()`, `get_acquisitions()`, `get_files_in_directory()` duplicated between `2_Visualize_Data.py` and `4_Projects.py` — move to `utils/bids.py`
- [ ] **Tab 2 (Scripts) in Job Manager**: hardcoded script paths (`~/scripts/run_segmentation.sh` etc.) that don't exist — either populate with real scripts or remove the tab
- [ ] **`import pandas as pd`** inside Tab 3 status dashboard — move to top of file with other imports

### Features to Add
- [ ] **Pipeline status in `4_Projects.py`**: read `.cortex/pipeline_status.json` and show per-session module status icons in the session list table
- [ ] **Job cancellation**: `scancel <job_id>` button next to queued/running rows in the workflow status dashboard
- [ ] **Retry failed jobs**: button in status dashboard to resubmit only entries with `status == "failed"`
- [ ] **Image path validation**: before submitting, verify `.sif` exists on HPC (`test -f <path>`) and surface a clear error
- [ ] **Derivatives browser in `3_Download_Data.py`**: allow browsing `derivatives/<module>/` paths, not just `<project>/<subdir>/output/`
- [ ] **Batch download**: implement the stub in `3_Download_Data.py`
- [ ] **SuperSynth module**: uncomment template in `CONTAINER_CONFIGS` once `image_path` and `command_template` are confirmed

### Features to Remove / Already Fixed
- [x] `pages/4_Data_Explorer.py` — old duplicate page causing second sidebar entry (deleted)
- [x] Debug `st.write()` statements in `2_Visualize_Data.py:get_projects()` (removed)
- [x] `bids_root` workflow branch bug — `input_file` was `None` when command was built (fixed)
- [ ] `example_useage.py`, `database_setup_example.py`, `secure_auth_example.py` at project root — scratch files, not part of the app; move to `examples/` or delete


## Changelog
- Every code change must be recorded in `CHANGELOG.md` at the project root.
- Group entries under the current date heading (`## YYYY-MM-DD`).
- Each entry: what changed, which file(s), and why (the problem it solved).


