import streamlit as st
import pandas as pd

from utils.sidebar import render_project_selector
from utils.bids_index import build_index, load_index, save_index

st.set_page_config(
    page_title="Data Browser",
    page_icon="📁",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Data Browser")

# ── Connection guard ──────────────────────────────────────────────────────────
if not st.session_state.get("connected") or not st.session_state.get("client"):
    st.warning("No HPC connection. Please connect via the Home page.")
    if st.button("Go to Home", use_container_width=True):
        st.switch_page("Home.py")
    st.stop()

client = st.session_state.client

# ── Sidebar: global project selector ─────────────────────────────────────────
render_project_selector(client)

# ── Home dir (cached) ─────────────────────────────────────────────────────────
if "_home_dir" not in st.session_state:
    st.session_state["_home_dir"] = client._run("echo $HOME").strip()
home_dir = st.session_state["_home_dir"]

# ── Index header: last-built time + rebuild button ────────────────────────────
index_data = load_index(client, home_dir)
built_at = index_data.get("built_at")
records = index_data.get("records", [])

header_col, btn_col = st.columns([5, 1])
with header_col:
    if built_at:
        st.caption(
            f"Index last built: {built_at[:19].replace('T', ' ')}  •  "
            f"{index_data.get('record_count', len(records)):,} files indexed"
        )
    else:
        st.caption("No index found. Click **Rebuild Index** to scan your projects.")

with btn_col:
    if st.button("Rebuild Index", type="primary", use_container_width=True):
        with st.spinner("Scanning BIDS projects on HPC…"):
            index_data = build_index(client, home_dir)
            save_index(client, home_dir, index_data)
        records = index_data.get("records", [])
        st.success(f"Index built: {len(records):,} files.")
        st.rerun()

if not records:
    st.info(
        "No files indexed yet. Click **Rebuild Index** to walk `~/projects/` "
        "on the HPC and populate the browser."
    )
    st.stop()

df = pd.DataFrame(records)

# ── Filters ───────────────────────────────────────────────────────────────────
st.subheader("Filters")

fc1, fc2, fc3, fc4, fc5 = st.columns([2, 2, 2, 2, 3])

# Project — pre-select from global project selector
all_projects = sorted(df["project"].unique())
selected_project = st.session_state.get("selected_project")
default_projects = (
    [selected_project]
    if selected_project and selected_project in all_projects
    else all_projects
)

with fc1:
    filter_projects = st.multiselect("Project", all_projects, default=default_projects)

view = df[df["project"].isin(filter_projects)] if filter_projects else df.copy()

with fc2:
    data_types = sorted(view["type"].unique())
    filter_types = st.multiselect("Type", data_types, default=data_types)

if filter_types:
    view = view[view["type"].isin(filter_types)]

with fc3:
    subjects = sorted(view["subject"].unique())
    filter_subjects = st.multiselect("Subject", subjects)

if filter_subjects:
    view = view[view["subject"].isin(filter_subjects)]

with fc4:
    sessions = sorted(view["session"].unique())
    filter_sessions = st.multiselect("Session", sessions)

if filter_sessions:
    view = view[view["session"].isin(filter_sessions)]

with fc5:
    filename_search = st.text_input("Filename contains", placeholder="T2w, bold, dwi…")

if filename_search:
    view = view[view["filename"].str.contains(filename_search, case=False, na=False)]

# ── Results table ─────────────────────────────────────────────────────────────
st.divider()
st.caption(f"Showing {len(view):,} of {len(df):,} files")

display_cols = ["project", "type", "subject", "session", "modality", "filename", "size", "mtime"]
event = st.dataframe(
    view[display_cols].reset_index(drop=True),
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "project":  st.column_config.TextColumn("Project"),
        "type":     st.column_config.TextColumn("Type"),
        "subject":  st.column_config.TextColumn("Subject"),
        "session":  st.column_config.TextColumn("Session"),
        "modality": st.column_config.TextColumn("Modality"),
        "filename": st.column_config.TextColumn("Filename"),
        "size":     st.column_config.TextColumn("Size", width="small"),
        "mtime":    st.column_config.TextColumn("Modified", width="small"),
    },
)

# ── File detail panel ─────────────────────────────────────────────────────────
if event.selection.rows:
    selected_idx = view.reset_index(drop=True).iloc[event.selection.rows[0]]
    st.divider()
    st.subheader("Selected file")

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Project", selected_idx["project"])
    d2.metric("Subject", selected_idx["subject"])
    d3.metric("Session", selected_idx["session"])
    d4.metric("Size", selected_idx["size"])

    st.code(selected_idx["path"], language=None)
    st.caption("Copy the path above to use in pipeline configuration or download commands.")
