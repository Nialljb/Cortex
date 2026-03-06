import json


def read_json_from_hpc(client, remote_path: str) -> dict:
    """Read a JSON file from the HPC via SFTP. Returns {} if not found or unreadable."""
    try:
        sftp = client.ssh_client.open_sftp()
        with sftp.open(remote_path, "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    except IOError:
        return {}
    except Exception:
        return {}


def write_json_to_hpc(client, remote_path: str, data: dict) -> None:
    """Write a dict as JSON to a remote path via SFTP. Creates parent directories if needed."""
    parent_dir = remote_path.rsplit("/", 1)[0]
    client._run(f"mkdir -p {parent_dir}")
    content = json.dumps(data, indent=2).encode("utf-8")
    sftp = client.ssh_client.open_sftp()
    with sftp.open(remote_path, "wb") as f:
        f.write(content)
