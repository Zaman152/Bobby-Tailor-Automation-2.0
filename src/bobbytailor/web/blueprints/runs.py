"""StackCT and PDF run initiation routes."""
import json
import logging
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Optional

from flask import Blueprint, jsonify, request, Response
from werkzeug.utils import secure_filename

from bobbytailor.web.jobs_runtime import jobs, object_manifests, register_job, uploads
from bobbytailor.web.jobs_runtime import _pdf_job, _stackct_job

logger = logging.getLogger(__name__)

runs_bp = Blueprint("runs", __name__)


def _job_conflict_response(active_job_id: str):
    """409 for a second concurrent job (WR-06 single-active-job guard)."""
    return jsonify({
        "error": (
            "Another takeoff job is already running. Wait for it to "
            "finish or cancel it before starting a new one."
        ),
        "active_job_id": active_job_id,
    }), 409


#: A filename that reads like a completed take-off rather than a set of plans.
#: Matches "takeoff", "take off", "take-off", "Take offs", in any case.
_TAKEOFF_NAME_RE = re.compile(r"take[ _-]?offs?\b", re.IGNORECASE)

#: The warning the operator sees. Stated as what the app WILL do with the file,
#: not as a scolding — the pipeline cannot tell a take-off from a plan set by
#: looking, and a take-off run through it produces confident, meaningless
#: numbers with nothing on the report to say so.
TAKEOFF_UPLOAD_WARNING = (
    "This filename looks like a completed TAKE-OFF, not a set of plans. "
    "Bobby Tailor measures plans; it has no way to tell a take-off apart from "
    "a drawing set once it starts, and running one produces confident numbers "
    "copied out of somebody else's quantities. Upload the PLANS instead — or "
    "confirm below if this really is a drawing set whose name happens to match."
)


def looks_like_completed_takeoff(filename) -> bool:
    """Does this uploaded filename read like a completed take-off?

    A filename heuristic and nothing more, which is why the caller WARNS rather
    than refuses: "Take-off Plaza - Plans.pdf" is a legitimate plan set and no
    regex can know that. It exists because ``POST /api/pdf/upload`` accepted
    ``Crow - Cass White Road-Take offs.pdf`` with a 200 and the operator got no
    signal at all (INV-A §3).

    The structural guard is elsewhere and unaffected: nothing scans the upload
    folder, only the selected ``upload_id`` is opened, and
    ``run_pdf_analysis`` passes ``allow_discovery=False``. This is the sign on
    the door, not the lock.
    """
    return bool(_TAKEOFF_NAME_RE.search(str(filename or "")))


def _plans_only_job_log(filename) -> list:
    """Opening job-log entries for a run started over a take-off-shaped name.

    Empty for every ordinary file. The warning travels onto the RUN and not
    only onto the upload screen because a run started over the operator's "are
    you sure" is a fact about that run, and a dialog leaves no record. Both PDF
    entry points call this — ``/api/run/pdf`` uploads and starts in one step
    and never sees the upload screen's warning at all.
    """
    if not looks_like_completed_takeoff(filename):
        return []
    from datetime import datetime as _dt
    logger.warning("PDF run started over take-off-shaped filename: %s", filename)
    return [{
        "timestamp": _dt.now().isoformat(),
        "type": "warning",
        "message": (
            "Started over a file whose name reads like a completed TAKE-OFF "
            "(%s). Bobby Tailor is plans-only. If this is not a drawing set, "
            "the numbers in this report are not a measurement of anything."
            % filename
        ),
    }]


def _safe_upload_name(filename, fallback: str = "upload.pdf") -> str:
    """Sanitize a browser-supplied filename for on-disk storage (WR-04).

    ``secure_filename`` strips path separators, control characters, and
    anything else unsafe for a single path segment; it can return an empty
    string for fully-hostile names, so a fallback is provided.
    """
    return secure_filename(filename or "") or fallback

