import os
import json
import paramiko
from pathlib import Path
import tempfile

class HPCSSHClient:
    def __init__(self, hostname, username=None, password=None, key_path=None):
        self.hostname = hostname
        self.username = username or os.getenv("USER")
        self.password = password  # Will be cleared after connection
        self.key_path = os.path.expanduser(key_path or "~/.ssh/id_rsa") if key_path else None

        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._connect()

    def _connect(self):
        """Establish SSH connection using password or key authentication"""
        try:
            if self.password:
                # Password authentication
                self.ssh_client.connect(
                    hostname=self.hostname,
                    username=self.username,
                    password=self.password,
                    timeout=10,
                    look_for_keys=False,
                    allow_agent=False
                )
                # Clear password from memory immediately after connection
                self.password = None
            elif self.key_path:
                # Key-based authentication
                self.ssh_client.connect(
                    hostname=self.hostname,
                    username=self.username,
                    key_filename=self.key_path,
                    look_for_keys=True,
                    timeout=10,
                )
            else:
                raise ValueError("Either password or key_path must be provided")
            
            print(f"Connected to {self.hostname} as {self.username}")
        except paramiko.AuthenticationException:
            raise Exception("Authentication failed - check your credentials")
        except paramiko.SSHException as e:
            raise Exception(f"SSH connection error: {str(e)}")
        except Exception as e:
            raise Exception(f"Connection failed: {str(e)}")

    def _run(self, command):
        stdin, stdout, stderr = self.ssh_client.exec_command(command)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        if err:
            print(f"[stderr] {err}")
        return out
    
    def _run_with_exit_code(self, command):
        """Run command and return (stdout, stderr, exit_code)"""
        stdin, stdout, stderr = self.ssh_client.exec_command(command)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        exit_code = stdout.channel.recv_exit_status()
        return out, err, exit_code

    # --------------------------------------------------------------------
    # Basic filesystem and job management
    # --------------------------------------------------------------------
    def get_username(self):
        """Return the HPC username"""
        return self.username

    def list_projects(self, base_dir="/projects"):
        return self._run(f"ls -d {base_dir}/*/").splitlines()

    def list_directory(self, path):
        """List contents of a directory on the HPC"""
        try:
            command = f"ls -1 {path}"
            result = self._run(command)
            if not result:
                return []
            return [line.strip() for line in result.split('\n') if line.strip()]
        except Exception as e:
            raise Exception(f"Failed to list directory {path}: {str(e)}")

    def list_project_directories(self, base_path="~/projects"):
        """List all directories in the projects folder."""
        try:
            result = self._run(f"ls -d {base_path}/*/")
            if not result:
                return []
            # Extract just the directory names
            dirs = [d.strip().rstrip('/').split('/')[-1] for d in result.splitlines() if d.strip()]
            return sorted(dirs)
        except Exception as e:
            raise Exception(f"Failed to list project directories: {str(e)}")
    
    def job_status(self, job_id):
        """Return job state (RUNNING, COMPLETED, FAILED, etc.)."""
        state = self._run(f"squeue -j {job_id} -h -o '%T'")
        return state or "COMPLETED"

    def download_results(self, remote_path, local_path):
        sftp = self.ssh_client.open_sftp()
        sftp.get(remote_path, local_path)
        sftp.close()
        print(f"Downloaded {remote_path} → {local_path}")

    def submit_job(self, script_path, job_name="test_job"):
        """Submit a job to the scheduler (example: Slurm)."""
        cmd = f"sbatch --job-name={job_name} {script_path}"
        result = self._run(cmd)
        
        # Check if result is empty or doesn't contain expected output
        if not result:
            raise ValueError(f"sbatch command returned empty result. Command: {cmd}")
        
        # Split and check if we have output
        parts = result.split()
        if not parts:
            raise ValueError(f"sbatch command returned unexpected format: '{result}'")
        
        # Typical sbatch output: "Submitted batch job 12345"
        # Extract job ID (last element)
        job_id = parts[-1]
        
        # Validate it looks like a job ID (numeric)
        if not job_id.isdigit():
            raise ValueError(f"Expected numeric job ID, got: '{job_id}' from output: '{result}'")
        
        return {"job_id": job_id}
    # --------------------------------------------------------------------
    # Slurm + Apptainer job submission
    # --------------------------------------------------------------------

    def read_pipeline_manifest(self, project_path):
        """Read the pipeline status manifest from <project>/.cortex/pipeline_status.json.

        Returns an empty dict if the file does not exist yet.
        """
        manifest_path = f"{project_path}/.cortex/pipeline_status.json"
        try:
            sftp = self.ssh_client.open_sftp()
            with sftp.open(manifest_path, "rb") as f:
                content = f.read().decode("utf-8")
            sftp.close()
            return json.loads(content)
        except IOError:
            # File doesn't exist yet
            return {}
        except Exception as e:
            print(f"[manifest] Could not read manifest: {e}")
            return {}

    def write_pipeline_manifest(self, project_path, manifest):
        """Write the pipeline status manifest to <project>/.cortex/pipeline_status.json."""
        cortex_dir = f"{project_path}/.cortex"
        manifest_path = f"{cortex_dir}/pipeline_status.json"
        self._run(f"mkdir -p {cortex_dir}")
        content = json.dumps(manifest, indent=2).encode("utf-8")
        sftp = self.ssh_client.open_sftp()
        with sftp.open(manifest_path, "wb") as f:
            f.write(content)
        sftp.close()

    def poll_job_statuses(self, job_ids):
        """Return a dict of {job_id: status} for the given Slurm job IDs.

        Uses sacct (covers all states including completed/failed) with a
        squeue fallback for clusters where accounting is unavailable.
        Status values match Slurm states: PENDING, RUNNING, COMPLETED, FAILED,
        CANCELLED, TIMEOUT, OUT_OF_MEMORY.
        """
        if not job_ids:
            return {}
        ids_str = ",".join(str(j) for j in job_ids)
        # sacct covers historical jobs; squeue only covers active ones
        out = self._run(
            f"sacct -j {ids_str} --format=JobID,State --noheader --parsable2 2>/dev/null"
        )
        if not out:
            # Fall back to squeue for clusters without accounting enabled
            out = self._run(
                f"squeue -j {ids_str} -h -o '%i|%T' 2>/dev/null"
            )
        statuses = {}
        for line in out.splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            parts = line.split("|")
            if len(parts) < 2:
                continue
            # Strip array/step suffixes (e.g. "12345.batch" → "12345")
            job_id = parts[0].split(".")[0]
            state = parts[1].strip()
            if job_id.isdigit() and job_id not in statuses:
                statuses[job_id] = state
        return statuses

    def submit_apptainer_job(
        self,
        image_path,
        command,
        job_name="apptainer_job",
        work_dir="/home/$USER",
        cpus=2,
        mem="4G",
        gpus=0,
        time="01:00:00",
        output_log="slurm-%j.out",
        bind_paths=None,
        dependency_job_ids=None,
    ):
        """
        Create and submit a temporary SLURM batch script to run Apptainer.

        dependency_job_ids: optional list of Slurm job ID strings that must
        complete successfully before this job starts (afterok chaining).
        """
        slurm_script = f"""#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --output={output_log}
#SBATCH --cpus-per-task={cpus}
#SBATCH --mem={mem}
#SBATCH --time={time}
"""

        if dependency_job_ids:
            dep_str = ":".join(str(j) for j in dependency_job_ids)
            slurm_script += f"#SBATCH --dependency=afterok:{dep_str}\n"

        if gpus > 0:
            slurm_script += f"#SBATCH --gres=gpu:{gpus}\n"

        # Prepare bind paths for Apptainer
        bind_option = ""
        if bind_paths:
            # Clean up bind_paths - remove whitespace and ensure proper formatting
            bind_list = [p.strip() for p in bind_paths.split(',') if p.strip()]
            if bind_list:
                bind_option = f"--bind {','.join(bind_list)}"

        slurm_script += f"""
cd {work_dir}

echo "Running Apptainer job on $(hostname)"
apptainer exec {bind_option} {image_path} {command}

echo "Job completed at $(date)"
"""

        # Ensure work directory exists
        self._run(f"mkdir -p {work_dir}")
        
        # Ensure log directory exists (extract directory from output_log path)
        if "/" in output_log:
            log_dir = os.path.dirname(output_log)
            self._run(f"mkdir -p {log_dir}")

        # Write the script to a temporary file and upload it
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(slurm_script)
            tmp_local = f.name

        remote_script = f"{work_dir}/{job_name}.sh"
        sftp = self.ssh_client.open_sftp()
        sftp.put(tmp_local, remote_script)
        sftp.close()
        os.remove(tmp_local)

        # Submit job with better error handling
        out, err, exit_code = self._run_with_exit_code(f"sbatch {remote_script}")
        
        # Check if sbatch was successful
        if exit_code != 0:
            error_msg = f"sbatch failed with exit code {exit_code}"
            if err:
                error_msg += f"\nError: {err}"
            if out:
                error_msg += f"\nOutput: {out}"
            raise RuntimeError(error_msg)
        
        if not out:
            raise RuntimeError(f"sbatch command returned no output for {remote_script}")
        
        # Parse job ID from sbatch output (typically "Submitted batch job 12345")
        parts = out.strip().split()
        if len(parts) == 0:
            raise RuntimeError(f"Unexpected sbatch output: {out}")
        
        job_id = parts[-1]
        print(f"Submitted job {job_id}: {out}")
        return {"job_id": job_id, "remote_script": remote_script}

    def close(self):
        self.ssh_client.close()



# Additional methods can be added as needed, for example:

# def upload_file(self, local_path, remote_path):
#     sftp = self.ssh_client.open_sftp()
#     sftp.put(local_path, remote_path)
#     sftp.close()


