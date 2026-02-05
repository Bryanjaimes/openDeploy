import argparse
import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def latest_version(model_dir: Path) -> Path | None:
    if not model_dir.exists():
        return None
    versions = [p for p in model_dir.iterdir() if p.is_dir()]
    if not versions:
        return None
    return sorted(versions, key=lambda p: p.name)[-1]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="OpenDeploy Edge OTA Agent")
    parser.add_argument("--registry", default="artifacts/registry", help="Registry path")
    parser.add_argument("--model", required=True, help="Model name")
    parser.add_argument("--cache", default="edge_cache", help="Local cache directory")
    parser.add_argument("--poll-seconds", type=int, default=30, help="Polling interval")
    args = parser.parse_args()

    registry_root = Path(args.registry)
    model_dir = registry_root / args.model.replace("/", "_")
    cache_root = Path(args.cache) / args.model.replace("/", "_")
    cache_root.mkdir(parents=True, exist_ok=True)

    state_path = cache_root / "current.json"
    current_version = None
    if state_path.exists():
        current_version = json.loads(state_path.read_text()).get("version")

    logger.info("Watching %s (current=%s)", model_dir, current_version)

    while True:
        latest = latest_version(model_dir)
        if latest and latest.name != current_version:
            logger.info("Updating to version %s", latest.name)
            target_dir = cache_root / latest.name
            target_dir.mkdir(parents=True, exist_ok=True)
            for item in latest.iterdir():
                if item.is_file():
                    (target_dir / item.name).write_bytes(item.read_bytes())
            state_path.write_text(json.dumps({"version": latest.name}, indent=2))
            current_version = latest.name
            logger.info("✅ Updated to %s", latest.name)

        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
