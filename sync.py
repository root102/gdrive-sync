#!/usr/bin/env python3
"""
Google Drive → HDD sync with full versioning.
Folder: https://drive.google.com/drive/folders/1PXIFZ8Vk_Wb6SgZH-30PUoJ_wFBekFu2
"""

import io
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

GOOGLE_MIME_EXPORT = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
    "application/vnd.google-apps.drawing": ("image/png", ".png"),
    "application/vnd.google-apps.script": ("application/json", ".json"),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("gdrive-sync")


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def get_drive_service(creds_file: str, token_file: str):
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            print("\n" + "="*60)
            print("Autoryzacja Google – otwórz link poniżej w przeglądarce:")
            print("(WSL2: wklej w Chrome/Edge na Windowsie)")
            print("="*60)
            creds = flow.run_local_server(port=8080, open_browser=False)
            print("="*60 + "\n")
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def list_folder_recursive(service, folder_id: str) -> list[dict]:
    """Return flat list of all files (not folders) under folder_id."""
    results = []
    page_token = None
    while True:
        resp = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="nextPageToken, files(id, name, mimeType, modifiedTime, md5Checksum, size)",
                pageToken=page_token,
            )
            .execute()
        )
        for item in resp.get("files", []):
            if item["mimeType"] == "application/vnd.google-apps.folder":
                results.extend(list_folder_recursive(service, item["id"]))
            else:
                item["_folder_id"] = folder_id
                results.append(item)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results


def build_path_map(service, folder_id: str, root_name: str = "") -> dict[str, str]:
    """Map each folder_id → relative path string."""
    mapping = {folder_id: root_name}
    page_token = None
    while True:
        resp = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="nextPageToken, files(id, name)",
                pageToken=page_token,
            )
            .execute()
        )
        for folder in resp.get("files", []):
            sub_path = os.path.join(root_name, folder["name"]) if root_name else folder["name"]
            mapping[folder["id"]] = sub_path
            mapping.update(build_path_map(service, folder["id"], sub_path))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return mapping


def file_checksum(path: Path) -> str:
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def save_version(current_path: Path, versions_root: Path):
    """Copy current file to versions directory with timestamp."""
    if not current_path.exists():
        return
    ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    rel = current_path.relative_to(current_path.parents[len(current_path.parts) - 2])
    ver_dir = versions_root / rel.parent / rel.stem
    ver_dir.mkdir(parents=True, exist_ok=True)
    suffix = current_path.suffix
    dest = ver_dir / f"{ts}{suffix}"
    shutil.copy2(current_path, dest)
    log.info(f"  versioned → {dest}")


def download_file(service, file_meta: dict, dest_path: Path):
    mime = file_meta["mimeType"]
    if mime in GOOGLE_MIME_EXPORT:
        export_mime, ext = GOOGLE_MIME_EXPORT[mime]
        if not dest_path.suffix:
            dest_path = dest_path.with_suffix(ext)
        request = service.files().export_media(fileId=file_meta["id"], mimeType=export_mime)
    else:
        request = service.files().get_media(fileId=file_meta["id"])

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    with open(dest_path, "wb") as f:
        f.write(buf.getvalue())


def load_state(state_file: Path) -> dict:
    if state_file.exists():
        with open(state_file) as f:
            return json.load(f)
    return {"files": {}, "page_token": None}


def save_state(state_file: Path, state: dict):
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


def parse_folder_id(id_or_url: str) -> str:
    """Accept raw ID or full Drive URL, return folder ID."""
    if "drive.google.com" in id_or_url:
        # https://drive.google.com/drive/folders/FOLDER_ID
        # https://drive.google.com/file/d/FILE_ID/view
        for part in id_or_url.rstrip("/").split("/"):
            if len(part) > 20 and part not in ("folders", "file", "d", "view", "drive"):
                return part
    return id_or_url.strip()


