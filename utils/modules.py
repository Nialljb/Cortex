"""
Module registry and dependency resolution for Cortex pipelines.

CONTAINER_CONFIGS is the authoritative list of available analysis modules.
Add new modules here; the Workflows page and auto-trigger script pick them up automatically.

Fields per module:
  image_path         - Apptainer .sif path on the HPC
  command_template   - command run inside the container; placeholders:
                       {input_file}, {output_dir}, {subject}, {session},
                       {bids_dir} (bids_root input_type only)
  input_type         - "acquisition" | "derivatives" | "bids_root"
  input_pattern      - regex matched against filenames to find the input file
  input_subdir       - BIDS subdirectory to search (e.g. "anat"), or None
  requires_derivative- output_name of the upstream module this depends on, or None
  output_name        - written to derivatives/<output_name>/
  default_*          - Slurm resource defaults for this module
"""


def build_container_configs(hpc_user: str) -> dict:
    """Return the module registry with the authenticated HPC username in image paths."""
    return {
        "DebugTest": {
            "image_path": f"/home/{hpc_user}/cortex/modules/debug_test.sif",
            "command_template": (
                "python /app/test_script.py "
                "--input {input_file} --output {output_dir} "
                "--subject {subject} --session {session}"
            ),
            "input_type": "acquisition",
            "input_pattern": r".*\.nii\.gz$",
            "input_subdir": "anat",
            "requires_derivative": None,
            "output_name": "debug_test",
            "default_cpus": 1,
            "default_mem": "2G",
            "default_gpus": 0,
            "default_time": "00:10:00",
            "description": "Debug test container for workflow validation",
        },
        "BabySeg": {
            "image_path": f"/home/{hpc_user}/cortex/modules/babyseg.sif",
            "command_template": (
                "python /app/run_babyseg.py --input {input_file} --output {output_dir}"
            ),
            "input_type": "acquisition",
            "input_pattern": r".*_T2w\.nii\.gz$",
            "input_subdir": "anat",
            "requires_derivative": None,
            "output_name": "babyseg",
            "default_cpus": 8,
            "default_mem": "32G",
            "default_gpus": 0,
            "default_time": "04:00:00",
            "description": "Infant brain segmentation",
        },
        "GAMBAS": {
            "image_path": f"/home/{hpc_user}/cortex/modules/gambas.sif",
            "command_template": (
                "python /app/run_gambas.py --input {input_file} --output {output_dir}"
            ),
            "input_type": "acquisition",
            "input_pattern": r".*_T2w\.nii\.gz$",
            "input_subdir": "anat",
            "requires_derivative": None,
            "output_name": "gambas",
            "default_cpus": 4,
            "default_mem": "16G",
            "default_gpus": 0,
            "default_time": "02:00:00",
            "description": "Brain tissue segmentation",
        },
        "Circumference": {
            "image_path": f"/home/{hpc_user}/cortex/modules/circumference.sif",
            "command_template": (
                "python /app/run_circumference.py --input {input_file} --output {output_dir}"
            ),
            "input_type": "derivatives",
            "input_pattern": r"(.*_mrr\.nii\.gz|.*_ResCNN\.nii\.gz|.*_T2w_gambas\.nii\.gz)$",
            "input_subdir": "anat",
            "requires_derivative": "gambas",
            "output_name": "circumference",
            "default_cpus": 4,
            "default_mem": "16G",
            "default_gpus": 0,
            "default_time": "01:00:00",
            "description": "Head circumference measurement (requires GAMBAS)",
        },
        "MRR": {
            "image_path": f"/home/{hpc_user}/cortex/modules/mrr.sif",
            "command_template": (
                "python /app/run_mrr.py --input {input_file} --output {output_dir}"
            ),
            "input_type": "acquisition",
            "input_pattern": r".*_T2w\.nii\.gz$",
            "input_subdir": "anat",
            "requires_derivative": None,
            "output_name": "mrr",
            "default_cpus": 4,
            "default_mem": "24G",
            "default_gpus": 0,
            "default_time": "03:00:00",
            "description": "MRI reconstruction and registration",
        },
        "fMRIPrep": {
            "image_path": f"/home/{hpc_user}/cortex/modules/fmriprep.sif",
            "command_template": (
                "fmriprep {bids_dir} {output_dir} participant --participant-label {subject}"
            ),
            "input_type": "bids_root",
            "input_pattern": None,
            "input_subdir": None,
            "requires_derivative": None,
            "output_name": "fmriprep",
            "default_cpus": 8,
            "default_mem": "32G",
            "default_gpus": 0,
            "default_time": "24:00:00",
            "description": "fMRI preprocessing pipeline",
        },
        # To add a new module, copy a block above and fill in the fields.
        # "SuperSynth": {
        #     "image_path": f"/home/{hpc_user}/cortex/modules/supersynth.sif",
        #     "command_template": (
        #         "python /app/run_supersynth.py --input {input_file} --output {output_dir}"
        #     ),
        #     "input_type": "derivatives",
        #     "input_pattern": r".*_mrr\.nii\.gz$",
        #     "input_subdir": "anat",
        #     "requires_derivative": "mrr",
        #     "output_name": "supersynth",
        #     "default_cpus": 4,
        #     "default_mem": "16G",
        #     "default_gpus": 0,
        #     "default_time": "02:00:00",
        #     "description": "Synthetic contrast generation (requires MRR)",
        # },
    }


def resolve_submission_order(selected_modules: list, container_configs: dict) -> list:
    """Topological sort of selected modules so upstream modules submit first.

    Raises ValueError if a circular dependency is detected.
    """
    in_degree = {m: 0 for m in selected_modules}
    graph = {m: [] for m in selected_modules}
    for m in selected_modules:
        req = container_configs[m].get("requires_derivative")
        if req and req in selected_modules:
            graph[req].append(m)
            in_degree[m] += 1
    queue = [m for m in selected_modules if in_degree[m] == 0]
    order = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        for neighbor in graph[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    if len(order) != len(selected_modules):
        raise ValueError("Circular dependency detected in selected modules.")
    return order
