# Cortex: External Setup Guide
## Apptainer Containers + HPC Deployment + Auto-Trigger Scheduling

**Context for AI assistants:** This app (Cortex) is a Streamlit portal that submits Apptainer/Singularity jobs to a Slurm HPC cluster. The app lives at `~/repos/Cortex/` on the HPC. Modules are defined in `utils/modules.py` with fields: `image_path` (`.sif` path on HPC), `command_template` (run inside container with `{input_file}`, `{output_dir}`, `{subject}`, `{session}`, `{bids_dir}` placeholders), `input_type` (`acquisition` | `derivatives` | `bids_root`), `requires_derivative` (upstream module's `output_name` or None). Jobs are submitted via `sbatch` with `--dependency=afterok` chaining. The auto-trigger script is `scripts/cortex_trigger.py`.

---

## Part 1 — Building Apptainer Containers

### 1.1 Definition file structure

Each module needs a `.def` file. Minimal template:

```
Bootstrap: docker
From: ubuntu:22.04

%labels
    Author  your-name
    Version 1.0.0
    Module  MyModule

%post
    apt-get update -qq
    apt-get install -y python3 python3-pip
    pip3 install numpy nibabel

    # Install your tool
    pip3 install my-neuroimaging-tool==1.2.3

%environment
    export LC_ALL=C
    export PATH=/usr/local/bin:$PATH

%runscript
    exec python3 /app/run_mymodule.py "$@"

%files
    # Copy local scripts into the image
    run_mymodule.py /app/run_mymodule.py
```

**For GPU modules** (e.g. BabySeg), start from a CUDA base:

```
Bootstrap: docker
From: nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04
```

**For FSL/FreeSurfer/fMRIPrep**, pull from existing registries rather than building from scratch — see section 1.3.

### 1.2 Building locally (requires root or fakeroot)

```bash
# On your local machine (needs Apptainer >= 1.1)
apptainer build mymodule.sif mymodule.def

# If you don't have root, use fakeroot (needs admin to set up once)
apptainer build --fakeroot mymodule.sif mymodule.def

# Build from a Docker image directly (no .def needed)
apptainer build mymodule.sif docker://ghcr.io/myorg/mymodule:latest
```

### 1.3 Pulling pre-built images (fMRIPrep, MRtrix, etc.)

```bash
# fMRIPrep (official, use specific version tag)
apptainer pull fmriprep.sif docker://nipreps/fmriprep:23.2.3

# MRtrix3
apptainer pull mrtrix3.sif docker://mrtrix3/mrtrix3:3.0.4

# FreeSurfer
apptainer pull freesurfer.sif docker://freesurfer/freesurfer:7.4.1
```

### 1.4 Transferring to HPC

```bash
# rsync is preferred — resumes interrupted transfers
rsync -avP mymodule.sif hpc-login.example.ac.uk:~/images/mymodule.sif

# Or scp
scp mymodule.sif username@hpc-login.example.ac.uk:~/images/mymodule.sif
```

**Convention used by Cortex:** images live at `~/images/<module_name>.sif`. The path is set in `utils/modules.py` as `f"/home/{hpc_user}/images/mymodule.sif"`.

### 1.5 Testing the container on the HPC

```bash
# Interactive test (not on login node — use an interactive Slurm session)
srun --pty --cpus-per-task=4 --mem=8G --time=01:00:00 bash

# Then inside the session:
apptainer exec ~/images/mymodule.sif python3 /app/run_mymodule.py --help

# With GPU
srun --pty --cpus-per-task=4 --mem=16G --gres=gpu:1 --time=01:00:00 bash
apptainer exec --nv ~/images/mymodule.sif python3 /app/run_mymodule.py --help
```

Note: if your module needs GPU support, add `--nv` to the `apptainer exec` call in `command_template`.

### 1.6 Registering a new module in Cortex

Open `utils/modules.py` and add a block inside `build_container_configs()`:

```python
"MyModule": {
    "image_path": f"/home/{hpc_user}/images/mymodule.sif",
    "command_template": (
        "python /app/run_mymodule.py "
        "--input {input_file} --output {output_dir} "
        "--subject {subject} --session {session}"
    ),
    "input_type": "acquisition",          # "acquisition" | "derivatives" | "bids_root"
    "input_pattern": r".*_T2w\.nii\.gz$", # regex matched against filenames
    "input_subdir": "anat",               # BIDS subdirectory, or None
    "requires_derivative": None,          # set to upstream module's output_name if dependent
    "output_name": "mymodule",            # written to derivatives/mymodule/
    "default_cpus": 4,
    "default_mem": "16G",
    "default_gpus": 0,
    "default_time": "02:00:00",
    "description": "One-line description shown in the Cortex UI",
},
```

**Dependency example** — a module that consumes output from `MyModule`:

```python
"MyModuleStep2": {
    ...
    "input_type": "derivatives",
    "requires_derivative": "mymodule",   # must match output_name of upstream
    "input_pattern": r".*_mymodule\.nii\.gz$",
    ...
},
```

The topological sort in `resolve_submission_order()` handles ordering automatically. The Streamlit UI and the trigger script both pick up the new module without any other changes.

---

## Part 2 — Auto-Trigger Scheduling

The trigger script (`scripts/cortex_trigger.py`) runs directly on the HPC — it uses local filesystem paths, not SSH. It reads `.cortex/pipeline_config.json` per project, checks `.cortex/pipeline_status.json` for what's already processed, then calls `sbatch`.

### Option A — Cron (simplest, recommended)

SSH into the HPC login node, then:

```bash
crontab -e
```

Add:

```cron
# Cortex auto-trigger — daily at 06:00
0 6 * * * bash $HOME/repos/Cortex/scripts/cortex_trigger.sh >> $HOME/.cortex/trigger.log 2>&1
```

`cortex_trigger.sh` handles timestamped log headers. The script activates a venv if present at `~/repos/Cortex/.venv`.

**Useful cron expressions:**

| Schedule | Expression |
|---|---|
| Daily at 06:00 | `0 6 * * *` |
| Every 6 hours | `0 */6 * * *` |
| Weekdays at 07:00 | `0 7 * * 1-5` |
| Every 30 minutes | `*/30 * * * *` |

Check cron is working:

```bash
tail -f ~/.cortex/trigger.log
```

### Option B — GitHub Actions (requires SSH secret)

This approach triggers the HPC script from a GitHub Actions workflow. The HPC never needs to reach out — GitHub SSHs in.

**Required GitHub secrets** (set in repo Settings → Secrets → Actions):

| Secret | Value |
|---|---|
| `HPC_HOST` | `login.hpc.example.ac.uk` |
| `HPC_USER` | your HPC username |
| `HPC_SSH_KEY` | contents of your `~/.ssh/id_rsa` private key |

**Generate a dedicated deploy key** (do not reuse your personal key):

```bash
ssh-keygen -t ed25519 -C "cortex-github-actions" -f ~/.ssh/cortex_deploy
# Add the public key to HPC authorized_keys:
cat ~/.ssh/cortex_deploy.pub >> ~/.ssh/authorized_keys
# Paste the private key content into the HPC_SSH_KEY GitHub secret
```

**.github/workflows/cortex_trigger.yml:**

```yaml
name: Cortex Auto-Trigger

on:
  schedule:
    - cron: "0 6 * * *"   # daily at 06:00 UTC
  workflow_dispatch:        # allow manual runs from GitHub UI

jobs:
  trigger:
    runs-on: ubuntu-latest
    steps:
      - name: SSH and run Cortex trigger
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.HPC_HOST }}
          username: ${{ secrets.HPC_USER }}
          key: ${{ secrets.HPC_SSH_KEY }}
          script: |
            bash $HOME/repos/Cortex/scripts/cortex_trigger.sh

      - name: Dry run check (optional, runs before real trigger)
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.HPC_HOST }}
          username: ${{ secrets.HPC_USER }}
          key: ${{ secrets.HPC_SSH_KEY }}
          script: |
            python3 $HOME/repos/Cortex/scripts/cortex_trigger.py --dry-run --verbose
```

**Tip:** the `workflow_dispatch` trigger lets you manually fire the workflow from the GitHub Actions tab without waiting for the schedule.

### Option C — Slurm itself as the scheduler

Submit a recurring "monitor" job that resubmits itself:

```bash
#!/bin/bash
#SBATCH --job-name=cortex_monitor
#SBATCH --time=00:10:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --output=%h/.cortex/monitor_%j.log

python3 $HOME/repos/Cortex/scripts/cortex_trigger.py

# Resubmit for tomorrow
sbatch --begin=now+1day $0
```

Submit once: `sbatch cortex_monitor.sh`. This avoids needing cron access (useful on shared clusters where cron is restricted).

---

## Part 3 — HPC Environment Setup

### Python dependencies for the trigger script

The trigger script only uses the standard library + `utils/modules.py`. No extra packages needed beyond what Cortex requires:

```bash
cd ~/repos/Cortex
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`cortex_trigger.sh` activates `.venv` automatically if it exists.

### Directory layout expected on HPC

```
~/
├── images/
│   ├── babyseg.sif
│   ├── gambas.sif
│   ├── mrr.sif
│   └── mymodule.sif
├── projects/
│   └── <project>/
│       ├── sub-001/ses-01/anat/*.nii.gz    <- raw BIDS input
│       ├── derivatives/
│       │   └── mymodule/sub-001/ses-01/    <- auto-created on first run
│       ├── logs/mymodule/                  <- Slurm .out files
│       ├── work/mymodule/                  <- Slurm working dir
│       └── .cortex/
│           ├── pipeline_config.json        <- written by Streamlit UI
│           └── pipeline_status.json        <- written by trigger + Streamlit
└── repos/
    └── Cortex/                             <- this repo
```

### Cluster-specific notes (KCL NaN cluster)

- Module loads (if needed before apptainer): `module load apptainer` or `module load singularity`
- Partition flags to add in Slurm scripts if required: `#SBATCH --partition=cpu` / `--partition=gpu`
- If home quota is tight, move `.sif` files to `/scratch` and update `image_path` in `utils/modules.py` accordingly
- Some clusters restrict outbound internet from compute nodes — build images locally and `rsync` them rather than pulling on the cluster

---

## Part 4 — Automated Container Builds (optional)

If you maintain your own container source code, automate builds on push and deploy to the HPC:

**.github/workflows/build_container.yml:**

```yaml
name: Build and push Apptainer image

on:
  push:
    paths:
      - "containers/mymodule/**"
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Apptainer
        run: |
          sudo apt-get install -y apptainer

      - name: Build image
        run: |
          apptainer build mymodule.sif containers/mymodule/mymodule.def

      - name: Push to GHCR
        run: |
          echo "${{ secrets.GITHUB_TOKEN }}" | apptainer registry login \
            --username ${{ github.actor }} --password-stdin oras://ghcr.io
          apptainer push mymodule.sif oras://ghcr.io/${{ github.repository }}/mymodule:latest

      - name: Deploy to HPC
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.HPC_HOST }}
          username: ${{ secrets.HPC_USER }}
          key: ${{ secrets.HPC_SSH_KEY }}
          script: |
            apptainer pull --force ~/images/mymodule.sif \
              oras://ghcr.io/${{ github.repository }}/mymodule:latest
```

This gives you: push code → image auto-builds → pushes to GHCR → HPC pulls updated `.sif` automatically.

---

## Quick-reference checklist for a new module

- [ ] Write `.def` file, build `.sif` locally
- [ ] `rsync` `.sif` to `~/images/` on HPC
- [ ] `apptainer exec` test in interactive Slurm session
- [ ] Add entry to `utils/modules.py` `build_container_configs()`
- [ ] Set `requires_derivative` if it depends on another module's output
- [ ] Verify `input_pattern` regex matches your actual output filenames
- [ ] In Cortex UI: select the module in Pipeline Configuration and run a dry-run trigger (`--dry-run`) to confirm command resolution before real submission
