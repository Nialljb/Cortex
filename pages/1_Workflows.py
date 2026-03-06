import streamlit as st
from datetime import datetime

from utils.sidebar import render_project_selector, get_project_list
from utils.modules import build_container_configs, resolve_submission_order
from utils.hpc_io import read_json_from_hpc, write_json_to_hpc

st.set_page_config(page_title="Workflows", page_icon="🔄", layout="wide")

def inject_workflow_styles() -> None:
    st.markdown(
        """
        <style>
        .wf-topbar {
            background: #161b22;
            border: 1px solid #2a3444;
            border-radius: 8px;
            padding: 10px 14px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }
        .wf-logo {
            font-size: 11px;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: #4fc3f7;
            font-weight: 600;
        }
        .wf-badge {
            border: 1px solid #2a3444;
            border-radius: 4px;
            padding: 3px 8px;
            font-size: 11px;
            color: #cdd9e5;
            background: #1c2230;
        }
        .wf-panel {
            background: #161b22;
            border: 1px solid #2a3444;
            border-radius: 8px;
            overflow: hidden;
            margin-bottom: 12px;
        }
        .wf-panel-header {
            padding: 9px 12px;
            border-bottom: 1px solid #2a3444;
            background: #1c2230;
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: #768a9e;
            font-weight: 600;
        }
        .wf-panel-body {
            padding: 12px;
        }
        .wf-status-card {
            background: #1c2230;
            border: 1px solid #2a3444;
            border-radius: 6px;
            padding: 10px;
        }
        .wf-status-label {
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #768a9e;
            margin-bottom: 6px;
        }
        .wf-status-value {
            font-size: 22px;
            font-weight: 600;
            color: #cdd9e5;
            line-height: 1;
        }
        .wf-good { color: #81c784; }
        .wf-warn { color: #ffb74d; }
        .wf-bad { color: #f06292; }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_workflow_styles()
st.markdown(
    """
    <div class="wf-topbar">
      <div class="wf-logo">Cortex <span style="color:#768a9e;">Workflow Orchestrator</span></div>
      <div class="wf-badge">Pipeline Configuration + Status</div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown("## Workflows")

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

projects = get_project_list(client)

st.markdown("<div class='wf-panel'><div class='wf-panel-header'>Active Project</div><div class='wf-panel-body'>", unsafe_allow_html=True)
pcol, rcol = st.columns([5, 1])
with pcol:
    if projects:
        current = st.session_state.get("selected_project")
        default_idx = projects.index(current) if current in projects else 0
        widget_key = "_workflows_selected_project"
        desired_project = projects[default_idx]
        if st.session_state.get(widget_key) != desired_project:
            st.session_state[widget_key] = desired_project
        selected_project = st.selectbox(
            "Project",
            options=projects,
            key=widget_key,
            help="Shared across all pages.",
        )
        st.session_state["selected_project"] = selected_project
    else:
        selected_project = None
        st.warning("No projects found in `~/projects/`.")
with rcol:
    st.write("")
    if st.button("Refresh", key="wf_refresh_projects", use_container_width=True):
        get_project_list(client, refresh=True)
        st.rerun()
st.markdown("</div></div>", unsafe_allow_html=True)

# ── Project context ───────────────────────────────────────────────────────────
if not selected_project:
    st.info("Select an active project to get started.")
    st.stop()

# Cache home dir for the duration of the session to avoid repeated SSH calls
if "_home_dir" not in st.session_state:
    st.session_state["_home_dir"] = client._run("echo $HOME").strip()
home_dir = st.session_state["_home_dir"]

project_path = f"{home_dir}/projects/{selected_project}"
PIPELINE_CONFIG_PATH = f"{project_path}/.cortex/pipeline_config.json"

st.markdown(f"<div class='wf-badge'>Project path: {project_path}</div>", unsafe_allow_html=True)

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
tab_config, tab_status = st.tabs(["Pipeline Configuration", "Pipeline Status"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — PIPELINE CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
with tab_config:
    st.markdown("<div class='wf-panel'><div class='wf-panel-header'>Pipeline Configuration</div><div class='wf-panel-body'>", unsafe_allow_html=True)
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
    st.markdown("</div></div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — PIPELINE STATUS
# ══════════════════════════════════════════════════════════════════════════════
with tab_status:
    import pandas as pd

    st.markdown("<div class='wf-panel'><div class='wf-panel-header'>Pipeline Status</div><div class='wf-panel-body'>", unsafe_allow_html=True)
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

        status_counts = {"queued": 0, "running": 0, "complete": 0, "failed": 0}
        for modules in manifest.values():
            for info in modules.values():
                status = info.get("status")
                if status in status_counts:
                    status_counts[status] += 1

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(
                f"<div class='wf-status-card'><div class='wf-status-label'>Queued</div><div class='wf-status-value wf-warn'>{status_counts['queued']}</div></div>",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f"<div class='wf-status-card'><div class='wf-status-label'>Running</div><div class='wf-status-value'>{status_counts['running']}</div></div>",
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                f"<div class='wf-status-card'><div class='wf-status-label'>Complete</div><div class='wf-status-value wf-good'>{status_counts['complete']}</div></div>",
                unsafe_allow_html=True,
            )
        with c4:
            st.markdown(
                f"<div class='wf-status-card'><div class='wf-status-label'>Failed</div><div class='wf-status-value wf-bad'>{status_counts['failed']}</div></div>",
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)
        st.dataframe(df_status, use_container_width=True, hide_index=True)

        with st.expander("View job details"):
            detail_key = st.selectbox(
                "Subject / Session", options=sorted(manifest.keys()), key="status_detail_key"
            )
            if detail_key:
                for mod, info in manifest[detail_key].items():
                    st.markdown(f"**{mod}**")
                    st.json(info)
    st.markdown("</div></div>", unsafe_allow_html=True)
