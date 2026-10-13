# Issue Desk — Bug Tracking System

A local bug-tracking workflow built with Python 3.13, SQLite, and the standard library. File issues, set priority and assignee, move issues through new → triaged → in progress → resolved → closed, leave comments, and filter by text, status, priority, or assignee. Reopen an issue by selecting an active status.

## Run

```powershell
python app.py
```

Open <http://127.0.0.1:8003>. The local SQLite database is `bugs.db`; set `BUG_TRACKER_DB` to change its path. Stop with Ctrl+C.

## Tests

```powershell
python -m unittest -v
```

No third-party packages are required. Included bug reports are fictional examples. This app is a local demo and does not provide authentication or production deployment controls.
