import os

from bobbytailor.web.app import create_app

app = create_app()
if __name__ == "__main__":
    # debug=True serves the Werkzeug interactive console, which executes
    # arbitrary Python from the browser behind a PIN. Not reachable under the
    # documented `gunicorn app:app` command — that imports this module without
    # running __main__ — but `python3 app.py` is itself a documented entry
    # point, and an operator who ssh's in and runs it while nginx proxies port
    # 5050 has just put that console on the public internet.
    app.run(
        debug=os.getenv("FLASK_ENV") == "development",
        port=5050,
        use_reloader=False,
    )
