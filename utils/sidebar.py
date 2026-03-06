import streamlit as st


def render_project_selector(client) -> str | None:
    """Render the global project selector in the sidebar.

    Fetches the project list once per session and caches it in
    st.session_state["_project_list"].  The selected project is stored in
    st.session_state["selected_project"] and shared across all pages.

    Returns the currently selected project name, or None if no projects found.
    """
    st.sidebar.divider()
    st.sidebar.header("Project")

    # Load project list once per session; allow manual refresh
    if "_project_list" not in st.session_state:
        _refresh_project_list(client)

    projects = st.session_state.get("_project_list", [])

    if not projects:
        st.sidebar.caption("No projects found in ~/projects/")
        if st.sidebar.button("Refresh projects", use_container_width=True):
            _refresh_project_list(client)
        return None

    # Preserve current selection across reruns
    current = st.session_state.get("selected_project")
    default_idx = projects.index(current) if current in projects else 0

    st.sidebar.selectbox(
        "Active project",
        options=projects,
        index=default_idx,
        key="selected_project",
    )

    if st.sidebar.button("Refresh projects", use_container_width=True):
        _refresh_project_list(client)
        st.rerun()

    return st.session_state.get("selected_project")


def clear_project_state() -> None:
    """Clear project-related and connection-cached session state on disconnect."""
    for key in ("selected_project", "_project_list", "_home_dir", "_config_project"):
        st.session_state.pop(key, None)


def _refresh_project_list(client) -> None:
    try:
        st.session_state["_project_list"] = client.list_project_directories()
    except Exception as e:
        st.sidebar.warning(f"Could not load projects: {e}")
        st.session_state["_project_list"] = []
