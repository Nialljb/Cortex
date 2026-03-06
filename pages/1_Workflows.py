import re
import streamlit as st
from datetime import datetime

from utils.sidebar import render_project_selector
from utils.modules import build_container_configs, resolve_submission_order
from utils.hpc_io import read_json_from_hpc, write_json_to_hpc

st.set_page_config(page_title="Workflows", page_icon="🔄", layout="wide")

st.title("Workflows")

# ── Connection guard ──────────────────────────────────────────────────────────
if not st.session_state.get("connected") or not st.session_state.get("client"):
    st.error("Not connected to HPC cluster. Please connect using the sidebar.")
    st.stop()

client = st.session_state.client

try:
    hpc_username = client.get_username()
except Exception:
    hpc_username = st.session_state.get("hpc_username", "username")

if "job_history" not in st.session_state:
    st.session_state.job_history = []

CONTAINER_CONFIGS = build_container_configs(hpc_username)

# ── Sidebar: global project selector ─────────────────────────────────────────
render_project_selector(client)

# ── Project context ───────────────────────────────────────────────────────────
selected_project = st.session_state.get("selected_project")
if not selected_project:
    st.info("Select a project from the sidebar to get started.")
    st.stop()

# Cache home dir for the duration of the session to avoid repeated SSH calls
if "_home_dir" not in st.session_state:
    st.session_state["_home_dir"] = client._run("echo $HOME").strip()
home_dir = st.session_state["_home_dir"]

project_path = f"{home_dir}/projects/{selected_project}"
PIPELINE_CONFIG_PATH = f"{project_path}/.cortex/pipeline_config.json"

st.caption(f"Project path: `{project_path}`")

# ── Helper: manifest status refresh ──────────────────────────────────────────
def refresh_manifest_statuses(manifest: dict) -> dict:
    """Poll Slurm for all in-flight job IDs and update manifest statuses in place."""
    slurm_to_cortex = {
        "RUNNING": "running",
        "PENDING": "queued",
        "COMPLETED": "complete",
        "FAILED": "failed",
        "CANCELLED": "failed",
        "TIMEOUT": "failed",
        "OUT_OF_MEMORY": "failed",
        "NODE_FAIL": "failed",
    }
    job_ids = [
        info["job_id"]
        for modules in manifest.values()
        for info in modules.values()
        if info.get("job_id") and info.get("status") in ("queued", "running")
    ]
    if not job_ids:
        return manifest
    slurm_statuses = client.poll_job_statuses(job_ids)
    for modules in manifest.values():
        for info in modules.values():
            jid = info.get("job_id")
            if jid and jid in slurm_statuses:
                new_status = slurm_to_cortex.get(slurm_statuses[jid], "unknown")
                info["status"] = new_status
                if new_status == "complete" and not info.get("completed_at"):
                    info["completed_at"] = datetime.now().isoformat()
    return manifest


# ── Helper: load saved config into widget session-state keys ─────────────────
def _load_config_into_state(config: dict) -> None:
    """Pre-populate widget keys from a saved pipeline config dict."""
    saved_modules = set(config.get("modules", []))
    overrides = config.get("resource_overrides", {})
    for mod_name, cfg in CONTAINER_CONFIGS.items():
        st.session_state[f"cfg_mod_{mod_name}"] = mod_name in saved_modules
        mod_ov = overrides.get(mod_name, {})
        st.session_state[f"cfg_cpus_{mod_name}"] = mod_ov.get("cpus", cfg["default_cpus"])
        st.session_state[f"cfg_mem_{mod_name}"] = mod_ov.get("mem", cfg["default_mem"])
        st.session_state[f"cfg_gpus_{mod_name}"] = mod_ov.get("gpus", cfg["default_gpus"])
        st.session_state[f"cfg_time_{mod_name}"] = mod_ov.get("time", cfg["default_time"])


