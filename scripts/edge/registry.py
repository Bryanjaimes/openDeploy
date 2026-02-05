"""Edge artifact registry — supports local filesystem and OCI (via ORAS CLI)."""

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

ORAS_MEDIA_TYPE = "application/vnd.opendeploy.model.v1+tar"


def _oras_available() -> bool:
    """Check if oras CLI is on PATH."""
    try:
        subprocess.run(["oras", "version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def push_oci(artifact_dir: Path, target: str, model: str, version: str) -> None:
    """Push artifacts to an OCI registry via the ``oras`` CLI.

    ``target`` should be an ``oci://`` URL, e.g. ``oci://ghcr.io/myorg``.
    """
    if not _oras_available():
        raise RuntimeError(
            "oras CLI is required for OCI push but was not found. "
            "Install from https://oras.land/docs/installation"
        )

    ref = f"{target.removeprefix('oci://')}/{model.replace('/', '_')}:{version}"

    # Collect files to push — each as its own layer
    files = [str(f) for f in artifact_dir.iterdir() if f.is_file()]
    if not files:
        raise ValueError(f"No files found in {artifact_dir}")

    cmd = [
        "oras", "push", ref,
        *[f"{f}:{ORAS_MEDIA_TYPE}" for f in files],
    ]
    logger.info("Pushing to OCI: %s", ref)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"oras push failed: {result.stderr}")
    logger.info("✅ OCI push complete: %s", ref)


def push_local(artifact_dir: Path, registry: str, model: str, version: str) -> None:
    """Copy artifacts to a local filesystem registry directory."""
    registry_root = Path(registry)
    target_dir = registry_root / model.replace("/", "_") / version
    target_dir.mkdir(parents=True, exist_ok=True)

    for item in artifact_dir.iterdir():
        if item.is_file():
            shutil.copy2(item, target_dir / item.name)

    manifest_path = target_dir / "manifest.json"
    if not manifest_path.exists():
        manifest_path.write_text(json.dumps({"model": model, "version": version}, indent=2))

    logger.info("📦 Pushed artifact to %s", target_dir)


def push_artifact(artifact_dir: Path, registry: str, model: str, version: str) -> None:
    """Push a built artifact to the given registry (local path or oci:// URL)."""
    if registry.startswith("oci://"):
        push_oci(artifact_dir, registry, model, version)
    else:
        push_local(artifact_dir, registry, model, version)
