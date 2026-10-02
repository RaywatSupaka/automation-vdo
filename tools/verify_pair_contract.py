"""Fail before packaging when Desktop, Extension, and helper tags disagree."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


class PairContractError(ValueError):
    pass


def _one(pattern: str, source: str, label: str) -> str:
    values = re.findall(pattern, source)
    if len(values) != 1:
        raise PairContractError(f"{label}: expected one version declaration, found {len(values)}")
    return values[0]


def verify_source_pair(root: Path) -> dict[str, str]:
    root = Path(root)
    release = json.loads((root / "CURRENT_RELEASE.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "browser_extension/manifest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise PairContractError("manifest: invalid Extension version")
    bridge = (root / "core/local_bridge.py").read_text(encoding="utf-8")
    launcher = (root / "launcher/SmartFlowLauncher.cs").read_text(encoding="utf-8")
    background = (root / "browser_extension/background.js").read_text(encoding="utf-8")
    flow = (root / "browser_extension/flow.js").read_text(encoding="utf-8")
    values = {
        "manifest": version,
        "release": release["runtime"]["extension_version"],
        "bridge": _one(r'REQUIRED_EXTENSION_VERSION\s*=\s*"(\d+\.\d+\.\d+)"', bridge, "bridge"),
        "launcher": _one(r'AssemblyFileVersion\("(\d+\.\d+\.\d+\.\d+)"\)', launcher, "launcher").rsplit(".", 1)[0],
    }
    helper = _one(r'const FLOW_HELPER_BUILD\s*=\s*"(flow-[^"]+)"', background, "background helper")
    flow_helper = _one(r'const helperBuild\s*=\s*"(flow-[^"]+)"', flow, "Flow helper")
    if helper != flow_helper or not helper.startswith(f"flow-{version}-"):
        raise PairContractError(f"helper mismatch: background={helper}, flow={flow_helper}, manifest={version}")
    if len(set(values.values())) != 1:
        raise PairContractError("version mismatch: " + ", ".join(f"{key}={value}" for key, value in values.items()))
    expected_folder = f"deliverables/SmartFlow_AI_Extension_{version}"
    if release["runtime"].get("install_directory") != expected_folder:
        raise PairContractError("release install_directory mismatch")
    if release["runtime"].get("install_zip") != expected_folder + ".zip":
        raise PairContractError("release install_zip mismatch")
    return {"version": version, "launcher_version": version + ".0", "helper_build": helper}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        print(json.dumps(verify_source_pair(args.root), indent=2))
    except (OSError, KeyError, ValueError, TypeError) as exc:
        parser.exit(1, f"PAIR CONTRACT FAILED: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
