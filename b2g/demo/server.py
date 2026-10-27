"""Local server for the Next.js demo site: serves web/out and plans live requests.

    python -m b2g.demo.server [--port 3000]      ->  open http://localhost:3000

GET  /api/health  whether live requests can run (an API key is set) and which days can be planned.
POST /api/plan    {"date": "YYYY-MM-DD", "request": "..."} -> the same JSON as a pre-run example
                  (S4 plans on the forecast; S1/S4/S5 settled on the actual day). Saved to results/demo/live/.
Only one plan runs at a time; LLM answers are cached, so repeating a request costs nothing.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory

from b2g import REPO_ROOT
from b2g.agents.llm_client import LLMClient, LLMSettings, load_env
from b2g.config import load_config
from b2g.demo import core
from b2g.demo.core import run_example, save_example, slug

SITE_DIR = REPO_ROOT / "web" / "out"
MAX_REQUEST_CHARS = 600


def plannable_days(cfg: dict[str, Any]) -> tuple[date, date]:
    """First and last day a live request may plan: the test period (forecasts exist, never used in training)."""
    first = date.fromisoformat(cfg["forecasting"]["val_end"]) + timedelta(days=1)
    return first, date.fromisoformat(cfg["forecasting"]["test_end"])


def create_app(site_dir: Path = SITE_DIR, client: LLMClient | None = None) -> Flask:
    """The Flask app. `client` replaces the real LLM (tests)."""
    load_env()
    first, last = plannable_days(load_config())
    app = Flask(__name__, static_folder=None)
    busy = threading.Lock()

    @app.get("/api/health")
    def health():
        settings = LLMSettings.from_env()
        return jsonify(live=client is not None or bool(settings.api_key), provider=settings.provider, model=settings.model,
                       first_day=first.isoformat(), last_day=last.isoformat())

    @app.post("/api/plan")
    def plan():
        body = request.get_json(silent=True) or {}
        text = str(body.get("request", "")).strip()
        try:
            day = date.fromisoformat(str(body.get("date", "")))
        except ValueError:
            return jsonify(error="Please choose a valid date."), 400
        if not first <= day <= last:
            return jsonify(error=f"Choose a day between {first:%d %b %Y} and {last:%d %b %Y} (the test period)."), 400
        if not 3 <= len(text) <= MAX_REQUEST_CHARS:
            return jsonify(error=f"Please type a request (up to {MAX_REQUEST_CHARS} characters)."), 400
        if not busy.acquire(blocking=False):
            return jsonify(error="Another request is still being planned. Please wait for it to finish."), 429
        try:
            llm = client or LLMClient(replace(LLMSettings.from_env(), run_id=f"web_{datetime.now():%Y%m%d_%H%M%S}"))
            data = run_example(day.isoformat(), text, title="Your request", client=llm)
        except Exception as e:  # provider down, no network, rate limit after retries ...
            return jsonify(error=f"The AI service could not be reached ({type(e).__name__}: {str(e)[:200]}). "
                                 "The pre-run examples still work."), 502
        finally:
            busy.release()
        (core.DEMO_DIR / "live").mkdir(parents=True, exist_ok=True)     # kept apart from the pre-run examples
        save_example(data, name=f"live/{datetime.now():%Y%m%d_%H%M%S}_{slug(text[:40])}")
        return jsonify(data)

    @app.get("/")
    @app.get("/<path:path>")
    def site(path: str = "index.html"):
        if not (site_dir / "index.html").exists():
            return "The website is not built: run `npm run build` in web/.", 500
        target = site_dir / path
        if target.is_dir():
            path = f"{path.rstrip('/')}/index.html"
        elif not target.exists() and (site_dir / f"{path}.html").exists():
            path = f"{path}.html"
        if not (site_dir / path).exists():
            return send_from_directory(site_dir, "404.html"), 404
        return send_from_directory(site_dir, path)

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=3000)
    port = parser.parse_args().port
    print(f"Smart Home Energy Planner: open http://localhost:{port}  (Ctrl+C to stop)", flush=True)
    create_app().run(host="127.0.0.1", port=port, threaded=True)
    return 0


if __name__ == "__main__":
    if not sys.flags.utf8_mode:   # same Windows encoding guard as b2g.cli
        sys.exit(subprocess.call([sys.executable, "-X", "utf8", "-m", "b2g.demo.server", *sys.argv[1:]]))
    sys.exit(main())