# Auto-load saved config once per project switch
_config_project_key = "_config_project"
if st.session_state.get(_config_project_key) != selected_project:
    saved_config = read_json_from_hpc(client, PIPELINE_CONFIG_PATH)
    if saved_config:
        _load_config_into_state(saved_config)
    st.session_state[_config_project_key] = selected_project


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_config, tab_trigger, tab_status = st.tabs(
    ["Pipeline Configuration", "Manual Trigger", "Pipeline Status"]
)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — PIPELINE CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
with tab_config:
    st.header("Pipeline Configuration")
    st.write(
        "Select the modules to include in this project's pipeline and set resource "
        "allocations. Save the configuration to persist it for this project — the saved "
        "config is also read by the auto-trigger script."
    )

    saved_config = read_json_from_hpc(client, PIPELINE_CONFIG_PATH)
    if saved_config:
        updated = saved_config.get("updated_at", "unknown")
        st.success(f"Saved configuration found (last updated: {updated})")
        if st.button("Reload from saved config", key="cfg_reload"):
            _load_config_into_state(saved_config)
            st.session_state[_config_project_key] = selected_project
            st.rerun()

    st.subheader("Select Modules")

    # Dependency labels for display
    dep_labels = {
        mod_name: (
            f" ← requires **{cfg['requires_derivative'].upper()}**"
            if cfg.get("requires_derivative")
            else ""
        )
        for mod_name, cfg in CONTAINER_CONFIGS.items()
    }

    cols = st.columns(3)
    for idx, (mod_name, cfg) in enumerate(CONTAINER_CONFIGS.items()):
        with cols[idx % 3]:
            st.checkbox(
                mod_name,
                key=f"cfg_mod_{mod_name}",
                help=f"{cfg['description']}{dep_labels[mod_name]}",
            )

    selected_modules = [
        m for m in CONTAINER_CONFIGS if st.session_state.get(f"cfg_mod_{m}")
    ]

    if selected_modules:
        # Warn about unsatisfied dependencies
        for mod in selected_modules:
            req = CONTAINER_CONFIGS[mod].get("requires_derivative")
            if req and req not in selected_modules:
                st.warning(
                    f"**{mod}** requires **{req.upper()}** as input. "
                    f"Add {req.upper()} to the pipeline, or ensure its output already "
                    f"exists in `derivatives/{req}/`."
                )

        try:
            ordered = resolve_submission_order(selected_modules, CONTAINER_CONFIGS)
            st.info(f"Submission order: **{' → '.join(ordered)}**")
        except ValueError as exc:
            st.error(str(exc))
            ordered = []

        if ordered:
            st.subheader("Resource Allocations")
            for mod_name in ordered:
                cfg = CONTAINER_CONFIGS[mod_name]
                with st.expander(f"{mod_name} — {cfg['description']}", expanded=False):
                    c1, c2, c3, c4 = st.columns(4)
                    c1.number_input(
                        "CPUs", min_value=1, max_value=64,
                        key=f"cfg_cpus_{mod_name}",
                    )
                    c2.text_input("Memory", key=f"cfg_mem_{mod_name}")
                    c3.number_input(
                        "GPUs", min_value=0, max_value=8,
                        key=f"cfg_gpus_{mod_name}",
                    )
                    c4.text_input("Time limit", key=f"cfg_time_{mod_name}")

    if st.button("Save Configuration", type="primary", use_container_width=True):
        if not selected_modules:
            st.error("Select at least one module before saving.")
        else:
            resource_overrides = {
                mod_name: {
                    "cpus": st.session_state[f"cfg_cpus_{mod_name}"],
                    "mem": st.session_state[f"cfg_mem_{mod_name}"],
                    "gpus": st.session_state[f"cfg_gpus_{mod_name}"],
                    "time": st.session_state[f"cfg_time_{mod_name}"],
                }
                for mod_name in selected_modules
            }
            config = {
                "modules": selected_modules,
                "resource_overrides": resource_overrides,
                "updated_at": datetime.now().isoformat(),
            }
            try:
                write_json_to_hpc(client, PIPELINE_CONFIG_PATH, config)
                st.success(
                    f"Configuration saved for **{selected_project}**: "
                    f"{' → '.join(selected_modules)}"
                )
                st.session_state[_config_project_key] = ""  # force reload on next render
            except Exception as exc:
                st.error(f"Failed to save configuration: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — MANUAL TRIGGER
# ══════════════════════════════════════════════════════════════════════════════
with tab_trigger:
    st.header("Manual Trigger")
    st.write(
        "Submit the configured pipeline immediately for selected subjects/sessions. "
        "Already-completed sessions (per the pipeline manifest) are skipped automatically."
    )

    config = read_json_from_hpc(client, PIPELINE_CONFIG_PATH)
    if not config:
        st.info(
            "No pipeline configuration found for this project. "
            "Set one up in the **Pipeline Configuration** tab first."
        )
        st.stop()

    trigger_modules = config.get("modules", [])
    resource_overrides = config.get("resource_overrides", {})

    try:
        ordered = resolve_submission_order(trigger_modules, CONTAINER_CONFIGS)
    except ValueError as exc:
        st.error(f"Dependency error in saved config: {exc}")
        st.stop()

    st.info(f"Configured pipeline: **{' → '.join(ordered)}**")

    # Warn about unresolved dependencies
    for mod in ordered:
        req = CONTAINER_CONFIGS[mod].get("requires_derivative")
        if req and req not in ordered:
            st.warning(
                f"**{mod}** requires **{req.upper()}** — not in pipeline. "
                f"Ensure `derivatives/{req}/` exists for all subjects."
            )

    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        subject_filter = st.text_input(
            "Subject filter (optional)",
            placeholder="sub-01, sub-02",
            help="Comma-separated subject IDs. Leave blank to process all.",
        )
    with col2:
        session_filter = st.text_input(
            "Session filter (optional)",
            placeholder="ses-01",
            help="Partial match on session label. Leave blank for all.",
        )

    dry_run = st.checkbox("Dry run (preview jobs without submitting)")

    if st.button("Submit Pipeline", type="primary", use_container_width=True):
        manifest = client.read_pipeline_manifest(project_path)

        try:
            all_items = client.list_directory(project_path)
            subjects = sorted(s for s in all_items if s.startswith("sub-"))
        except Exception as exc:
            st.error(f"Could not scan project directory: {exc}")
            subjects = []

        if subject_filter:
            filter_list = [s.strip() for s in subject_filter.split(",")]
            subjects = [s for s in subjects if s in filter_list]

        if not subjects:
            st.warning("No matching subjects found in project directory.")
        else:
            progress = st.progress(0)
            submitted_count = 0
            skipped_count = 0

            for sub_idx, subject in enumerate(subjects):
                subject_path = f"{project_path}/{subject}"

                try:
                    sub_contents = client.list_directory(subject_path)
                    sessions = sorted(d for d in sub_contents if d.startswith("ses-"))
                except Exception:
                    sessions = []

                if not sessions:
                    sessions = [None]

                for session in sessions:
                    session_label = session or "no_session"

                    if session_filter and session and session_filter not in session:
                        continue

                    manifest_key = f"{subject}/{session_label}"
                    if manifest_key not in manifest:
                        manifest[manifest_key] = {}

                    # Accumulate job IDs within this subject/session for chaining
                    session_job_ids: dict[str, str] = {}

                    for module_name in ordered:
                        cfg = CONTAINER_CONFIGS[module_name]

                        # Skip already-completed entries
                        existing = manifest[manifest_key].get(module_name, {})
                        if existing.get("status") == "complete":
                            st.write(
                                f"✓ `{subject}/{session_label}` — **{module_name}**: "
                                "already complete, skipping"
                            )
                            skipped_count += 1
                            continue

                        # ── Resolve input and build command ───────────────
                        command = None

                        if cfg["input_type"] == "bids_root":
                            subject_id = subject.replace("sub-", "")
                            output_dir = (
                                f"{project_path}/derivatives/{cfg['output_name']}"
                            )
                            command = cfg["command_template"].format(
                                bids_dir=project_path,
                                output_dir=output_dir,
                                subject=subject_id,
                            )

                        elif cfg["input_type"] == "acquisition":
                            search_path = (
                                f"{subject_path}/{session}/{cfg['input_subdir']}"
                                if session
                                else f"{subject_path}/{cfg['input_subdir']}"
                            )
                            try:
                                file_list = client.list_directory(search_path)
                            except Exception:
                                st.write(
                                    f"⏭ `{subject}/{session_label}` — **{module_name}**: "
                                    f"`{cfg['input_subdir']}` dir not found"
                                )
                                skipped_count += 1
                                continue
                            input_file = next(
                                (
                                    f"{search_path}/{fn}"
                                    for fn in file_list
                                    if re.search(cfg["input_pattern"], fn)
                                ),
                                None,
                            )
                            if not input_file:
                                st.write(
                                    f"⏭ `{subject}/{session_label}` — **{module_name}**: "
                                    f"no file matching `{cfg['input_pattern']}`"
                                )
                                skipped_count += 1
                                continue
                            output_dir = (
                                f"{project_path}/derivatives/{cfg['output_name']}"
                                f"/{subject}/{session}"
                                if session
                                else f"{project_path}/derivatives/{cfg['output_name']}"
                                f"/{subject}"
                            )
                            command = cfg["command_template"].format(
                                input_file=input_file,
                                output_dir=output_dir,
                                subject=subject,
                                session=session or "",
                            )

                        elif cfg["input_type"] == "derivatives":
                            req = cfg["requires_derivative"]
                            deriv_path = (
                                f"{project_path}/derivatives/{req}"
                                f"/{subject}/{session}/{cfg['input_subdir']}"
                                if session
                                else f"{project_path}/derivatives/{req}"
                                f"/{subject}/{cfg['input_subdir']}"
                            )
                            try:
                                file_list = client.list_directory(deriv_path)
                            except Exception:
                                st.write(
                                    f"⏭ `{subject}/{session_label}` — **{module_name}**: "
                                    f"no `{req}` derivative output found"
                                )
                                skipped_count += 1
                                continue
                            input_file = next(
                                (
                                    f"{deriv_path}/{fn}"
                                    for fn in file_list
                                    if re.search(cfg["input_pattern"], fn)
                                ),
                                None,
                            )
                            if not input_file:
                                st.write(
                                    f"⏭ `{subject}/{session_label}` — **{module_name}**: "
                                    f"no matching file in `{req}` derivatives"
                                )
                                skipped_count += 1
                                continue
                            output_dir = (
                                f"{project_path}/derivatives/{cfg['output_name']}"
                                f"/{subject}/{session}"
                                if session
                                else f"{project_path}/derivatives/{cfg['output_name']}"
                                f"/{subject}"
                            )
                            command = cfg["command_template"].format(
                                input_file=input_file,
                                output_dir=output_dir,
                                subject=subject,
                                session=session or "",
                            )

                        if command is None:
                            st.write(
                                f"⏭ `{subject}/{session_label}` — **{module_name}**: "
                                f"unknown input_type `{cfg['input_type']}`"
                            )
                            skipped_count += 1
                            continue

                        # ── Slurm dependency chaining ─────────────────────
                        req_mod = cfg.get("requires_derivative")
                        dep_ids = (
                            [session_job_ids[req_mod]]
                            if req_mod and req_mod in session_job_ids
                            else []
                        )

                        # ── Resource allocation (saved config → defaults) ──
                        ov = resource_overrides.get(module_name, {})
                        cpus = ov.get("cpus", cfg["default_cpus"])
                        mem = ov.get("mem", cfg["default_mem"])
                        gpus = ov.get("gpus", cfg["default_gpus"])
                        time_limit = ov.get("time", cfg["default_time"])

                        time_fmt = "%Y%m%d_%H%M%S"
                        job_name = (
                            f"{cfg['output_name']}_{subject}_{session_label}"
                            f"_{datetime.now().strftime(time_fmt)}"
                        )
                        work_dir = f"{project_path}/work/{module_name.lower()}"
                        log_file = (
                            f"{project_path}/logs/{module_name.lower()}/{job_name}.out"
                        )

                        if dry_run:
                            dep_str = (
                                f" [after job {', '.join(dep_ids)}]" if dep_ids else ""
                            )
                            st.write(
                                f"[DRY RUN] `{subject}/{session_label}` — "
                                f"**{module_name}**{dep_str}"
                            )
                            st.code(command, language="bash")
                            manifest[manifest_key][module_name] = {
                                "status": "dry_run",
                                "job_id": None,
                                "submitted_at": datetime.now().isoformat(),
                                "completed_at": None,
                                "depends_on": [req_mod] if req_mod else [],
                            }
                        else:
                            try:
                                result = client.submit_apptainer_job(
                                    image_path=cfg["image_path"],
                                    command=command,
                                    job_name=job_name,
                                    work_dir=work_dir,
                                    cpus=cpus,
                                    mem=mem,
                                    gpus=gpus,
                                    time=time_limit,
                                    output_log=log_file,
                                    dependency_job_ids=dep_ids or None,
                                )
                                job_id = result["job_id"]
                                session_job_ids[module_name] = job_id
                                manifest[manifest_key][module_name] = {
                                    "status": "queued",
                                    "job_id": job_id,
                                    "submitted_at": datetime.now().isoformat(),
                                    "completed_at": None,
                                    "depends_on": [req_mod] if req_mod else [],
                                }
                                submitted_count += 1
                                st.write(
                                    f"✅ `{subject}/{session_label}` — "
                                    f"**{module_name}**: job `{job_id}`"
                                )
                            except Exception as exc:
                                st.error(
                                    f"❌ `{subject}/{session_label}` — "
                                    f"**{module_name}**: {exc}"
                                )
                                manifest[manifest_key][module_name] = {
                                    "status": "failed",
                                    "job_id": None,
                                    "submitted_at": datetime.now().isoformat(),
                                    "completed_at": None,
                                    "depends_on": [req_mod] if req_mod else [],
                                    "error": str(exc),
                                }

                progress.progress((sub_idx + 1) / len(subjects))

            progress.empty()

            if dry_run:
                st.info("Dry run complete — no jobs submitted.")
            else:
                client.write_pipeline_manifest(project_path, manifest)
                st.success(
                    f"Pipeline submitted: {submitted_count} jobs queued, "
                    f"{skipped_count} already complete or skipped."
                )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — PIPELINE STATUS
# ══════════════════════════════════════════════════════════════════════════════
with tab_status:
    import pandas as pd

    st.header("Pipeline Status")
    st.caption(f"Project: **{selected_project}**")

    refresh_clicked = st.button("Refresh Status", key="status_refresh")

    manifest = client.read_pipeline_manifest(project_path)

    if refresh_clicked and manifest:
        with st.spinner("Polling Slurm for job statuses..."):
            manifest = refresh_manifest_statuses(manifest)
        client.write_pipeline_manifest(project_path, manifest)
        st.success("Status updated.")

    if not manifest:
        st.info("No pipeline runs recorded for this project yet.")
    else:
        STATUS_ICONS = {
            "queued":   "🟡 queued",
            "running":  "🟢 running",
            "complete": "✅ complete",
            "failed":   "❌ failed",
            "dry_run":  "🔍 dry_run",
            "unknown":  "⚪ unknown",
        }

        all_modules = sorted({mod for mods in manifest.values() for mod in mods})
        rows = []
        for key, mods in sorted(manifest.items()):
            row = {"Subject / Session": key}
            for mod in all_modules:
                info = mods.get(mod, {})
                status = info.get("status", "—")
                row[mod] = STATUS_ICONS.get(status, status)
            rows.append(row)

        df_status = pd.DataFrame(rows)
        st.dataframe(df_status, use_container_width=True, hide_index=True)

        with st.expander("View job details"):
            detail_key = st.selectbox(
                "Subject / Session", options=sorted(manifest.keys()), key="status_detail_key"
            )
            if detail_key:
                for mod, info in manifest[detail_key].items():
                    st.markdown(f"**{mod}**")
                    st.json(info)
