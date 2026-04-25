from flask import Flask, render_template, redirect, url_for

app = Flask(__name__)


@app.route("/")
def index():
    """Login / Signup page."""
    return render_template("auth.html")


@app.route("/feed")
def feed():
    """Main news feed (JWT gating is handled client-side)."""
    return render_template("feed.html")


if __name__ == "__main__":
    app.run(port=5000, debug=True)
