"""
Tracking — Contractor & Employee Hour Tracking by Job Number
FastAPI router served at /tracking on dullknife.com
"""

from fastapi import APIRouter, Request, Form, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
import sqlite3
import os

router = APIRouter()
templates = Jinja2Templates(directory="templates")

DB_FILE = "/var/www/pyengines/tracking/tracking.db"


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            display_name TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_number TEXT NOT NULL,
            identity_name TEXT NOT NULL,
            start_date TEXT NOT NULL,
            is_completed INTEGER DEFAULT 0,
            created_by INTEGER REFERENCES users(id),
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS time_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            work_date TEXT NOT NULL,
            hours REAL NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_created_by ON jobs(created_by);
        CREATE INDEX IF NOT EXISTS idx_time_entries_job ON time_entries(job_id);
    """)
    # Default user
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, display_name, is_admin) VALUES (?, ?, ?, ?)",
        ('Rob', 'Arthur', 'Rob', 1)
    )
    conn.commit()
    conn.close()


# Initialize on import
init_db()


def get_user(request: Request):
    """Get logged-in user from cookie."""
    user_id = request.cookies.get("tracking_user")
    if not user_id:
        return None
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    db.close()
    return user


# --- Auth ---

@router.get("/tracking/login")
def tracking_login(request: Request, error: str = ""):
    return templates.TemplateResponse("tracking_login.html", {"request": request, "error": error})


@router.post("/tracking/login")
def tracking_login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE LOWER(username) = LOWER(?) AND LOWER(password) = LOWER(?)",
        (username, password)
    ).fetchone()
    db.close()

    if not user:
        return templates.TemplateResponse("tracking_login.html", {
            "request": request,
            "error": "Invalid username or password."
        })

    response = RedirectResponse("/tracking", status_code=303)
    response.set_cookie("tracking_user", str(user["id"]), httponly=True)
    return response


@router.get("/tracking/logout")
def tracking_logout():
    response = RedirectResponse("/tracking/login", status_code=303)
    response.delete_cookie("tracking_user")
    return response


# --- Landing / Overview ---

@router.get("/tracking")
def tracking_overview(request: Request):
    user = get_user(request)
    if not user:
        return RedirectResponse("/tracking/login", status_code=303)

    db = get_db()
    jobs = db.execute("""
        SELECT j.*,
               COALESCE(SUM(t.hours), 0) as total_hours,
               COUNT(t.id) as entry_count
        FROM jobs j
        LEFT JOIN time_entries t ON j.id = t.job_id
        GROUP BY j.id
        ORDER BY j.is_completed ASC, j.created_at DESC
    """).fetchall()
    db.close()

    return templates.TemplateResponse("tracking_overview.html", {
        "request": request,
        "user": user,
        "jobs": jobs,
    })


# --- New Job ---

@router.get("/tracking/new")
def tracking_new_job(request: Request):
    user = get_user(request)
    if not user:
        return RedirectResponse("/tracking/login", status_code=303)

    return templates.TemplateResponse("tracking_new_job.html", {
        "request": request,
        "user": user,
    })


@router.post("/tracking/new")
def tracking_new_job_post(
    request: Request,
    job_number: str = Form(...),
    start_date: str = Form(...),
    identity_name: str = Form(...),
):
    user = get_user(request)
    if not user:
        return RedirectResponse("/tracking/login", status_code=303)

    db = get_db()
    db.execute(
        "INSERT INTO jobs (job_number, identity_name, start_date, created_by) VALUES (?, ?, ?, ?)",
        (job_number.strip(), identity_name.strip(), start_date, user["id"])
    )
    db.commit()
    db.close()

    return RedirectResponse("/tracking", status_code=303)


# --- Job Detail ---

@router.get("/tracking/job/{job_id}")
def tracking_job_detail(request: Request, job_id: int):
    user = get_user(request)
    if not user:
        return RedirectResponse("/tracking/login", status_code=303)

    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        db.close()
        return RedirectResponse("/tracking", status_code=303)

    entries = db.execute(
        "SELECT * FROM time_entries WHERE job_id = ? ORDER BY work_date",
        (job_id,)
    ).fetchall()

    total_hours = sum(e["hours"] for e in entries)
    db.close()

    return templates.TemplateResponse("tracking_job_detail.html", {
        "request": request,
        "user": user,
        "job": job,
        "entries": entries,
        "total_hours": total_hours,
    })


@router.post("/tracking/job/{job_id}/save")
def tracking_job_save(request: Request, job_id: int):
    """Save all time entries (updates + new row)."""
    user = get_user(request)
    if not user:
        return RedirectResponse("/tracking/login", status_code=303)

    import asyncio
    # Need to read form data async
    return RedirectResponse(f"/tracking/job/{job_id}", status_code=303)


@router.post("/tracking/job/{job_id}/add-entry")
async def tracking_add_entry(request: Request, job_id: int):
    user = get_user(request)
    if not user:
        return RedirectResponse("/tracking/login", status_code=303)

    form = await request.form()
    work_date = form.get("new_date", "").strip()
    hours = form.get("new_hours", "").strip()

    if work_date and hours:
        try:
            hours_val = float(hours)
            db = get_db()
            db.execute(
                "INSERT INTO time_entries (job_id, work_date, hours) VALUES (?, ?, ?)",
                (job_id, work_date, hours_val)
            )
            db.commit()
            db.close()
        except ValueError:
            pass

    return RedirectResponse(f"/tracking/job/{job_id}", status_code=303)


@router.post("/tracking/job/{job_id}/update-entry/{entry_id}")
async def tracking_update_entry(request: Request, job_id: int, entry_id: int):
    user = get_user(request)
    if not user:
        return RedirectResponse("/tracking/login", status_code=303)

    form = await request.form()
    work_date = form.get("work_date", "").strip()
    hours = form.get("hours", "").strip()

    if work_date and hours:
        try:
            hours_val = float(hours)
            db = get_db()
            db.execute(
                "UPDATE time_entries SET work_date = ?, hours = ? WHERE id = ? AND job_id = ?",
                (work_date, hours_val, entry_id, job_id)
            )
            db.commit()
            db.close()
        except ValueError:
            pass

    return RedirectResponse(f"/tracking/job/{job_id}", status_code=303)


@router.post("/tracking/job/{job_id}/delete-entry/{entry_id}")
def tracking_delete_entry(request: Request, job_id: int, entry_id: int):
    user = get_user(request)
    if not user:
        return RedirectResponse("/tracking/login", status_code=303)

    db = get_db()
    db.execute("DELETE FROM time_entries WHERE id = ? AND job_id = ?", (entry_id, job_id))
    db.commit()
    db.close()

    return RedirectResponse(f"/tracking/job/{job_id}", status_code=303)


# --- Job Actions ---

@router.post("/tracking/job/{job_id}/toggle-completed")
def tracking_toggle_completed(request: Request, job_id: int):
    user = get_user(request)
    if not user:
        return RedirectResponse("/tracking/login", status_code=303)

    db = get_db()
    db.execute("UPDATE jobs SET is_completed = NOT is_completed WHERE id = ?", (job_id,))
    db.commit()
    db.close()

    return RedirectResponse(f"/tracking/job/{job_id}", status_code=303)


@router.post("/tracking/job/{job_id}/email-report")
async def tracking_email_report(request: Request, job_id: int):
    """Email a job report to a recipient."""
    user = get_user(request)
    if not user:
        return RedirectResponse("/tracking/login", status_code=303)

    form = await request.form()
    recipient = form.get("recipient", "").strip()

    if not recipient:
        return RedirectResponse(f"/tracking/job/{job_id}", status_code=303)

    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    entries = db.execute(
        "SELECT * FROM time_entries WHERE job_id = ? ORDER BY work_date", (job_id,)
    ).fetchall()
    total_hours = sum(e["hours"] for e in entries)
    db.close()

    if not job:
        return RedirectResponse("/tracking", status_code=303)

    # Build report
    status = "Completed" if job["is_completed"] else "Active"
    lines = [
        "Job Report",
        "=" * 58,
        "",
        f"Job Number:    {job['job_number']}",
        f"Name:          {job['identity_name']}",
        f"Start Date:    {job['start_date']}",
        f"Status:        {status}",
        "",
        "-" * 58,
        f"{'Date':<20} {'Hours':>8}",
        "-" * 58,
    ]
    for entry in entries:
        lines.append(f"{entry['work_date']:<20} {entry['hours']:>8.1f}")
    lines.append("-" * 58)
    lines.append(f"{'Total Hours:':<20} {total_hours:>8.1f}")
    lines.append("=" * 58)

    body = "\n".join(lines)

    # Send email via localhost Postfix
    import smtplib
    from email.mime.text import MIMEText

    msg = MIMEText(body)
    msg["Subject"] = f"Job Report — {job['job_number']} — {job['identity_name']}"
    msg["From"] = "tracking@dullknife.com"
    msg["To"] = recipient

    try:
        with smtplib.SMTP("localhost", 25) as server:
            server.sendmail("tracking@dullknife.com", recipient, msg.as_string())
    except Exception as e:
        print(f"Email failed: {e}")

    return RedirectResponse(f"/tracking/job/{job_id}", status_code=303)


@router.post("/tracking/job/{job_id}/delete")
def tracking_delete_job(request: Request, job_id: int):
    user = get_user(request)
    if not user:
        return RedirectResponse("/tracking/login", status_code=303)

    db = get_db()
    db.execute("DELETE FROM time_entries WHERE job_id = ?", (job_id,))
    db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    db.commit()
    db.close()

    return RedirectResponse("/tracking", status_code=303)