@runs_bp.route("/api/run/stackct", methods=["POST"])
def run_stackct():
    """
    Start a StackCT scraping job.

    Body parameters:
        mode (str): "all" | "specific" — ignored when analyze_only=true.
        project_id (int): StackCT project ID (required for mode="specific").
        project_name (str): Human-readable project name.
        page_ids (list[int]): Optional subset of page IDs (mode="specific").
        folder_id (int): Optional plan-set folder ID.
        analyze_only (bool): Skip capture; re-run Claude on an existing
            manifest. Requires a prior capture run for project_name.
        manifest_dir (str): Optional explicit run folder path (absolute or
            relative to output/screenshots). Auto-discovers latest run when
            omitted. Only used when analyze_only=true.
    """
    data = request.json or {}
    mode = data.get("mode", "all")           # "all" | "specific"
    project_id = data.get("project_id")
    project_name = data.get("project_name", "Project")
    page_ids = data.get("page_ids")          # Optional list of specific page IDs to analyze
    folder_id = data.get("folder_id")
    analyze_only: bool = bool(data.get("analyze_only", False))
    manifest_dir: Optional[str] = data.get("manifest_dir") or None

    # Optional object manifest (canonical names + completeness) — used ONLY
    # when explicitly attached to this run. Production never auto-discovers
    # manifest files (plans-only LOCKED contract, 21-REVIEW WR-08).
    object_manifest_path: Optional[str] = None
    object_manifest_id = data.get("object_manifest_id")
    if object_manifest_id:
        man = object_manifests.get(object_manifest_id)
        if not man or not os.path.isfile(man.get("path", "")):
            return jsonify({"error": "Object manifest not found or expired"}), 404
        object_manifest_path = man["path"]

    # Validate page_ids belong to folder when both provided
    if not analyze_only and mode == "specific" and project_id and page_ids and folder_id is not None:
        from bobbytailor.stores import stackct_store as _store
        _store.init_db()
        allowed = {
            p["page_id"]
            for p in _store.get_plans(int(project_id), int(folder_id))
        }
        if allowed:
            bad = [pid for pid in page_ids if int(pid) not in allowed]
            if bad:
                return jsonify({
                    "error": (
                        f"page_ids {bad[:5]} are not in plan set folder {folder_id}"
                    ),
                }), 400

    mode_detail = "analyze_only" if analyze_only else "full"

    job_id = str(uuid.uuid4())[:8]
    conflict = register_job(job_id, {
        "id": job_id, "type": "stackct", "status": "queued",
        "progress": 0, "log": [], "result": None, "error": None,
        "project": project_name, "mode": mode, "mode_detail": mode_detail,
        "started_at": None,
        "current_phase": None,
        "current_sheet": {"index": 0, "total": 0, "name": None, "phase": None},
        "sheets_completed": [],
        "linked_sheets_count": 0,
        "linked_sheets_suggested_count": 0,
    })
    if conflict:
        return _job_conflict_response(conflict)

    t = threading.Thread(
        target=_stackct_job,
        args=(job_id, mode, project_id, project_name, page_ids, folder_id),
        kwargs={"analyze_only": analyze_only, "manifest_dir": manifest_dir,
                "object_manifest_path": object_manifest_path},
        daemon=True
    )
    t.start()
    return jsonify({"job_id": job_id})


