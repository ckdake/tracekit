"""File activity routes for the tracekit web app.

Routes
------
GET  /api/file/download?name=<filename>
    Download a file activity that belongs to the current user.  The file is
    served as an attachment (browser download) and never redirected to a public
    URL.  Ownership is verified against the FileActivity database record before
    any bytes are sent.
"""

import glob as _glob
import os

from flask import Blueprint, request, send_file

files_bp = Blueprint("files", __name__)

# Lazy top-level imports — lets tests patch them without intercepting
# intra-function import calls.
from tracekit.providers.file.file_activity import FileActivity
from tracekit.user_context import get_user_id


@files_bp.route("/api/file/download")
def api_file_download():
    """Serve a file activity as a download, verifying user ownership."""
    filename = request.args.get("name", "").strip()
    # Reject any path traversal attempts
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
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

    return send_file(matches[0], as_attachment=True, download_name=filename)
