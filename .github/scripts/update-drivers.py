#!/usr/bin/env python3
"""
Scrape https://www.nvidia.com/en-us/drivers/unix/ for the latest
"New Feature Branch" and "Beta" Linux x86_64 driver versions, prefetch
the runfile hashes, and rewrite default.nix in-place.

Exits non-zero if a version cannot be parsed or a runfile cannot be fetched
so that the workflow fails loudly rather than silently skipping an update.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

UNIX_DRIVERS_PAGE = "https://www.nvidia.com/en-us/drivers/unix/"
DEFAULT_NIX = Path(__file__).resolve().parents[2] / "default.nix"

# Each branch in default.nix corresponds to a heading on the NVIDIA Unix
# drivers page. The page renders as:
#
#   <span calss="title">Latest New Feature Branch Version:</span>
#   <a href="...">590.48.01</a>
#
# (the "calss" typo is NVIDIA's, not ours). The page repeats the same
# labels for each platform (Linux x86_64, aarch64, FreeBSD, Solaris) but
# all four list the same version, so we just grab the first match.
BRANCHES: dict[str, re.Pattern[str]] = {
    "production": re.compile(
        r"Latest\s+Production\s+Branch\s+Version:\s*</span>\s*"
        r"<[Aa][^>]*>(\d+\.\d+(?:\.\d+)?)</[Aa]>",
        re.IGNORECASE | re.DOTALL,
    ),
    "new_feature": re.compile(
        r"Latest\s+New\s+Feature\s+Branch\s+Version:\s*</span>\s*"
        r"<[Aa][^>]*>(\d+\.\d+(?:\.\d+)?)</[Aa]>",
        re.IGNORECASE | re.DOTALL,
    ),
    "beta": re.compile(
        r"Latest\s+Beta\s+Version:\s*</span>\s*"
        r"<[Aa][^>]*>(\d+\.\d+(?:\.\d+)?)</[Aa]>",
        re.IGNORECASE | re.DOTALL,
    ),
}


def fetch_page() -> str:
    req = urllib.request.Request(
        UNIX_DRIVERS_PAGE,
        headers={"User-Agent": "Mozilla/5.0 (nixpkgs-nvidia update bot)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_versions(html: str) -> dict[str, str]:
    versions: dict[str, str] = {}
    for branch, pattern in BRANCHES.items():
        m = pattern.search(html)
        if not m:
            sys.exit(
                f"error: could not locate version for branch '{branch}' on "
                f"{UNIX_DRIVERS_PAGE} — NVIDIA likely changed the page layout"
            )
        versions[branch] = m.group(1)
    return versions


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


def runfile_urls(version: str) -> tuple[str, str]:
    x86 = (
        f"https://download.nvidia.com/XFree86/Linux-x86_64/"
        f"{version}/NVIDIA-Linux-x86_64-{version}.run"
    )
    aarch = (
        f"https://download.nvidia.com/XFree86/Linux-aarch64/"
        f"{version}/NVIDIA-Linux-aarch64-{version}.run"
    )
    return x86, aarch


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
    html = fetch_page()
    target = parse_versions(html)
    print(f"NVIDIA page reports: {target}", file=sys.stderr)

    text = DEFAULT_NIX.read_text()
    updated: dict[str, str] = {}

    # We always prefetch the runfiles for the version NVIDIA reports,
    # even when default.nix already names that version. This catches
    # hash drift — e.g. NVIDIA re-publishing the same version under a
    # different artifact, or default.nix being hand-edited with a
    # mismatched hash. Cost: ~6 runfile downloads per run regardless.
    for branch, target_version in target.items():
        cur_version = current_version(text, branch)
        if cur_version is None:
            sys.exit(f"error: branch '{branch}' missing from default.nix")
        cur_sha_64, cur_sha_aarch = current_shas(text, branch)

        x86_url, aarch_url = runfile_urls(target_version)
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
