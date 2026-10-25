DSA Planner

A personal planner for DSA interview preparation. Tell it how many days you have and how many hours you can give each day, and it builds a day-by-day plan of free LeetCode problems. You solve on LeetCode; the planner tracks your progress, your revision queue and your streak.

About this project

Most DSA trackers either give you a fixed roadmap or are a plain checklist. This one starts from your real constraint, which is time. A 10-day plan and a 60-day plan should not look alike, and when you fall behind the plan should adjust instead of going stale.

It was inspired by Striver's TUF-style tracking, with one addition: a problem you solved with AI help, or couldn't finish alone, is marked Redo instead of "done", so it comes back for revision.

Time-first planning: the plan is sized to your days, hours per day and level.
Honest tracking: four statuses, so "solved with help" is not counted as "solved".
Free problems only: the catalog contains no premium-only LeetCode problems.
No database: everything is stored as plain JSON files you can read, back up or delete.
Features
Plan generator: input days, hours per day, level (beginner, intermediate, advanced) and weak topics. A live preview shows how many problems fit and how much of the core material is covered. If your time is too short, it recommends days and hours that would cover it.
Curated catalog: 221 free problems across 18 topics, each tagged by pattern and tier (core, important, stretch).
Four statuses: Pending, Solved, Solved with hints, and Redo. Each problem also has a notes field and attempt history.
Revision queue: Redo problems come back the next day, and problems solved with hints after 3 days. Review days are also built into longer plans.
Replan from today: unfinished problems are re-packed into the remaining days. Anything that no longer fits is reported, not silently dropped.
Dashboard: today's problems, plan progress, solo-solve rate, streak, revision queue and topic progress.
Live free-tier check: optionally verifies the catalog against leetcode.com and removes any problem that has become premium. If it can't connect, the bundled list is used.
Export: download a plan as a Markdown checklist or JSON.
Interface: light and dark themes, responsive down to phone width.
Tech stack
Layer	Choice
Backend	Python, FastAPI, Pydantic v2, Uvicorn
HTTP client	httpx (LeetCode free-tier check)
Storage	JSON files with atomic writes (no database)
Frontend	Plain HTML, CSS and ES-module JavaScript, no build step
Tests	pytest with FastAPI TestClient (77 tests)
How it works
Capacity: days × hours per day, with about 15% of each study day kept free for revision.
Selection: problems are chosen by tier (core first), spread across topics, with your weak topics boosted.
Time estimates: each problem gets minutes based on its difficulty and your level. Beginner plans leave out Hard problems.
Packing: problems are packed into days in roadmap order, with an even load across days.
Review days: in longer plans, some days re-solve earlier Redo and Hint problems.
Feasibility: the plan reports core coverage and, if it falls short, searches for the days/hours that would reach it.
Project structure
app/            FastAPI backend (planner, catalog, progress, storage, verification)
frontend/       Web UI (index.html, css/, js/, js/views/)
tests/          pytest suite
data/           Your plans and progress (created at runtime, git-ignored)
run.py          Starts the server
Quick start

Windows (PowerShell):

python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python run.py

macOS / Linux:

python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python run.py

Open http://127.0.0.1:8000. Interactive API docs are at /docs.

To use another port: python run.py --port 8765.

Run the tests
python -m pytest
Your data
File	Contents
data/state.json	Your progress, notes and history
data/plans/<id>.json and .md	Each generated plan, as data and as a checklist
data/verified.json	Cache of the last LeetCode free-tier check

Set the DSA_PLANNER_DATA environment variable to store data in another folder. To back up, copy the data/ folder.

API overview
Method	Endpoint	Purpose
GET	/api/dashboard	Today's view, stats, revision queue
GET	/api/problems	List and filter problems
PUT	/api/problems/{slug}	Set status and notes
POST	/api/plans/preview	Preview a plan without saving
POST	/api/plans	Create a plan
POST	/api/plans/{id}/replan	Re-pack unfinished work
GET	/api/plans/{id}/export	Export as Markdown or JSON
POST	/api/catalog/verify	Run the LeetCode free-tier check
Notes and limitations
The problem list is a curated set (221 problems), not all of LeetCode.
LeetCode has no official public API. The free-tier check uses public endpoints and may stop working if LeetCode changes them. The app then falls back to the bundled list.
This is a single-user local tool with no login.
Ideas for next steps
AI hint ladder: a nudge first, then bigger hints, so fewer problems end up as Redo.
Daily reminders by email or notification.
Company-specific problem sets.
Login and a hosted version for sharing with friends.
