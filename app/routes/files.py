"""File activity routes for the tracekit web app.

Routes
------
GET  /api/file/download?name=<filename>
    Download a file activity that belongs to the current user.  The file is
    served as an attachment (browser download) and never redirected to a public
    URL.  Ownership is verified against the FileActivity database record before
    any bytes are sent.

POST /api/file/upload
    Upload one or more activity files (or a .zip containing them) to the
    user's data folder.  Existing files are never overwritten.  Returns a JSON
    summary of saved / skipped / rejected files.
"""

import glob as _glob
import os
import zipfile

from flask import Blueprint, jsonify, request, send_file
from werkzeug.utils import secure_filename

files_bp = Blueprint("files", __name__)

# Lazy top-level imports — lets tests patch them without intercepting
# intra-function import calls.
from tracekit.providers.file.file_activity import FileActivity
from tracekit.user_context import get_user_id

# Extensions the file provider can parse
_SUPPORTED_EXTS = (".gpx", ".gpx.gz", ".fit", ".fit.gz", ".tcx", ".tcx.gz")


def _is_supported(name: str) -> bool:
    """Return True if *name* has a supported activity-file extension."""
    lower = name.lower()
    return any(lower.endswith(ext) for ext in _SUPPORTED_EXTS)


def _file_exists_in_folder(data_folder: str, filename: str) -> bool:
    """Return True if a file named *filename* already exists anywhere under data_folder."""
    return bool(_glob.glob(os.path.join(data_folder, "**", filename), recursive=True))


@files_bp.route("/api/file/download")
def api_file_download():
    """Serve a file activity as a download, verifying user ownership."""
    raw_name = request.args.get("name", "").strip()
    # Normalize to a secure, base-name-only filename
    filename = secure_filename(raw_name)
    if not filename:
        return "Invalid filename", 400

    user_id = get_user_id()

    # Verify the file belongs to this user before serving it
    activity = FileActivity.get_or_none(
        FileActivity.file_path == filename,
        FileActivity.user_id == user_id,
    )
    if not activity:
        return "File not found", 404

    data_dir = os.environ.get("TRACEKIT_DATA_DIR", "/opt/tracekit/data")
    data_folder = os.path.join(data_dir, "activities", str(user_id))
    matches = _glob.glob(os.path.join(data_folder, "**", filename), recursive=True)
    if not matches:
        return "File not found on disk", 404

    # Ensure the resolved path is contained within the user's data folder
    data_folder_real = os.path.realpath(data_folder)
    match_path = os.path.realpath(matches[0])
    if not match_path.startswith(data_folder_real + os.path.sep):
        return "File not found on disk", 404

    return send_file(match_path, as_attachment=True, download_name=filename)


@files_bp.route("/api/file/upload", methods=["POST"])
def api_file_upload():
    """Accept an activity file (or .zip of activity files) and queue processing.

    Returns JSON::

        {
            "saved":   ["activity.fit"],   # files written to disk and queued
            "skipped": ["dup.gpx"],        # already exist on disk — not overwritten
            "rejected":["bad.pdf"],        # unsupported extension
            "error":   "message"           # present only on hard failures
        }
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    uploaded = request.files["file"]
    if not uploaded.filename:
        return jsonify({"error": "Empty filename"}), 400

    original_name = secure_filename(uploaded.filename)
    if not original_name:
        return jsonify({"error": "Invalid filename"}), 400

    user_id = get_user_id()
    data_dir = os.environ.get("TRACEKIT_DATA_DIR", "/opt/tracekit/data")
    data_folder = os.path.join(data_dir, "activities", str(user_id))
    os.makedirs(data_folder, exist_ok=True)

    saved: list[str] = []
    skipped: list[str] = []
    rejected: list[str] = []

    if original_name.lower().endswith(".zip"):
        # Read the uploaded zip into memory and extract supported files.
        try:
            zf = zipfile.ZipFile(uploaded.stream)
        except zipfile.BadZipFile:
            return jsonify({"error": "Uploaded file is not a valid zip archive"}), 400

        with zf:
            for info in zf.infolist():
                member_name = secure_filename(os.path.basename(info.filename))
                if not member_name:
                    # Directory entry or name that normalised to empty — skip.
                    continue
                if not _is_supported(member_name):
                    rejected.append(member_name)
                    continue
                if _file_exists_in_folder(data_folder, member_name):
                    skipped.append(member_name)
                    continue
                dest_path = os.path.join(data_folder, member_name)
                with zf.open(info) as src, open(dest_path, "wb") as dst:
                    dst.write(src.read())
                saved.append(member_name)
                _enqueue_process_file(dest_path, user_id)
    elif _is_supported(original_name):
        if _file_exists_in_folder(data_folder, original_name):
            skipped.append(original_name)
        else:
            dest_path = os.path.join(data_folder, original_name)
            uploaded.save(dest_path)
            saved.append(original_name)
            _enqueue_process_file(dest_path, user_id)
    else:
        rejected.append(original_name)

    return jsonify({"saved": saved, "skipped": skipped, "rejected": rejected})


def _enqueue_process_file(file_path: str, user_id: int) -> None:
    """Enqueue a process_file Celery task; silently skip if worker unavailable."""
    try:
        from tracekit.worker import process_file

        process_file.delay(file_path, user_id=user_id)
    except Exception:
        pass
