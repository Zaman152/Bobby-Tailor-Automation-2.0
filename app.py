from bobbytailor.web.app import create_app

app = create_app()
if __name__ == "__main__":
    app.run(debug=True, port=5050, use_reloader=False)
