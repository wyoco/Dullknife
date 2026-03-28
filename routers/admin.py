from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from typing import Optional, List
import bcrypt
import time
import secrets
from database import get_db
from utils.email import send_group_email, send_approval_email, send_rejection_email

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")

LOCKOUT_ATTEMPTS = 5
LOCKOUT_DURATION = 3600
WARNING_AT = 3

def require_admin(request: Request):
    return request.cookies.get("admin_session")

@router.get("/login")
def admin_login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request, "error": None, "warning": None})

@router.post("/login")
def admin_login_submit(
    request: Request,
    db=Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
):
    with db.cursor() as cursor:
        cursor.execute("SELECT id, password_hash, failed_attempts, lockout_until FROM admins WHERE username = %s", (username,))
        admin = cursor.fetchone()

    if not admin:
        return templates.TemplateResponse("admin_login.html", {
            "request": request, "error": "Invalid username or password.", "warning": None
        })

    now = time.time()
    if admin["lockout_until"] and admin["lockout_until"] > now:
        return templates.TemplateResponse("admin_login.html", {
            "request": request, "error": "Account locked for one hour due to failed login attempts.", "warning": None
        })

    if not bcrypt.checkpw(password.encode(), admin["password_hash"].encode()):
        new_attempts = admin["failed_attempts"] + 1
        lockout_until = now + LOCKOUT_DURATION if new_attempts >= LOCKOUT_ATTEMPTS else None
        with db.cursor() as cursor:
            cursor.execute("UPDATE admins SET failed_attempts=%s, lockout_until=%s WHERE id=%s",
                           (new_attempts, lockout_until, admin["id"]))
            db.commit()
        warning = None
        if new_attempts >= WARNING_AT and new_attempts < LOCKOUT_ATTEMPTS:
            remaining = LOCKOUT_ATTEMPTS - new_attempts
            warning = f"WARNING: {new_attempts} failed attempts. {remaining} remaining before lockout."
        error = "Account locked for one hour." if new_attempts >= LOCKOUT_ATTEMPTS else "Invalid username or password."
        return templates.TemplateResponse("admin_login.html", {
            "request": request, "error": error, "warning": warning
        })

    with db.cursor() as cursor:
        cursor.execute("UPDATE admins SET failed_attempts=0, lockout_until=NULL WHERE id=%s", (admin["id"],))
        db.commit()

    resp = RedirectResponse(url="/admin", status_code=303)
    resp.set_cookie("admin_session", str(admin["id"]), httponly=True)
    return resp

@router.get("")
def admin_panel(request: Request):
    if not require_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    return templates.TemplateResponse("admin_panel.html", {"request": request})

@router.get("/logout")
def admin_logout(request: Request):
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie("admin_session")
    return resp

@router.get("/group-email")
def group_email_page(request: Request):
    if not require_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    return templates.TemplateResponse("admin_group_email.html", {"request": request, "sent": False})

@router.post("/group-email")
def group_email_submit(request: Request, db=Depends(get_db), subject: str = Form(...), message: str = Form(...)):
    if not require_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    with db.cursor() as cursor:
        cursor.execute("SELECT email, first_name FROM members WHERE member_type = 'current'")
        members = cursor.fetchall()
    send_group_email(members, subject, message)
    return templates.TemplateResponse("admin_group_email.html", {"request": request, "sent": True})

@router.get("/manage-users")
def manage_users(request: Request, db=Depends(get_db), search: Optional[str] = None):
    if not require_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    with db.cursor() as cursor:
        cursor.execute("SELECT id, username, email, member_type FROM members ORDER BY member_type, username")
        all_users = cursor.fetchall()
    search_results = None
    if search:
        with db.cursor() as cursor:
            like = f"%{search}%"
            cursor.execute("""
                SELECT DISTINCT m.id, m.username, m.email, m.member_type
                FROM members m
                LEFT JOIN member_disciplines md ON m.id = md.member_id
                LEFT JOIN disciplines d ON md.discipline_id = d.id
                WHERE m.first_name LIKE %s OR m.last_name LIKE %s OR m.email LIKE %s
                OR m.skills_summary LIKE %s OR m.admin_notes LIKE %s OR d.name LIKE %s
                ORDER BY m.member_type, m.username
            """, (like, like, like, like, like, like))
            search_results = cursor.fetchall()
    return templates.TemplateResponse("admin_manage_users.html", {
        "request": request, "all_users": all_users, "search": search, "search_results": search_results
    })

@router.get("/edit-user")
def edit_user_redirect(request: Request, member_id: int = 0):
    if not require_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    return RedirectResponse(url=f"/admin/edit-user/{member_id}", status_code=303)

