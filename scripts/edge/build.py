import argparse
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def now_version() -> str:
    return time.strftime("%Y%m%d%H%M%S")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}")


def build_placeholder(artifact_path: Path, content: str) -> None:
    artifact_path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenDeploy Edge Build Pipeline")
    parser.add_argument("--model", required=True, help="Model name or path")
    parser.add_argument("--format", default="auto", choices=["auto", "gguf", "onnx"], help="Output format")
    parser.add_argument("--quant", default="q4_0", help="Quantization preset")
    parser.add_argument("--version", default="", help="Artifact version tag")
    parser.add_argument("--output", default="artifacts/edge", help="Output directory")
    parser.add_argument("--registry", default="artifacts/registry", help="Registry path or oci:// URL")
    parser.add_argument("--push", default="true", help="Push to registry (true/false)")

    args = parser.parse_args()
    version = args.version or now_version()
    output_root = Path(args.output)
    model_name = args.model
    format_name = "gguf" if args.format == "auto" else args.format

    artifact_dir = output_root / model_name.replace("/", "_") / version
    ensure_dir(artifact_dir)

    manifest = {
        "model": model_name,
        "format": format_name,
        "quant": args.quant,
        "version": version,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "opendeploy build --target edge",
        "artifacts": [],
        "status": "placeholder",
    }

    artifact_file = artifact_dir / f"{model_name.replace('/', '_')}.{format_name}"

    llama_cpp_path = os.getenv("LLAMA_CPP_PATH")
    autogptq_bin = os.getenv("AUTOGPTQ_BIN")

    try:
        if format_name == "gguf" and llama_cpp_path:
            convert_script = Path(llama_cpp_path) / "convert.py"
            if convert_script.exists():
                run(["python", str(convert_script), "--outtype", args.quant, "--outfile", str(artifact_file), model_name])
                manifest["status"] = "built"
        elif format_name == "onnx" and autogptq_bin:
            run([autogptq_bin, "--model", model_name, "--output", str(artifact_file)])
            manifest["status"] = "built"
    except Exception as exc:
        logger.warning("Build tool failed, creating placeholder: %s", exc)

    if not artifact_file.exists():
        build_placeholder(
            artifact_file,
            f"Placeholder artifact for {model_name} ({format_name}, {args.quant}).\n"
            "Set LLAMA_CPP_PATH or AUTOGPTQ_BIN to enable real builds.\n",
        )

    manifest["artifacts"].append({"path": str(artifact_file), "size": artifact_file.stat().st_size})

    manifest_path = artifact_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if args.push.lower() == "true":
        from scripts.edge.registry import push_artifact

        push_artifact(artifact_dir, args.registry, model_name, version)

    logger.info("✅ Edge build complete: %s", manifest_path)


if __name__ == "__main__":
    main()
