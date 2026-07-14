"""Job status, cancellation, and history routes."""
import logging
import re
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import login_required

from bobbytailor.stores import job_store
from bobbytailor.web.jobs_runtime import jobs

logger = logging.getLogger(__name__)

jobs_bp = Blueprint("jobs", __name__)

@jobs_bp.route("/api/status/<job_id>")
def job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    # Don't return full result in status poll — too large
    cs = job.get("current_sheet", {})
    completed = job.get("sheets_completed", [])
    return jsonify({
        "id": job["id"],
        "type": job["type"],
        "status": job["status"],
        "progress": job["progress"],
        "started_at": job.get("started_at"),
        "current_sheet": cs,
        "current_phase": job.get("current_phase") or (cs.get("phase") if cs else None),
        "sheets_completed": len(completed),
        "total_sheets": cs.get("total") or job.get("total_sheets") or 0,
        "cancelling": bool(job.get("_cancel") and job["status"] in ("running", "queued")),
        "sheet_log": completed[-10:],
        "sheet_log_full": completed,
        "log": job["log"][-50:],
        "project": job["project"],
        "error": job["error"],
        "warning": job.get("warning"),
        "has_result": job["result"] is not None,
        "linked_sheets_count": job.get("linked_sheets_count", 0),
        "linked_sheets_suggested_count": job.get("linked_sheets_suggested_count", 0),
    })


@jobs_bp.route("/api/cancel/<job_id>", methods=["POST"])
def cancel_job(job_id):
    """Request cooperative cancellation of a running or queued job."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job.get("_cancel"):
        return jsonify({"success": True, "message": "Cancellation already requested"})
    if job["status"] not in ("running", "queued"):
        return jsonify({"error": "Job is not running"}), 400
    job["_cancel"] = True
    job["current_phase"] = "cancelling"
    job["log"].append({
        "timestamp": datetime.now().isoformat(),
        "type": "info",
        "message": "Cancellation requested — stopping after current step…",
    })
    return jsonify({"success": True})


@jobs_bp.route("/api/jobs/active")
def get_active_job():
    """Return the currently running job, if any. Used by sidebar mini-card (JOB-04)."""
    for job in jobs.values():
        if job["status"] == "running":
            return jsonify({
                "active": True,
                "job": {
                    "id": job["id"],
                    "type": job["type"],
                    "project": job["project"],
                    "progress": job["progress"],
                    "started_at": job.get("started_at"),
                    "current_sheet": job.get("current_sheet", {}),
                    "sheets_completed": len(job.get("sheets_completed", []))
                }
            })
    return jsonify({"active": False, "job": None})


@jobs_bp.route("/api/jobs/history")
@login_required
def job_history_list():
    """Paginated list of completed job runs, newest first."""
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
    except (ValueError, TypeError):
        limit, offset = 50, 0

    outcome_filter = request.args.get("outcome") or None
    valid_outcomes = {"success", "partial", "failed", "cancelled"}
    if outcome_filter and outcome_filter not in valid_outcomes:
        return jsonify({"error": f"Invalid outcome filter: {outcome_filter}"}), 400

    runs = job_store.list_job_runs(limit=limit, offset=offset, outcome=outcome_filter)
    return jsonify({"runs": runs, "limit": limit, "offset": offset})


@jobs_bp.route("/api/jobs/history/<job_id>")
@login_required
def job_history_detail(job_id: str):
    """Full detail for a single completed job run, including log tail."""
    if not re.match(r"^[a-zA-Z0-9\-]{1,64}$", job_id):
        return jsonify({"error": "Invalid job_id format"}), 400

    run = job_store.get_job_run(job_id)
    if run is None:
        return jsonify({"error": "Job not found in history"}), 404
    return jsonify(run)

