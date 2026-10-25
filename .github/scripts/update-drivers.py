#!/usr/bin/env python3
"""
Query NVIDIA's driver lookup service (the same backend that populates
https://www.nvidia.com/en-us/drivers/unix/) for the latest Production,
New Feature, and Beta Linux driver versions, prefetch the runfile hashes,
and rewrite default.nix in-place.

Exits non-zero if a version cannot be resolved or a runfile cannot be fetched
so that the workflow fails loudly rather than silently skipping an update.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

UNIX_DRIVERS_PAGE = "https://www.nvidia.com/en-us/drivers/unix/"
DRIVER_LOOKUP_URL = (
    "https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/"
    "services/AjaxDriverService.php"
)
DEFAULT_NIX = Path(__file__).resolve().parents[2] / "default.nix"

# The Unix drivers page no longer renders versions server-side. Its inline
# JS issues one DriverManualLookup request per (OS, branch) pair and fills
# the "Latest ... Version:" slots from the responses. We issue the same
# requests directly. The query parameters below are copied from the page's
# `drvrLkupInputs` table; only `beta`, `qnf` and `sort1` differ per branch.
COMMON_PARAMS: dict[str, str] = {
    "func": "DriverManualLookup",
    "psid": "133",
    "pfid": "1075",
    "languageCode": "1033",
    "isWHQL": "0",
    "dltype": "-1",
    "dch": "0",
    "upCRD": "null",
    "ctk": "null",
    "numberOfResults": "1",
}

BRANCH_PARAMS: dict[str, dict[str, str]] = {
    "production": {"beta": "0", "qnf": "0", "sort1": ""},
    "new_feature": {"beta": "null", "qnf": "1", "sort1": "1"},
    "beta": {"beta": "1", "qnf": "0", "sort1": "1"},
}

# NVIDIA's osID for each runfile architecture default.nix tracks.
ARCH_OS_IDS: dict[str, str] = {
    "x86_64": "12",
    "aarch64": "124",
}


def lookup_driver(branch: str, arch: str) -> tuple[str, str]:
    """Return (version, runfile URL) NVIDIA publishes for `branch` on `arch`."""
    params = {**COMMON_PARAMS, **BRANCH_PARAMS[branch], "osID": ARCH_OS_IDS[arch]}
    req = urllib.request.Request(
        f"{DRIVER_LOOKUP_URL}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": "Mozilla/5.0 (nixpkgs-nvidia update bot)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)

    try:
        if str(data["Success"]) != "1":
            raise ValueError("lookup reported failure")
        info = data["IDS"][0]["downloadInfo"]
        version = info.get("DisplayVersion") or info["Version"]
        url = urllib.parse.unquote(info["DownloadURL"])
    except (KeyError, IndexError, TypeError, ValueError) as e:
        sys.exit(
            f"error: unexpected driver lookup response for {branch}/{arch} "
            f"({e!r}) — NVIDIA likely changed the {UNIX_DRIVERS_PAGE} backend"
        )

    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
        sys.exit(f"error: unparseable version {version!r} for {branch}/{arch}")
    if not url.endswith(f"-{version}.run"):
        sys.exit(f"error: download URL {url} does not match version {version}")
    return version, url


def resolve_branches() -> dict[str, tuple[str, str, str]]:
    """Return {branch: (version, x86_64 URL, aarch64 URL)}."""
    resolved: dict[str, tuple[str, str, str]] = {}
    for branch in BRANCH_PARAMS:
        x86_version, x86_url = lookup_driver(branch, "x86_64")
        aarch_version, aarch_url = lookup_driver(branch, "aarch64")
        # default.nix pins a single version per branch for both arches, so
        # refuse to proceed if NVIDIA has published them out of step.
        if x86_version != aarch_version:
            sys.exit(
                f"error: {branch} version mismatch between x86_64 "
                f"({x86_version}) and aarch64 ({aarch_version})"
            )
        resolved[branch] = (x86_version, x86_url, aarch_url)
    return resolved


def prefetch_sri(url: str) -> str:
    """Download `url` via nix-prefetch-url and return an SRI sha256 string."""
    base32 = subprocess.check_output(
        ["nix-prefetch-url", "--type", "sha256", url],
        text=True,
    ).strip()
    sri = subprocess.check_output(
        [
            "nix",
            "--extra-experimental-features",
            "nix-command",
            "hash",
            "convert",
            "--hash-algo",
            "sha256",
            "--to",
            "sri",
            base32,
        ],
        text=True,
    ).strip()
    return sri


def block_pattern(branch: str) -> re.Pattern[str]:
    # Matches the entire branch attribute body so we can substitute version
    # and both sha256 fields atomically. The body is non-greedy and stops
    # at the closing brace of the attrset.
    return re.compile(
        r"(?P<head>\b" + re.escape(branch) + r"\s*=\s*generic\s*\{)"
        r"(?P<body>[^}]*?)"
        r"(?P<tail>\})",
        re.DOTALL,
    )


def current_version(text: str, branch: str) -> str | None:
    m = block_pattern(branch).search(text)
    if not m:
        return None
    vm = re.search(r'version\s*=\s*"([^"]+)"', m.group("body"))
    return vm.group(1) if vm else None


def current_shas(text: str, branch: str) -> tuple[str | None, str | None]:
    m = block_pattern(branch).search(text)
    if not m:
        return None, None
    body = m.group("body")
    sha_64 = re.search(r'sha256_64bit\s*=\s*"([^"]+)"', body)
    sha_aarch = re.search(r'sha256_aarch64\s*=\s*"([^"]+)"', body)
    return (sha_64.group(1) if sha_64 else None,
            sha_aarch.group(1) if sha_aarch else None)


def update_branch(text: str, branch: str, version: str, sha_64: str, sha_aarch: str) -> str:
    def repl_body(body: str) -> str:
        body = re.sub(r'(version\s*=\s*")[^"]*(")', rf'\g<1>{version}\g<2>', body)
        body = re.sub(r'(sha256_64bit\s*=\s*")[^"]*(")', rf'\g<1>{sha_64}\g<2>', body)
        body = re.sub(r'(sha256_aarch64\s*=\s*")[^"]*(")', rf'\g<1>{sha_aarch}\g<2>', body)
        return body

    pat = block_pattern(branch)
    m = pat.search(text)
    if not m:
        sys.exit(f"error: branch '{branch}' not found in default.nix")
    return text[: m.start()] + m.group("head") + repl_body(m.group("body")) + m.group("tail") + text[m.end():]


def emit_github_output(updated: dict[str, str]) -> None:
    out_path = os.environ.get("GITHUB_OUTPUT")
    if not out_path:
        return
    with open(out_path, "a") as f:
        f.write(f"changed={'true' if updated else 'false'}\n")
        f.write(f"updated={json.dumps(updated)}\n")
        if updated:
            summary = ", ".join(f"{b} → {v}" for b, v in updated.items())
            f.write(f"summary={summary}\n")


def main() -> None:
    target = resolve_branches()
    print(
        "NVIDIA reports: "
        + ", ".join(f"{b}={v}" for b, (v, _, _) in target.items()),
        file=sys.stderr,
    )

    text = DEFAULT_NIX.read_text()
    updated: dict[str, str] = {}

    # We always prefetch the runfiles for the version NVIDIA reports,
    # even when default.nix already names that version. This catches
    # hash drift — e.g. NVIDIA re-publishing the same version under a
    # different artifact, or default.nix being hand-edited with a
    # mismatched hash. Cost: ~6 runfile downloads per run regardless.
    for branch, (target_version, x86_url, aarch_url) in target.items():
        cur_version = current_version(text, branch)
        if cur_version is None:
            sys.exit(f"error: branch '{branch}' missing from default.nix")
        cur_sha_64, cur_sha_aarch = current_shas(text, branch)

        new_sha_64 = prefetch_sri(x86_url)
        new_sha_aarch = prefetch_sri(aarch_url)

        if (cur_version, cur_sha_64, cur_sha_aarch) == (
            target_version, new_sha_64, new_sha_aarch
        ):
            print(f"{branch}: already at {cur_version} with matching hashes", file=sys.stderr)
            continue

        if cur_version != target_version:
            print(f"{branch}: {cur_version} -> {target_version}", file=sys.stderr)
        else:
            print(f"{branch}: hash drift at {cur_version}, refreshing", file=sys.stderr)

        text = update_branch(text, branch, target_version, new_sha_64, new_sha_aarch)
        updated[branch] = target_version

    if updated:
        DEFAULT_NIX.write_text(text)
        print("default.nix rewritten", file=sys.stderr)
    else:
        print("no updates needed", file=sys.stderr)

    emit_github_output(updated)


if __name__ == "__main__":
    main()