@router.get("/edit-user/{member_id}")
def edit_user_page(member_id: int, request: Request, db=Depends(get_db)):
    if not require_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM members WHERE id = %s", (member_id,))
        member = cursor.fetchone()
    if not member:
        return RedirectResponse(url="/admin/manage-users", status_code=303)
    with db.cursor() as cursor:
        cursor.execute("SELECT discipline_id FROM member_disciplines WHERE member_id = %s", (member_id,))
        member_disc_ids = {row["discipline_id"] for row in cursor.fetchall()}
    with db.cursor() as cursor:
        cursor.execute("SELECT id, name FROM disciplines ORDER BY name")
        all_disciplines = cursor.fetchall()
    disciplines = [{"id": d["id"], "name": d["name"], "checked": d["id"] in member_disc_ids} for d in all_disciplines]
    return templates.TemplateResponse("admin_edit_user.html", {
        "request": request, "member": member, "disciplines": disciplines, "message": None, "error": None
    })

@router.post("/edit-user/{member_id}")
def edit_user_submit(
    member_id: int,
    request: Request,
    db=Depends(get_db),
    action: str = Form(...),
    member_type: str = Form(...),
    username: str = Form(...),
    first_name: str = Form(...),
    middle_name: Optional[str] = Form(None),
    last_name: str = Form(...),
    email: str = Form(...),
    address: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
    zipcode: Optional[str] = Form(None),
    phone_1: Optional[str] = Form(None),
    phone_2: Optional[str] = Form(None),
    skills_summary: Optional[str] = Form(None),
    admin_notes: Optional[str] = Form(None),
    disciplines: Optional[List[str]] = Form(default=None),
):
    if not require_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    if action == "approve":
        member_type = "current"
        with db.cursor() as cursor:
            cursor.execute("SELECT email FROM members WHERE id = %s", (member_id,))
            row = cursor.fetchone()
        send_approval_email(row["email"], row["first_name"], username)
        final_type = "current"
        pw_hash = "temporary"
    elif action == "reject":
        with db.cursor() as cursor:
            cursor.execute("SELECT email FROM members WHERE id = %s", (member_id,))
            row = cursor.fetchone()
        send_rejection_email(row["email"], row["first_name"])
        final_type = "applicant"
        pw_hash = None
    else:
        final_type = member_type
        pw_hash = None

    with db.cursor() as cursor:
        if pw_hash:
            cursor.execute("""
                UPDATE members SET username=%s, first_name=%s, middle_name=%s, last_name=%s,
                email=%s, address=%s, city=%s, state=%s, zipcode=%s, phone_1=%s, phone_2=%s,
                skills_summary=%s, admin_notes=%s, member_type=%s, password_hash=%s WHERE id=%s
            """, (username, first_name, middle_name, last_name, email, address, city, state,
                   zipcode, phone_1, phone_2, skills_summary, admin_notes, final_type, pw_hash, member_id))
        else:
            cursor.execute("""
                UPDATE members SET username=%s, first_name=%s, middle_name=%s, last_name=%s,
                email=%s, address=%s, city=%s, state=%s, zipcode=%s, phone_1=%s, phone_2=%s,
                skills_summary=%s, admin_notes=%s, member_type=%s WHERE id=%s
            """, (username, first_name, middle_name, last_name, email, address, city, state,
                   zipcode, phone_1, phone_2, skills_summary, admin_notes, final_type, member_id))
        cursor.execute("DELETE FROM member_disciplines WHERE member_id=%s", (member_id,))
        if disciplines:
            for disc_id in disciplines:
                cursor.execute("INSERT INTO member_disciplines (member_id, discipline_id) VALUES (%s, %s)",
                               (member_id, int(disc_id)))
        db.commit()

    msg = {"approve": "Member approved. Temporary password set.",
            "reject": "Application rejected.",
            "update": "User record updated."}.get(action, "Updated.")

    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM members WHERE id = %s", (member_id,))
        member = cursor.fetchone()
    with db.cursor() as cursor:
        cursor.execute("SELECT discipline_id FROM member_disciplines WHERE member_id = %s", (member_id,))
        member_disc_ids = {row["discipline_id"] for row in cursor.fetchall()}
    with db.cursor() as cursor:
        cursor.execute("SELECT id, name FROM disciplines ORDER BY name")
        all_disciplines = cursor.fetchall()
    disciplines_out = [{"id": d["id"], "name": d["name"], "checked": d["id"] in member_disc_ids} for d in all_disciplines]

    return templates.TemplateResponse("admin_edit_user.html", {
        "request": request, "member": member, "disciplines": disciplines_out, "message": msg, "error": None
    })
