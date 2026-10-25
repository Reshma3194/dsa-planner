"""Start the app:  python run.py   (then open http://127.0.0.1:8000)"""
import argparse

import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run DSA Planner")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes (development)")
    args = parser.parse_args()
    print(f"\n  DSA Planner running at http://{args.host}:{args.port}\n")
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)