def sync_folder(service, folder_id: str, folder_name: str, dest_root: Path,
                versions_root: Path, state: dict) -> tuple[int, int]:
    """Sync a single Drive folder into dest_root/folder_name/. Returns (synced, skipped)."""
    base = dest_root / folder_name
    ver_base = versions_root / folder_name

    path_map = build_path_map(service, folder_id)
    files = list_folder_recursive(service, folder_id)

    synced = 0
    skipped = 0
    remote_ids = {f["id"] for f in files}

    for f in files:
        fid = f["id"]
        name = f["name"]
        mime = f["mimeType"]
        modified = f.get("modifiedTime", "")
        remote_md5 = f.get("md5Checksum", "")

        parent_fid = f.get("_folder_id", folder_id)
        rel_dir = path_map.get(parent_fid, "")
        rel_path = Path(rel_dir) / name if rel_dir else Path(name)

        if mime in GOOGLE_MIME_EXPORT:
            _, ext = GOOGLE_MIME_EXPORT[mime]
            if not rel_path.suffix or rel_path.suffix != ext:
                rel_path = rel_path.with_suffix(ext)

        dest_path = base / rel_path
        prev = state["files"].get(fid, {})

        if dest_path.exists() and prev.get("modifiedTime") == modified:
            if remote_md5 and prev.get("md5") == remote_md5:
                skipped += 1
                continue
            local_md5 = file_checksum(dest_path)
            if remote_md5 and local_md5 == remote_md5:
                skipped += 1
                continue

        if dest_path.exists():
            save_version(dest_path, ver_base)

        log.info(f"  downloading  {folder_name}/{rel_path}")
        try:
            download_file(service, f, dest_path)
            state["files"][fid] = {
                "name": name,
                "folder": folder_name,
                "path": str(rel_path),
                "modifiedTime": modified,
                "md5": remote_md5 or file_checksum(dest_path),
            }
            synced += 1
        except HttpError as e:
            log.error(f"  ERROR {folder_name}/{rel_path}: {e}")

    # remove files deleted from Drive (only those belonging to this folder)
    folder_fids = {fid for fid, v in state["files"].items() if v.get("folder") == folder_name}
    for fid in folder_fids - remote_ids:
        old_path = base / state["files"][fid]["path"]
        if old_path.exists():
            save_version(old_path, ver_base)
            old_path.unlink()
            log.info(f"  deleted (removed from Drive): {old_path}")
        del state["files"][fid]

    return synced, skipped


def sync_once(service, config: dict, state: dict) -> dict:
    dest_root = Path(config["dest_dir"])
    versions_root = Path(config["versions_dir"])
    state_file = Path(config["state_file"])

    # support both old single folder_id and new folders list
    folders = config.get("folders")
    if not folders:
        folders = [{"id": config["folder_id"], "name": "files"}]

    log.info("=== Sync started ===")
    total_synced = 0
    total_skipped = 0

    for entry in folders:
        fid = parse_folder_id(entry["id"])
        fname = entry.get("name", fid[:8])
        log.info(f"  folder: {fname}  ({fid})")
        try:
            s, k = sync_folder(service, fid, fname, dest_root, versions_root, state)
            total_synced += s
            total_skipped += k
        except Exception as e:
            log.error(f"  folder {fname} failed: {e}")

    save_state(state_file, state)
    log.info(f"=== Sync done: {total_synced} downloaded, {total_skipped} skipped ===\n")
    return state


def main():
    config = load_config()

    log_file = config.get("log_file")
    if log_file:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s"))
        log.addHandler(fh)

    service = get_drive_service(config["credentials_file"], config["token_file"])
    state = load_state(Path(config["state_file"]))

    interval = config.get("sync_interval_seconds", 600)

    log.info(f"Starting sync daemon  |  interval={interval}s  |  dest={config['dest_dir']}")
    while True:
        try:
            state = sync_once(service, config, state)
        except Exception as e:
            log.exception(f"Sync failed: {e}")
        time.sleep(interval)


if __name__ == "__main__":
    main()
