"""Project catalog and dashboard routes."""
import logging

from flask import Blueprint, jsonify, render_template, request, send_file

logger = logging.getLogger(__name__)

projects_bp = Blueprint("projects", __name__)

@projects_bp.route("/")
def index():
    return render_template("index.html")


@projects_bp.route("/api/projects")
def get_projects():
    """Return project list from SQLite (DB-first).

    Query: ?refresh=1 forces live StackCT sync.
    Response may include from_cache, stale, syncing.
    Legacy projects_cache.json is no longer read on this path.
    """
    from project_cache import get_projects as _get
    force = request.args.get("refresh") == "1"
    result = _get(force_refresh=force)
    return jsonify(result)


@projects_bp.route("/api/projects/refresh", methods=["POST"])
def refresh_projects():
    """Force StackCT project catalog sync into SQLite."""
    from stackct_sync import sync_projects
    result = sync_projects(force=True)
    return jsonify(result)


@projects_bp.route("/api/projects/sheet-counts")
def get_sheet_counts():
    """Return sheet counts per project_id from SQLite (no browser when DB warm)."""
    from project_cache import get_all_sheet_counts as _counts
    return jsonify(_counts())


@projects_bp.route("/api/projects/<int:project_id>/sync-plan-sets", methods=["POST"])
def sync_plan_sets_route(project_id):
    """Warm plan-set (folder) index for a project into SQLite."""
    from stackct_sync import sync_project_plan_sets
    force = request.args.get("force") == "1"
    count_sheets = request.args.get("counts") == "1"
    return jsonify(
        sync_project_plan_sets(project_id, force=force, count_sheets=count_sheets)
    )


@projects_bp.route("/api/projects/<int:project_id>/plan-sets")
def get_plan_sets_route(project_id):
    """Return plan sets (folders) for a project (DB-first).

    Query: ?refresh=1 — full sync with per-folder sheet counts (slow)
           ?wait=1 — block until fast folder list is ready (Preview Plans)
    """
    from project_cache import get_project_plan_sets as _get
    force = request.args.get("refresh") == "1"
    wait = request.args.get("wait") == "1"
    return jsonify(_get(project_id, force_refresh=force, wait=wait))


@projects_bp.route("/api/projects/<int:project_id>/plan-sets/<int:folder_id>/plans")
def get_folder_plans(project_id, folder_id):
    """Return drawing pages for one plan set (DB-first). Query: ?refresh=1"""
    from project_cache import get_project_plans as _get_plans
    force = request.args.get("refresh") == "1"
    background = request.args.get("background") == "1"
    return jsonify(
        _get_plans(
            project_id,
            folder_id,
            force_refresh=force,
            background=background,
        )
    )


def _stackct_project_name(project_id: int) -> str:
    import stackct_store as store

    store.init_db()
    for p in store.list_projects():
        if p.get("id") == project_id:
            return p.get("name") or f"Project_{project_id}"
    return f"Project_{project_id}"


@projects_bp.route("/api/projects/<int:project_id>/sheet-previews")
def sheet_previews(project_id):
    """Map page_id → preview_url (if HD screenshot exists) and stackct_url."""
    from project_cache import get_project_plans as _get_plans
    from sheet_preview import build_sheet_preview_payload

    folder_id = request.args.get("folder_id", type=int)
    if folder_id is None:
        return jsonify({"error": "folder_id required"}), 400

    data = _get_plans(project_id, folder_id, force_refresh=False, background=False)
    plans = data.get("plans") or []
    name = (request.args.get("project_name") or "").strip() or _stackct_project_name(project_id)
    previews = build_sheet_preview_payload(
        project_id, name, plans, folder_id=folder_id
    )
    return jsonify({"previews": {str(k): v for k, v in previews.items()}})


@projects_bp.route("/api/projects/<int:project_id>/sheet-preview/<int:page_id>")
def serve_sheet_preview(project_id, page_id):
    """Serve an HD drawing image from a prior takeoff run (JPEG or PNG)."""
    from project_cache import get_project_plans as _get_plans
    from sheet_preview import resolve_screenshot_path

    folder_id = request.args.get("folder_id", type=int)
    if folder_id is None:
        return jsonify({"error": "folder_id required"}), 400

    name = (request.args.get("project_name") or "").strip() or _stackct_project_name(project_id)
    data = _get_plans(project_id, folder_id, force_refresh=False, background=False)
    plans = data.get("plans") or []
    path = resolve_screenshot_path(project_id, page_id, name, plans)
    if not path:
        return jsonify({"error": "Screenshot not found"}), 404
    mime = "image/jpeg" if str(path).lower().endswith((".jpg", ".jpeg")) else "image/png"
    return send_file(path, mimetype=mime, max_age=3600)


@projects_bp.route("/api/projects/<int:project_id>/sync-plans", methods=["POST"])
def sync_plans(project_id):
    """Warm plan list for one folder into SQLite. Requires folder_id in JSON or query."""
    from stackct_sync import sync_project_plans
    force = request.args.get("force") == "1"
    body = request.get_json(silent=True) or {}
    folder_id = body.get("folder_id")
    if folder_id is None:
        folder_id = request.args.get("folder_id", type=int)
    if folder_id is None:
        return jsonify({
            "error": "folder_id required. Call /plan-sets first, then sync a folder.",
        }), 400
    return jsonify(sync_project_plans(project_id, int(folder_id), force=force))


@projects_bp.route("/api/projects/<int:project_id>/plans")
def get_plans(project_id):
    """Legacy plans route — requires folder_id query param."""
    folder_id = request.args.get("folder_id", type=int)
    if folder_id is None:
        return jsonify({
            "error": "folder_id required. Use GET /api/projects/<id>/plan-sets first.",
            "hint": "/api/projects/{}/plan-sets".format(project_id),
        }), 400
    from project_cache import get_project_plans as _get_plans
    force = request.args.get("refresh") == "1"
    background = request.args.get("background") == "1"
    return jsonify(
        _get_plans(
            project_id,
            folder_id,
            force_refresh=force,
            background=background,
        )
    )

