"""
BIDS project index builder.

Walks ~/projects/ on the HPC via a single `find` command and produces a flat
list of file records.  The index is stored as JSON at $HOME/.cortex/bids_index.json
and loaded via SFTP so Streamlit never needs to make live SSH calls while browsing.

Expected BIDS path layouts that are indexed:
  Raw:        {home}/projects/<project>/sub-*/[ses-*]/<modality>/<file>
  Derivative: {home}/projects/<project>/derivatives/<module>/sub-*/[ses-*]/<modality>/<file>
"""

from datetime import datetime
from utils.hpc_io import read_json_from_hpc, write_json_to_hpc

_INDEX_RELPATH = ".cortex/bids_index.json"

# File extensions to include in the index
_INCLUDE_NAMES = (
    "*.nii.gz", "*.nii", "*.json", "*.tsv", "*.bvec", "*.bval"
)


# ── Public API ────────────────────────────────────────────────────────────────

def index_path(home_dir: str) -> str:
    return f"{home_dir}/{_INDEX_RELPATH}"


def build_index(client, home_dir: str) -> dict:
    """Walk ~/projects/ on the HPC and return an index dict ready for saving.

    Uses a single GNU find command (standard on Linux HPC) with -printf to
    avoid per-file SSH round-trips.  Parsing happens locally.
    """
    projects_dir = f"{home_dir}/projects"

    name_clauses = " -o ".join(f"-name '{pat}'" for pat in _INCLUDE_NAMES)
    find_cmd = (
        f"find {projects_dir} -maxdepth 8 -type f "
        f"\\( {name_clauses} \\) "
        r"-printf '%p\t%s\t%TY-%Tm-%Td\n' 2>/dev/null"
    )

    raw = client._run(find_cmd) or ""
    records = []
    for line in raw.splitlines():
        parts = line.strip().split("\t")
        if len(parts) != 3:
            continue
        record = _parse_bids_path(home_dir, *parts)
        if record:
            records.append(record)

    return {
        "built_at": datetime.now().isoformat(),
        "projects_dir": projects_dir,
        "record_count": len(records),
        "records": records,
    }


def load_index(client, home_dir: str) -> dict:
    """Load the saved index from the HPC. Returns {} if not found."""
    return read_json_from_hpc(client, index_path(home_dir))


def save_index(client, home_dir: str, index: dict) -> None:
    """Persist the index to the HPC."""
    write_json_to_hpc(client, index_path(home_dir), index)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _parse_bids_path(
    home_dir: str, file_path: str, size_str: str, mtime: str
) -> dict | None:
    """Parse an absolute HPC file path into a structured record.

    Returns None for paths that don't match the expected project layout.

    Supported layouts (relative to ~/projects/<project>/):
      Raw:        sub-*/[ses-*]/<modality>/<file>
      Derivative: derivatives/<module>/sub-*/[ses-*]/<modality>/<file>
    """
    prefix = f"{home_dir}/projects/"
    if not file_path.startswith(prefix):
        return None

    parts = file_path[len(prefix):].split("/")
    if len(parts) < 3:
        return None

    project = parts[0]

    # Derivative path: project/derivatives/<module>/sub-*/...
    if len(parts) >= 3 and parts[1] == "derivatives":
        module = parts[2] if len(parts) > 2 else "unknown"
        rest = parts[3:]
        data_type = f"derivative/{module}"
    else:
        rest = parts[1:]
        data_type = "raw"

    if not rest or not rest[0].startswith("sub-"):
        return None

    subject = rest[0]

    if len(rest) >= 2 and rest[1].startswith("ses-"):
        session = rest[1]
        modality = rest[2] if len(rest) > 3 else "—"
    else:
        session = "—"
        modality = rest[1] if len(rest) > 2 else "—"

    filename = parts[-1]

    try:
        size_display = _human_size(int(size_str))
    except ValueError:
        size_display = size_str

    return {
        "project": project,
        "type": data_type,
        "subject": subject,
        "session": session,
        "modality": modality,
        "filename": filename,
        "size": size_display,
        "mtime": mtime,
        "path": file_path,
    }


def _human_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.0f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes} TB"
