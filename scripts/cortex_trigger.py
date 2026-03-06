#!/usr/bin/env python3
"""
cortex_trigger.py — Cortex auto-trigger script.

Scans all projects under ~/projects/ for new or unprocessed subjects/sessions
and submits Slurm jobs for any pipeline modules not yet recorded as complete in
the project's pipeline manifest (.cortex/pipeline_status.json).

Reads pipeline configuration from .cortex/pipeline_config.json (written by the
Cortex Streamlit app's Pipeline Configuration tab).

Usage:
    python3 cortex_trigger.py [--projects-dir ~/projects] [--dry-run] [--retry-failed]

Example cron entry (runs daily at 06:00):
    0 6 * * * python3 ~/repos/Cortex/scripts/cortex_trigger.py >> ~/.cortex/trigger.log 2>&1

Example GitHub Actions step:
    - name: Trigger Cortex pipelines
      run: ssh $HPC_HOST "python3 ~/repos/Cortex/scripts/cortex_trigger.py"
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Allow importing utils.modules from the Cortex repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.modules import build_container_configs, resolve_submission_order

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("cortex_trigger")

# ── Slurm status map (sacct states → Cortex states) ──────────────────────────
_SLURM_MAP = {
    "RUNNING": "running",
    "PENDING": "queued",
    "COMPLETED": "complete",
    "FAILED": "failed",
    "CANCELLED": "failed",
    "TIMEOUT": "failed",
    "OUT_OF_MEMORY": "failed",
    "NODE_FAIL": "failed",
}


# ═════════════════════════════════════════════════════════════════════════════
# Core trigger logic
# ═════════════════════════════════════════════════════════════════════════════

class CortexTrigger:
    def __init__(
        self,
        projects_dir: Path,
        dry_run: bool = False,
        retry_failed: bool = False,
    ):
        self.projects_dir = projects_dir
        self.dry_run = dry_run
        self.retry_failed = retry_failed
        self.username = os.environ.get("USER", "unknown")
        self.container_configs = build_container_configs(self.username)

    # ── Entry point ───────────────────────────────────────────────────────────

    def run(self) -> None:
        log.info(
            "Cortex trigger started  |  projects_dir=%s  dry_run=%s  retry_failed=%s",
            self.projects_dir, self.dry_run, self.retry_failed,
        )

        projects_with_config = [
            d for d in sorted(self.projects_dir.iterdir())
            if d.is_dir() and (d / ".cortex" / "pipeline_config.json").exists()
        ]

        if not projects_with_config:
            log.info("No projects with pipeline_config.json found — nothing to do.")
            return

        for project_dir in projects_with_config:
            log.info("Processing project: %s", project_dir.name)
            try:
                self._process_project(project_dir)
            except Exception as exc:
                log.error("Error processing %s: %s", project_dir.name, exc)

        log.info("Cortex trigger finished.")

    # ── Per-project logic ─────────────────────────────────────────────────────

    def _process_project(self, project_dir: Path) -> None:
        config = json.loads(
            (project_dir / ".cortex" / "pipeline_config.json").read_text()
        )
        modules = config.get("modules", [])
        resource_overrides = config.get("resource_overrides", {})

        if not modules:
            log.warning("%s: pipeline_config.json has no modules — skipping.", project_dir.name)
            return

        try:
            ordered = resolve_submission_order(modules, self.container_configs)
        except ValueError as exc:
            log.error("%s: dependency error — %s", project_dir.name, exc)
            return

        manifest_path = project_dir / ".cortex" / "pipeline_status.json"
        manifest = (
            json.loads(manifest_path.read_text())
            if manifest_path.exists()
            else {}
        )

        # Optionally refresh in-flight statuses before deciding what to submit
        manifest = self._refresh_slurm_statuses(manifest)

        subjects = sorted(
            d.name for d in project_dir.iterdir()
            if d.is_dir() and d.name.startswith("sub-")
        )

        manifest_dirty = False

        for subject in subjects:
            subject_path = project_dir / subject
            sessions = sorted(
                d.name for d in subject_path.iterdir()
                if d.is_dir() and d.name.startswith("ses-")
            )
            if not sessions:
                sessions = [None]

            for session in sessions:
                session_label = session or "no_session"
                manifest_key = f"{subject}/{session_label}"

                if manifest_key not in manifest:
                    manifest[manifest_key] = {}

                # job_ids accumulated in this pass for within-session chaining
                session_job_ids: dict[str, str] = {}

                # Seed from already-queued/running entries so chaining works
                for mod, info in manifest[manifest_key].items():
                    if info.get("status") in ("queued", "running") and info.get("job_id"):
                        session_job_ids[mod] = info["job_id"]

                for module_name in ordered:
                    existing = manifest[manifest_key].get(module_name, {})
                    current_status = existing.get("status")

                    # Skip complete and in-flight jobs
                    if current_status == "complete":
                        continue
                    if current_status in ("queued", "running"):
                        log.debug(
                            "%s  %s/%s  %s: already %s — skipping",
                            project_dir.name, subject, session_label,
                            module_name, current_status,
                        )
                        continue
                    if current_status == "failed" and not self.retry_failed:
                        log.debug(
                            "%s  %s/%s  %s: failed (use --retry-failed to resubmit)",
                            project_dir.name, subject, session_label, module_name,
                        )
                        continue

                    # Resolve input and build command
                    command = self._resolve_command(
                        project_dir, subject, session, module_name
                    )
                    if command is None:
                        log.debug(
                            "%s  %s/%s  %s: no matching input — skipping",
                            project_dir.name, subject, session_label, module_name,
                        )
                        continue

                    cfg = self.container_configs[module_name]
                    ov = resource_overrides.get(module_name, {})

                    req_mod = cfg.get("requires_derivative")
                    dep_ids = (
                        [session_job_ids[req_mod]]
                        if req_mod and req_mod in session_job_ids
                        else []
                    )

                    time_fmt = "%Y%m%d_%H%M%S"
                    job_name = (
                        f"{cfg['output_name']}_{subject}_{session_label}"
                        f"_{datetime.now().strftime(time_fmt)}"
                    )
                    log_file = (
                        project_dir / "logs" / module_name.lower() / f"{job_name}.out"
                    )
                    work_dir = project_dir / "work" / module_name.lower()

                    if self.dry_run:
                        dep_str = (
                            f" [after {','.join(dep_ids)}]" if dep_ids else ""
                        )
                        log.info(
                            "[DRY RUN] %s  %s/%s  %s%s",
                            project_dir.name, subject, session_label,
                            module_name, dep_str,
                        )
                        log.info("  cmd: %s", command)
                    else:
                        try:
                            job_id = self._submit_slurm_job(
                                image_path=cfg["image_path"],
                                command=command,
                                job_name=job_name,
                                work_dir=work_dir,
                                log_file=log_file,
                                cpus=ov.get("cpus", cfg["default_cpus"]),
                                mem=ov.get("mem", cfg["default_mem"]),
                                gpus=ov.get("gpus", cfg["default_gpus"]),
                                time_limit=ov.get("time", cfg["default_time"]),
                                dep_ids=dep_ids,
                            )
                            session_job_ids[module_name] = job_id
                            manifest[manifest_key][module_name] = {
                                "status": "queued",
                                "job_id": job_id,
                                "submitted_at": datetime.now().isoformat(),
                                "completed_at": None,
                                "depends_on": [req_mod] if req_mod else [],
                            }
                            manifest_dirty = True
                            log.info(
                                "Submitted  %s  %s/%s  %s  → job %s",
                                project_dir.name, subject, session_label,
                                module_name, job_id,
                            )
                        except Exception as exc:
                            log.error(
                                "Failed to submit %s/%s %s: %s",
                                subject, session_label, module_name, exc,
                            )
                            manifest[manifest_key][module_name] = {
                                "status": "failed",
                                "job_id": None,
                                "submitted_at": datetime.now().isoformat(),
                                "completed_at": None,
                                "depends_on": [req_mod] if req_mod else [],
                                "error": str(exc),
                            }
                            manifest_dirty = True

        if manifest_dirty and not self.dry_run:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps(manifest, indent=2))
            log.info("%s: manifest updated.", project_dir.name)

    # ── Command resolution ────────────────────────────────────────────────────

    def _resolve_command(
        self,
        project_dir: Path,
        subject: str,
        session: str | None,
        module_name: str,
    ) -> str | None:
        """Build the container command string for a given subject/session/module.

        Returns None if a required input file cannot be found.
        """
        cfg = self.container_configs[module_name]
        subject_path = project_dir / subject
        session_path = subject_path / session if session else subject_path

        if cfg["input_type"] == "bids_root":
            subject_id = subject.replace("sub-", "")
            output_dir = project_dir / "derivatives" / cfg["output_name"]
            return cfg["command_template"].format(
                bids_dir=str(project_dir),
                output_dir=str(output_dir),
                subject=subject_id,
            )

        if cfg["input_type"] == "acquisition":
            search_dir = (
                session_path / cfg["input_subdir"]
                if cfg["input_subdir"]
                else session_path
            )
            input_file = self._find_file(search_dir, cfg["input_pattern"])
            if not input_file:
                return None
            output_dir = (
                project_dir / "derivatives" / cfg["output_name"] / subject / session
                if session
                else project_dir / "derivatives" / cfg["output_name"] / subject
            )
            return cfg["command_template"].format(
                input_file=str(input_file),
                output_dir=str(output_dir),
                subject=subject,
                session=session or "",
            )

        if cfg["input_type"] == "derivatives":
            req = cfg["requires_derivative"]
            deriv_dir = (
                project_dir / "derivatives" / req / subject / session / cfg["input_subdir"]
                if session
                else project_dir / "derivatives" / req / subject / cfg["input_subdir"]
            )
            input_file = self._find_file(deriv_dir, cfg["input_pattern"])
            if not input_file:
                return None
            output_dir = (
                project_dir / "derivatives" / cfg["output_name"] / subject / session
                if session
                else project_dir / "derivatives" / cfg["output_name"] / subject
            )
            return cfg["command_template"].format(
                input_file=str(input_file),
                output_dir=str(output_dir),
                subject=subject,
                session=session or "",
            )

        return None

    @staticmethod
    def _find_file(directory: Path, pattern: str) -> Path | None:
        """Return the first file in directory matching the regex pattern, or None."""
        if not directory.is_dir():
            return None
        for f in sorted(directory.iterdir()):
            if f.is_file() and re.search(pattern, f.name):
                return f
        return None

    # ── Slurm helpers ─────────────────────────────────────────────────────────

    def _submit_slurm_job(
        self,
        image_path: str,
        command: str,
        job_name: str,
        work_dir: Path,
        log_file: Path,
        cpus: int,
        mem: str,
        gpus: int,
        time_limit: str,
        dep_ids: list[str],
    ) -> str:
        """Write a temporary sbatch script and submit it. Returns the Slurm job ID."""
        work_dir.mkdir(parents=True, exist_ok=True)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        script_lines = [
            "#!/bin/bash",
            f"#SBATCH --job-name={job_name}",
            f"#SBATCH --output={log_file}",
            f"#SBATCH --cpus-per-task={cpus}",
            f"#SBATCH --mem={mem}",
            f"#SBATCH --time={time_limit}",
        ]
        if dep_ids:
            dep_str = ":".join(str(j) for j in dep_ids)
            script_lines.append(f"#SBATCH --dependency=afterok:{dep_str}")
        if gpus > 0:
            script_lines.append(f"#SBATCH --gres=gpu:{gpus}")

        script_lines += [
            "",
            f"cd {work_dir}",
            'echo "Running Apptainer job on $(hostname)"',
            f"apptainer exec {image_path} {command}",
            'echo "Job completed at $(date)"',
        ]

        script_content = "\n".join(script_lines) + "\n"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sh", delete=False, prefix="cortex_"
        ) as tmp:
            tmp.write(script_content)
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                ["sbatch", tmp_path],
                capture_output=True,
                text=True,
                check=True,
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        # sbatch stdout: "Submitted batch job <ID>"
        match = re.search(r"(\d+)", result.stdout)
        if not match:
            raise RuntimeError(
                f"Could not parse job ID from sbatch output: {result.stdout!r}"
            )
        return match.group(1)

    # ── Slurm status refresh ──────────────────────────────────────────────────

    @staticmethod
    def _refresh_slurm_statuses(manifest: dict) -> dict:
        """Poll sacct for all in-flight job IDs and update manifest statuses."""
        in_flight = [
            info["job_id"]
            for mods in manifest.values()
            for info in mods.values()
            if info.get("job_id") and info.get("status") in ("queued", "running")
        ]
        if not in_flight:
            return manifest

        try:
            result = subprocess.run(
                [
                    "sacct", "-j", ",".join(in_flight),
                    "--format=JobID,State",
                    "--noheader", "--parsable2",
                ],
                capture_output=True, text=True, timeout=30,
            )
        except Exception as exc:
            log.warning("Could not poll Slurm statuses: %s", exc)
            return manifest

        statuses: dict[str, str] = {}
        for line in result.stdout.splitlines():
            parts = line.strip().split("|")
            if len(parts) >= 2:
                job_id, state = parts[0].strip(), parts[1].strip().split()[0]
                if job_id.isdigit():
                    statuses[job_id] = _SLURM_MAP.get(state, "unknown")

        for mods in manifest.values():
            for info in mods.values():
                jid = info.get("job_id")
                if jid and jid in statuses:
                    new_status = statuses[jid]
                    info["status"] = new_status
                    if new_status == "complete" and not info.get("completed_at"):
                        info["completed_at"] = datetime.now().isoformat()
        return manifest


# ═════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cortex auto-trigger: submit Slurm jobs for unprocessed BIDS data."
    )
    parser.add_argument(
        "--projects-dir",
        type=Path,
        default=Path.home() / "projects",
        help="Path to the projects root directory (default: ~/projects)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be submitted without actually calling sbatch.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Resubmit entries with status 'failed' (default: skip them).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    projects_dir = args.projects_dir.expanduser().resolve()
    if not projects_dir.is_dir():
        log.error("Projects directory not found: %s", projects_dir)
        sys.exit(1)

    trigger = CortexTrigger(
        projects_dir=projects_dir,
        dry_run=args.dry_run,
        retry_failed=args.retry_failed,
    )
    trigger.run()


if __name__ == "__main__":
    main()
