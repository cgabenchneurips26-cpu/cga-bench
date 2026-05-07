"""Record current environment info to JSON for reproducibility."""
import json
import sys
import platform
import subprocess
from datetime import datetime
from pathlib import Path


def _collect_dataset_versions() -> dict:
    """Collect dataset version/DOI/commit hash from registry manifests."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from cga_bench.semantic_layer.external.registry import REGISTRY
        versions = {}
        for dataset_id, manifest in REGISTRY.items():
            versions[dataset_id] = {
                "name": manifest.dataset_name,
                "version": manifest.version,
                "commit_hash": manifest.commit_hash,
                "artifact_url": manifest.artifact_url,
                "license": manifest.license,
                "access_level": manifest.access_level,
            }
        return versions
    except ImportError:
        return {"error": "registry not importable"}


def record_environment(output_dir: str | None = None) -> dict:
    git_sha = subprocess.getoutput("git rev-parse HEAD").strip()
    git_dirty = bool(subprocess.getoutput("git status --porcelain").strip())
    info = {
        "timestamp": datetime.utcnow().isoformat(),
        "python_version": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "git_sha": git_sha,
        "git_dirty": git_dirty,
        "pip_freeze": subprocess.getoutput("pip freeze").strip().split("\n"),
        "dataset_versions": _collect_dataset_versions(),
    }
    if output_dir:
        date_str = datetime.utcnow().strftime("%Y%m%d")
        out_path = Path(output_dir) / date_str / git_sha[:8]
        out_path.mkdir(parents=True, exist_ok=True)
        with open(out_path / "environment.json", "w") as f:
            json.dump(info, f, indent=2)
    return info


if __name__ == "__main__":
    info = record_environment("reports")
    print(json.dumps(info, indent=2))
