"""Settings page and API routes."""
import logging

from flask import Blueprint, jsonify, render_template, request

logger = logging.getLogger(__name__)

settings_bp = Blueprint("settings", __name__)

@settings_bp.route("/settings")
def settings_page():
    """Settings management page."""
    return render_template("settings.html")


@settings_bp.route("/api/settings", methods=["GET"])
def api_get_settings():
    """Return current settings with secrets redacted."""
    from settings import get_settings
    return jsonify(get_settings())


@settings_bp.route("/api/settings", methods=["PUT"])
def api_update_settings():
    """Update settings — partial updates supported."""
    from settings import get_settings, update_settings
    data = request.get_json() or {}
    if not data:
        return jsonify({"error": "No settings provided"}), 400

    success, message, restart_required = update_settings(data)
    if not success:
        return jsonify({"error": message}), 400

    return jsonify({
        "success": True,
        "message": message,
        "restart_required": restart_required,
        "settings": get_settings()
    })

