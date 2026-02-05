import argparse
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="OpenDeploy Edge Runtime Selector")
    parser.add_argument("--artifact", required=True, help="Path to artifact directory")
    args = parser.parse_args()

    artifact_dir = Path(args.artifact)
    manifest_path = artifact_dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit("manifest.json not found")

    manifest = json.loads(manifest_path.read_text())
    fmt = manifest.get("format")

    if fmt == "gguf":
        logger.info("Runtime: llama.cpp")
        logger.info("Command: ./llama.cpp/server -m %s/*.gguf --port 8080", artifact_dir)
    elif fmt == "onnx":
        logger.info("Runtime: onnxruntime")
        logger.info("Command: python run_onnx.py --model %s/*.onnx", artifact_dir)
    else:
        logger.warning("Unknown format: %s", fmt)


if __name__ == "__main__":
    main()
