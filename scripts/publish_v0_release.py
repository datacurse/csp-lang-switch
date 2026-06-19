#!/usr/bin/env python3
"""Update GitHub release v0 notes and replace csp-lang-switch.exe.

Only the exe is uploaded as a release asset. GitHub also shows automatic
"Source code (zip/tar.gz)" links on the release page; those cannot be removed
on public repos. Point users at the direct exe URL instead of the release page.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BODY = ROOT / "release-notes" / "v0.md"
EXE = ROOT / "dist" / "csp-lang-switch.exe"
OWNER = "datacurse"
REPO = "csp-lang-switch"
TAG = "v0"
ASSET_NAME = "csp-lang-switch.exe"


def get_token() -> str:
    proc = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    creds: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            creds[key] = value
    token = creds.get("password", "").strip()
    if not token:
        sys.exit("error: no GitHub token from git credential")
    return token


def api(token: str, method: str, url: str, data: bytes | None = None,
        content_type: str = "application/json") -> bytes:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if data is not None:
        headers["Content-Type"] = content_type
        headers["Content-Length"] = str(len(data))
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        sys.exit(f"GitHub API error {exc.code}: {exc.read().decode()}")


def api_json(token: str, method: str, url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    raw = api(token, method, url, data)
    return json.loads(raw.decode()) if raw else {}


def get_release(token: str) -> dict:
    return api_json(token, "GET",
                      f"https://api.github.com/repos/{OWNER}/{REPO}/releases/tags/{TAG}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--notes-only", action="store_true",
        help="Update release notes only; do not replace the exe asset",
    )
    parser.add_argument(
        "--asset-only", action="store_true",
        help="Replace the exe asset only; do not change release notes",
    )
    args = parser.parse_args()

    if args.notes_only and args.asset_only:
        sys.exit("error: --notes-only and --asset-only are mutually exclusive")

    if not BODY.is_file():
        sys.exit(f"error: missing {BODY}")
    if not args.notes_only and not EXE.is_file():
        sys.exit(f"error: missing {EXE} — run pyinstaller first")

    token = get_token()
    release = get_release(token)
    release_id = release["id"]

    if not args.asset_only:
        body = BODY.read_text(encoding="utf-8")
        api(token, "PATCH",
            f"https://api.github.com/repos/{OWNER}/{REPO}/releases/{release_id}",
            json.dumps({"body": body}).encode())
        print("updated release body")

    if args.notes_only:
        return 0

    for asset in release.get("assets", []):
        if asset.get("name") == ASSET_NAME:
            api(token, "DELETE",
                f"https://api.github.com/repos/{OWNER}/{REPO}/releases/assets/{asset['id']}")
            print("deleted old asset")
            break

    exe_data = EXE.read_bytes()
    upload_url = (
        f"https://uploads.github.com/repos/{OWNER}/{REPO}/releases/"
        f"{release_id}/assets?name={ASSET_NAME}"
    )
    api(token, "POST", upload_url, exe_data, "application/octet-stream")
    print(f"uploaded {EXE.name} ({len(exe_data):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
