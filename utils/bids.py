"""
Shared BIDS filesystem helpers.

All functions communicate with the HPC via HPCSSHClient and return plain Python
types (lists, dicts).  No Streamlit calls here — callers are responsible for
surfacing errors to the UI.
"""


def get_projects(client) -> list[str]:
    """List project directories directly under ~/projects/."""
    try:
        result = client._run(
            "find $HOME/projects -maxdepth 1 -mindepth 1 -type d"
            " -exec basename {} \\;"
        )
        return sorted(p.strip() for p in result.split("\n") if p.strip()) if result else []
    except Exception:
        return []


def count_subjects_and_sessions(client, project_path: str) -> tuple[int, int]:
    """Return (num_subjects, num_sessions) for a project path."""
    try:
        r_sub = client._run(
            f"find {project_path} -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l"
        )
        r_ses = client._run(
            f"find {project_path} -mindepth 2 -maxdepth 2 -type d 2>/dev/null | wc -l"
        )
        return (
            int(r_sub.strip()) if r_sub else 0,
            int(r_ses.strip()) if r_ses else 0,
        )
    except Exception:
        return 0, 0


def get_subjects(client, project_path: str) -> list[str]:
    """List subject directories (sub-*) in a project."""
    try:
        result = client._run(
            f"find {project_path} -maxdepth 1 -mindepth 1 -type d"
            f" -exec basename {{}} \\;"
        )
        return sorted(s.strip() for s in result.split("\n") if s.strip()) if result else []
    except Exception:
        return []


def get_sessions(client, subject_path: str) -> list[str]:
    """List session directories (ses-*) for a subject."""
    try:
        result = client._run(
            f"find {subject_path} -maxdepth 1 -mindepth 1 -type d"
            f" -exec basename {{}} \\;"
        )
        return sorted(s.strip() for s in result.split("\n") if s.strip()) if result else []
    except Exception:
        return []


def get_acquisitions(client, session_path: str) -> list[str]:
    """List acquisition/modality directories for a session."""
    try:
        result = client._run(
            f"find {session_path} -maxdepth 1 -mindepth 1 -type d"
            f" -exec basename {{}} \\;"
        )
        return sorted(a.strip() for a in result.split("\n") if a.strip()) if result else []
    except Exception:
        return []


def get_files_in_directory(client, directory_path: str) -> list[dict]:
    """List files in a directory with name, size, and modification time.

    Returns a list of dicts: [{name, size, modified}, ...].
    """
    try:
        result = client._run(
            f"ls -lh --time-style=long-iso {directory_path} 2>/dev/null | grep '^-'"
        )
        if not result:
            return []
        files = []
        for line in result.split("\n"):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 8:
                files.append({
                    "name": " ".join(parts[7:]),
                    "size": parts[4],
                    "modified": f"{parts[5]} {parts[6]}",
                })
        return files
    except Exception:
        return []