@runs_bp.route("/api/pdf/upload", methods=["POST"])
def upload_pdf():
    """Upload a PDF and return metadata for page selection (no analysis)."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename or not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files accepted"}), 400

    upload_id = str(uuid.uuid4())[:8]
    save_path = os.path.join("uploads", f"{upload_id}_{_safe_upload_name(f.filename)}")
    f.save(save_path)

    from bobbytailor.pipeline.pdf_analyzer import get_pdf_metadata
    meta = get_pdf_metadata(save_path)

    plans_only_warning = (
        TAKEOFF_UPLOAD_WARNING if looks_like_completed_takeoff(f.filename) else None
    )
    if plans_only_warning:
        logger.warning(
            "Upload %s has a take-off-shaped filename (%s) — plans-only warning served",
            upload_id, f.filename,
        )

    uploads[upload_id] = {
        "save_path": save_path,
        "filename": f.filename,
        "plans_only_warning": plans_only_warning,
        **meta,
    }

    return jsonify({
        "upload_id": upload_id,
        "filename": f.filename,
        "page_count": meta["page_count"],
        "file_size_bytes": meta["file_size_bytes"],
        "pages": meta["pages"],
        "plans_only_warning": plans_only_warning,
    })


@runs_bp.route("/api/pdf/run", methods=["POST"])
def run_pdf_from_upload():
    """Start PDF analysis from a previous upload with optional page selection."""
    data = request.json or {}
    upload_id = data.get("upload_id")
    project_name = data.get("project_name")
    selected_pages = data.get("selected_pages")
    manifest_id = data.get("object_manifest_id")

    if not upload_id:
        return jsonify({"error": "upload_id required"}), 400

    upload = uploads.get(upload_id)
    if not upload:
        return jsonify({"error": "Upload not found or expired"}), 404

    pdf_path = upload["save_path"]
    if not os.path.isfile(pdf_path):
        return jsonify({"error": "Upload file missing on server"}), 404

    if not project_name:
        project_name = Path(upload.get("filename", "PDF Project")).stem

    manifest_path = None
    manifest_count = 0
    if manifest_id:
        man = object_manifests.get(manifest_id)
        if not man or not os.path.isfile(man.get("path", "")):
            return jsonify({"error": "Object manifest not found or expired"}), 404
        manifest_path = man["path"]
        manifest_count = man.get("count", 0)

    job_id = str(uuid.uuid4())[:8]
    conflict = register_job(job_id, {
        "id": job_id, "type": "pdf", "status": "queued",
        "progress": 0, "log": _plans_only_job_log(upload.get("filename")),
        "result": None, "error": None,
        "project": project_name,
        "file": upload.get("filename"),
        "started_at": None,
        "current_sheet": {"index": 0, "total": 0, "name": None, "phase": None},
        "sheets_completed": [],
        "selected_pages": selected_pages,
        "object_manifest_count": manifest_count,
    })
    if conflict:
        return _job_conflict_response(conflict)

    t = threading.Thread(
        target=_pdf_job,
        args=(job_id, pdf_path, project_name, selected_pages, manifest_path),
        daemon=True,
    )
    t.start()
    return jsonify({"job_id": job_id})


@runs_bp.route("/api/pdf/manifest/template", methods=["GET"])
def object_manifest_template():
    """Download a CSV template the user can fill in and upload as an object manifest."""
    from bobbytailor.devtools.object_manifest import template_csv
    from flask import Response
    return Response(
        template_csv(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=object_manifest_template.csv"},
    )


@runs_bp.route("/api/pdf/manifest/upload", methods=["POST"])
def upload_object_manifest():
    """Accept an object manifest as a file (CSV/JSON) OR an inline JSON list.

    The manifest lists the objects expected in the project with their canonical
    name + unit (no quantities). Returns a manifest_id to pass to /api/pdf/run.
    """
    from bobbytailor.devtools.object_manifest import load_manifest

    manifest_id = str(uuid.uuid4())[:8]
    save_path = os.path.join("uploads", f"manifest_{manifest_id}")

    try:
        if "file" in request.files:
            f = request.files["file"]
            if not f.filename:
                return jsonify({"error": "No file uploaded"}), 400
            ext = Path(f.filename).suffix.lower() or ".csv"
            if ext not in (".csv", ".json"):
                return jsonify({"error": "Object manifest must be .csv or .json"}), 400
            save_path += ext
            f.save(save_path)
        else:
            data = request.json or {}
            objects = data.get("objects") or data.get("manifest")
            if not isinstance(objects, list) or not objects:
                return jsonify({"error": "Provide a file or a non-empty 'objects' list"}), 400
            save_path += ".json"
            with open(save_path, "w", encoding="utf-8") as out:
                json.dump(objects, out)

        manifest = load_manifest(save_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Object manifest upload failed: %s", exc)
        return jsonify({"error": f"Could not parse object manifest: {exc}"}), 400

    if not manifest:
        return jsonify({"error": "Object manifest has no usable rows"}), 400

    preview = [
        {"name": e.name, "unit": e.unit, "measure": e.measure,
         "aliases": e.aliases}
        for e in manifest.entries[:50]
    ]
    object_manifests[manifest_id] = {
        "path": save_path,
        "count": len(manifest),
        "objects": preview,
    }
    return jsonify({
        "manifest_id": manifest_id,
        "count": len(manifest),
        "objects": preview,
    })


@runs_bp.route("/api/run/pdf", methods=["POST"])
def run_pdf():
    """Upload a PDF and start analysis job (legacy — all pages, single step)."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename or not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files accepted"}), 400

    project_name = request.form.get("project_name") or Path(f.filename).stem
    save_path = os.path.join("uploads", f"{str(uuid.uuid4())[:8]}_{_safe_upload_name(f.filename)}")
    f.save(save_path)

    job_id = str(uuid.uuid4())[:8]
    conflict = register_job(job_id, {
        "id": job_id, "type": "pdf", "status": "queued",
        "progress": 0, "log": _plans_only_job_log(f.filename),
        "result": None, "error": None,
        "project": project_name, "file": f.filename,
        "started_at": None,
        "current_sheet": {"index": 0, "total": 0, "name": None, "phase": None},
        "sheets_completed": []
    })
    if conflict:
        # Remove the file this rejected request already saved.
        try:
            os.remove(save_path)
        except OSError:
            pass
        return _job_conflict_response(conflict)

    t = threading.Thread(
        target=_pdf_job, args=(job_id, save_path, project_name), daemon=True
    )
    t.start()
    resp = {"job_id": job_id}
    if looks_like_completed_takeoff(f.filename):
        resp["plans_only_warning"] = TAKEOFF_UPLOAD_WARNING
    return jsonify(resp)

