from fastapi import APIRouter, Request, Depends, Form, Response, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from typing import Optional, List
import bcrypt
from database import get_db
from utils.security import sign_member_session, verify_member_session, get_member_id
from utils.recaptcha import verify_recaptcha, SITE_KEY
import time
import io
import os
from PIL import Image as PilImage

router = APIRouter()
templates = Jinja2Templates(directory="templates")

LOCKOUT_ATTEMPTS = 5
LOCKOUT_DURATION = 3600
WARNING_AT = 3

@router.get("/login")
def login_page(request: Request):
    show_recaptcha = not request.cookies.get("suppress_recaptcha")
    return templates.TemplateResponse("login.html", {"request": request, "show_recaptcha": show_recaptcha})

@router.post("/login")
def login_submit(
    request: Request,
    response: Response,
    db=Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
    suppress_recaptcha: Optional[str] = Form(None),
    recaptcha_token: str = Form(default="", alias="g-recaptcha-response"),
):
    # Verify reCAPTCHA unless suppressed
    if not request.cookies.get("suppress_recaptcha"):
        from utils.security import get_client_ip
        if not verify_recaptcha(recaptcha_token, get_client_ip(request)):
            return templates.TemplateResponse("login.html", {
                "request": request, "show_recaptcha": True,
                "error": "reCAPTCHA verification failed. Please try again."
            })

    with db.cursor() as cursor:
        cursor.execute("""
            SELECT id, username, password_hash, member_type, failed_attempts, lockout_until
            FROM members WHERE username = %s
        """, (username,))
        member = cursor.fetchone()

    if not member:
        return RedirectResponse(url="/login-failed", status_code=303)

    if member["member_type"] == "banned":
        return RedirectResponse(url="/banned", status_code=303)

    now = time.time()
    if member["lockout_until"] and member["lockout_until"] > now:
        return RedirectResponse(url="/account-locked", status_code=303)

    if member["password_hash"] == "temporary":
        if password != "temporary":
            return RedirectResponse(url="/login-failed", status_code=303)
        resp = RedirectResponse(url="/new-member-reset", status_code=303)
        resp.set_cookie("member_id", sign_member_session(member["id"]), httponly=True, secure=True, samesite="Lax")
        return resp

    if not bcrypt.checkpw(password.encode(), member["password_hash"].encode()):
        new_attempts = member["failed_attempts"] + 1
        lockout_until = None
        if new_attempts >= LOCKOUT_ATTEMPTS:
            lockout_until = now + LOCKOUT_DURATION
        with db.cursor() as cursor:
            cursor.execute("""
                UPDATE members SET failed_attempts = %s, lockout_until = %s
                WHERE id = %s
            """, (new_attempts, lockout_until, member["id"]))
            db.commit()
        if new_attempts >= LOCKOUT_ATTEMPTS:
            return RedirectResponse(url="/account-locked", status_code=303)
        return RedirectResponse(url=f"/login-failed?attempts={new_attempts}", status_code=303)

    with db.cursor() as cursor:
        cursor.execute("""
            UPDATE members SET failed_attempts = 0, lockout_until = NULL
            WHERE id = %s
        """, (member["id"],))
        db.commit()

    resp = RedirectResponse(url="/member", status_code=303)
    resp.set_cookie("member_id", sign_member_session(member["id"]), httponly=True, secure=True, samesite="Lax")
    if suppress_recaptcha:
        resp.set_cookie("suppress_recaptcha", "1", httponly=True, secure=True, samesite="Lax", max_age=31536000)
    return resp

@router.get("/login-failed")
def login_failed(request: Request, attempts: int = 0):
    warning = None
    if attempts >= WARNING_AT:
        remaining = LOCKOUT_ATTEMPTS - attempts
        warning = f"WARNING: {attempts} failed login attempts detected. You have {remaining} more attempt(s) before this account is locked."
    return templates.TemplateResponse("login_failed.html", {"request": request, "warning": warning})

MEMBER_IMAGE_DIR = "static/images"

US_STATES = [
    ("AL","Alabama"),("AK","Alaska"),("AZ","Arizona"),("AR","Arkansas"),("CA","California"),
    ("CO","Colorado"),("CT","Connecticut"),("DE","Delaware"),("FL","Florida"),("GA","Georgia"),
    ("HI","Hawaii"),("ID","Idaho"),("IL","Illinois"),("IN","Indiana"),("IA","Iowa"),
    ("KS","Kansas"),("KY","Kentucky"),("LA","Louisiana"),("ME","Maine"),("MD","Maryland"),
    ("MA","Massachusetts"),("MI","Michigan"),("MN","Minnesota"),("MS","Mississippi"),("MO","Missouri"),
    ("MT","Montana"),("NE","Nebraska"),("NV","Nevada"),("NH","New Hampshire"),("NJ","New Jersey"),
    ("NM","New Mexico"),("NY","New York"),("NC","North Carolina"),("ND","North Dakota"),("OH","Ohio"),
    ("OK","Oklahoma"),("OR","Oregon"),("PA","Pennsylvania"),("RI","Rhode Island"),("SC","South Carolina"),
    ("SD","South Dakota"),("TN","Tennessee"),("TX","Texas"),("UT","Utah"),("VT","Vermont"),
    ("VA","Virginia"),("WA","Washington"),("WV","West Virginia"),("WI","Wisconsin"),("WY","Wyoming"),
    ("DC","District of Columbia"),
]

@router.get("/member")
def member_page(request: Request, db=Depends(get_db)):
    member_id = get_member_id(request)
    if not member_id:
        return RedirectResponse(url="/login", status_code=303)

    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM members WHERE id = %s", (member_id,))
        member = cursor.fetchone()

    if not member or member["member_type"] != "current":
        return RedirectResponse(url="/login", status_code=303)

    with db.cursor() as cursor:
        cursor.execute("SELECT discipline_id FROM member_disciplines WHERE member_id = %s", (member_id,))
        member_disc_ids = {row["discipline_id"] for row in cursor.fetchall()}

    with db.cursor() as cursor:
        cursor.execute("SELECT id, name FROM disciplines ORDER BY name")
        all_disciplines = cursor.fetchall()

    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM member_images WHERE member_id = %s ORDER BY is_active DESC, uploaded_at DESC", (member_id,))
        images = cursor.fetchall()

    with db.cursor() as cursor:
        cursor.execute("SELECT name FROM wyoming_cities ORDER BY name")
        wy_cities = [row["name"] for row in cursor.fetchall()]

    disciplines = [{"id": d["id"], "name": d["name"], "checked": d["id"] in member_disc_ids} for d in all_disciplines]

    return templates.TemplateResponse("member.html", {
        "request": request,
        "member": member,
        "disciplines": disciplines,
        "images": images,
        "wy_cities": wy_cities,
        "us_states": US_STATES,
        "upload_error": None,
    })


@router.post("/member/upload-image")
async def upload_image(request: Request, db=Depends(get_db), image: UploadFile = File(...)):
    member_id = get_member_id(request)
    if not member_id:
        return RedirectResponse(url="/login", status_code=303)

    contents = await image.read()
    if len(contents) > 5 * 1024 * 1024:
        return RedirectResponse(url="/member", status_code=303)
    try:
        img = PilImage.open(io.BytesIO(contents))
        if img.size != (400, 400):
            with db.cursor() as cursor:
                cursor.execute("SELECT * FROM member_images WHERE member_id = %s ORDER BY is_active DESC, uploaded_at DESC", (member_id,))
                images = cursor.fetchall()
            with db.cursor() as cursor:
                cursor.execute("SELECT * FROM members WHERE id = %s", (member_id,))
                member = cursor.fetchone()
            with db.cursor() as cursor:
                cursor.execute("SELECT discipline_id FROM member_disciplines WHERE member_id = %s", (member_id,))
                member_disc_ids = {row["discipline_id"] for row in cursor.fetchall()}
            with db.cursor() as cursor:
                cursor.execute("SELECT id, name FROM disciplines ORDER BY name")
                all_disciplines = cursor.fetchall()
            disciplines = [{"id": d["id"], "name": d["name"], "checked": d["id"] in member_disc_ids} for d in all_disciplines]
            return templates.TemplateResponse("member.html", {
                "request": request, "member": member, "disciplines": disciplines,
                "images": images, "upload_error": f"Image must be exactly 400×400 px. Yours is {img.size[0]}×{img.size[1]} px."
            })
    except Exception:
        return RedirectResponse(url="/member", status_code=303)

    ext = os.path.splitext(image.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        return RedirectResponse(url="/member", status_code=303)

    subdir = os.path.join(MEMBER_IMAGE_DIR, str(member_id))
    os.makedirs(subdir, exist_ok=True)
    hex_name = secrets.token_hex(12)
    filename = f"{str(member_id)}/{hex_name}{ext}"
    with open(os.path.join(MEMBER_IMAGE_DIR, filename), "wb") as f:
        f.write(contents)

    with db.cursor() as cursor:
        cursor.execute("INSERT INTO member_images (member_id, filename, is_active) VALUES (%s, %s, 0)", (member_id, filename))
        db.commit()

    return RedirectResponse(url="/member", status_code=303)


@router.post("/member/set-active-image/{image_id}")
def set_active_image(image_id: int, request: Request, db=Depends(get_db)):
    member_id = get_member_id(request)
    if not member_id:
        return RedirectResponse(url="/login", status_code=303)
    with db.cursor() as cursor:
        cursor.execute("UPDATE member_images SET is_active = 0 WHERE member_id = %s", (member_id,))
        cursor.execute("UPDATE member_images SET is_active = 1 WHERE id = %s AND member_id = %s", (image_id, member_id))
        db.commit()
    return RedirectResponse(url="/member", status_code=303)


@router.post("/member/delete-image/{image_id}")
def delete_image(image_id: int, request: Request, db=Depends(get_db)):
    member_id = get_member_id(request)
    if not member_id:
        return RedirectResponse(url="/login", status_code=303)
    with db.cursor() as cursor:
        cursor.execute("SELECT filename FROM member_images WHERE id = %s AND member_id = %s", (image_id, member_id))
        row = cursor.fetchone()
    if row:
        path = os.path.join(MEMBER_IMAGE_DIR, row["filename"])
        if os.path.exists(path):
            os.remove(path)
        with db.cursor() as cursor:
            cursor.execute("DELETE FROM member_images WHERE id = %s AND member_id = %s", (image_id, member_id))
            db.commit()
    return RedirectResponse(url="/member", status_code=303)

@router.post("/member")
def member_update(
    request: Request,
    db=Depends(get_db),
    first_name: str = Form(...),
    middle_name: Optional[str] = Form(None),
    last_name: str = Form(...),
    address: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
    zipcode: Optional[str] = Form(None),
    phone_1: Optional[str] = Form(None),
    phone_2: Optional[str] = Form(None),
    skills_summary: Optional[str] = Form(None),
    disciplines: Optional[List[str]] = Form(default=None),
):
    member_id = get_member_id(request)
    if not member_id:
        return RedirectResponse(url="/login", status_code=303)

    with db.cursor() as cursor:
        cursor.execute("SELECT member_type FROM members WHERE id = %s", (member_id,))
        m = cursor.fetchone()
        if not m or m["member_type"] != "current":
            return RedirectResponse(url="/login", status_code=303)

    with db.cursor() as cursor:
        cursor.execute("""
            UPDATE members SET first_name=%s, middle_name=%s, last_name=%s,
            address=%s, city=%s, state=%s, zipcode=%s, phone_1=%s, phone_2=%s, skills_summary=%s
            WHERE id=%s
        """, (first_name, middle_name, last_name, address, city, state, zipcode, phone_1, phone_2, skills_summary, member_id))

        cursor.execute("DELETE FROM member_disciplines WHERE member_id=%s", (member_id,))
        if disciplines:
            for disc_id in disciplines:
                cursor.execute(
                    "INSERT INTO member_disciplines (member_id, discipline_id) VALUES (%s, %s)",
                    (member_id, int(disc_id))
                )
        db.commit()

    return RedirectResponse(url="/member", status_code=303)

@router.get("/logout")
def logout(request: Request):
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie("member_id")
    resp.delete_cookie("suppress_recaptcha")
    return resp

@router.get("/account-locked")
def account_locked(request: Request):
    return templates.TemplateResponse("account_locked.html", {"request": request})

@router.get("/banned")
def banned_account(request: Request):
    return templates.TemplateResponse("banned.html", {"request": request})

import secrets
import re
import datetime
from utils.email import send_password_reset

def password_strength(password):
    if len(password) < 8:
        return "weak"
    score = sum([
        bool(re.search(r'[A-Z]', password)),
        bool(re.search(r'[a-z]', password)),
        bool(re.search(r'[0-9]', password)),
        bool(re.search(r'[^A-Za-z0-9]', password)),
    ])
    if score <= 1:
        return "weak"
    elif score <= 2:
        return "medium"
    return "hard"

@router.get("/reset-password")
def reset_password_page(request: Request):
    return templates.TemplateResponse("reset_password.html", {"request": request, "sent": False})

@router.post("/reset-password")
def reset_password_submit(request: Request, db=Depends(get_db), email: str = Form(...)):
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM members WHERE email = %s AND member_type = 'current'",
            (email,)
        )
        member = cursor.fetchone()

    if member:
        # Cooldown: skip if a token was created in the last 5 minutes
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM password_reset_tokens WHERE member_id = %s AND created_at > NOW() - INTERVAL 5 MINUTE",
                (member["id"],)
            )
            recent = cursor.fetchone()
        if not recent:
            token = secrets.token_urlsafe(32)
            expires_at = datetime.datetime.now() + datetime.timedelta(minutes=20)
            with db.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO password_reset_tokens (member_id, token, expires_at) VALUES (%s, %s, %s)",
                    (member["id"], token, expires_at)
                )
                db.commit()
            reset_url = f"https://www.dullknife.com/change-password?token={token}"
            send_password_reset(email, reset_url)

    return templates.TemplateResponse("reset_password.html", {"request": request, "sent": True})

@router.get("/change-password")
def change_password_page(request: Request, token: str = "", db=Depends(get_db)):
    if not token:
        return templates.TemplateResponse("change_password.html", {
            "request": request, "error": "Invalid or missing reset token.", "success": False, "token": "", "form_error": None
        })
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM password_reset_tokens WHERE token = %s AND used = 0 AND expires_at > NOW()",
            (token,)
        )
        record = cursor.fetchone()
    if not record:
        return templates.TemplateResponse("change_password.html", {
            "request": request, "error": "This reset link is invalid or has expired.", "success": False, "token": "", "form_error": None
        })
    return templates.TemplateResponse("change_password.html", {
        "request": request, "error": None, "success": False, "token": token, "form_error": None
    })

@router.post("/change-password")
def change_password_submit(
    request: Request,
    db=Depends(get_db),
    token: str = Form(...),
    password: str = Form(...),
    confirm: str = Form(...),
):
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT id, member_id FROM password_reset_tokens WHERE token = %s AND used = 0 AND expires_at > NOW()",
            (token,)
        )
        record = cursor.fetchone()

    if not record:
        return templates.TemplateResponse("change_password.html", {
            "request": request, "error": "This reset link is invalid or has expired.", "success": False, "token": "", "form_error": None
        })

    if password != confirm:
        return templates.TemplateResponse("change_password.html", {
            "request": request, "error": None, "success": False, "token": token,
            "form_error": "Passwords do not match."
        })

    if password_strength(password) == "weak":
        return templates.TemplateResponse("change_password.html", {
            "request": request, "error": None, "success": False, "token": token,
            "form_error": "Password is too weak. Please use at least 8 characters with a mix of uppercase, lowercase, numbers, or symbols."
        })

    # Check password reuse
    with db.cursor() as cursor:
        cursor.execute("SELECT password_hash FROM members WHERE id = %s", (record["member_id"],))
        current = cursor.fetchone()
    if current and current["password_hash"] != "temporary":
        if bcrypt.checkpw(password.encode(), current["password_hash"].encode()):
            return templates.TemplateResponse("change_password.html", {
                "request": request, "error": None, "success": False, "token": token,
                "form_error": "New password must be different from your current password."
            })

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with db.cursor() as cursor:
        cursor.execute("UPDATE members SET password_hash = %s WHERE id = %s", (hashed, record["member_id"]))
        cursor.execute("UPDATE password_reset_tokens SET used = 1 WHERE id = %s", (record["id"],))
        db.commit()

    return templates.TemplateResponse("change_password.html", {
        "request": request, "error": None, "success": True, "token": "", "form_error": None
    })

@router.get("/new-member-reset")
def new_member_reset(request: Request):
    member_id = get_member_id(request)
    if not member_id:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("new_member_reset.html", {"request": request})

@router.get("/new-member-change-password")
def new_member_change_password(request: Request, db=Depends(get_db)):
    member_id = get_member_id(request)
    if not member_id:
        return RedirectResponse(url="/login", status_code=303)
    with db.cursor() as cursor:
        cursor.execute("SELECT id FROM members WHERE id = %s AND password_hash = 'temporary'", (member_id,))
        member = cursor.fetchone()
    if not member:
        return RedirectResponse(url="/member", status_code=303)
    return templates.TemplateResponse("change_password.html", {
        "request": request, "error": None, "success": False, "token": None, "form_error": None, "new_member": True
    })

@router.post("/new-member-change-password")
def new_member_change_password_submit(
    request: Request,
    db=Depends(get_db),
    password: str = Form(...),
    confirm: str = Form(...),
):
    member_id = get_member_id(request)
    if not member_id:
        return RedirectResponse(url="/login", status_code=303)

    if password != confirm:
        return templates.TemplateResponse("change_password.html", {
            "request": request, "error": None, "success": False, "token": None,
            "form_error": "Passwords do not match.", "new_member": True
        })

    if password_strength(password) == "weak":
        return templates.TemplateResponse("change_password.html", {
            "request": request, "error": None, "success": False, "token": None,
            "form_error": "Password is too weak. Please use at least 8 characters with a mix of uppercase, lowercase, numbers, or symbols.",
            "new_member": True
        })

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with db.cursor() as cursor:
        cursor.execute("UPDATE members SET password_hash = %s WHERE id = %s", (hashed, member_id))
        db.commit()

    return templates.TemplateResponse("change_password.html", {
        "request": request, "error": None, "success": True, "token": None, "form_error": None, "new_member": True
    })

@router.get("/new-member-cancel")
def new_member_cancel(request: Request):
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie("member_id")
    return resp


# ── Request Advertising ──────────────────────────────────────────────────────

ADS_IMAGE_DIR = "static/images/ads"

@router.get("/request-ad")
def request_ad_page(request: Request, db=Depends(get_db)):
    member_id = get_member_id(request)
    if not member_id:
        return RedirectResponse(url="/login", status_code=303)
    with db.cursor() as cursor:
        cursor.execute("SELECT id FROM members WHERE id = %s AND member_type = 'current'", (member_id,))
        if not cursor.fetchone():
            return RedirectResponse(url="/login", status_code=303)
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM advertisers WHERE member_id = %s ORDER BY created_at DESC",
            (member_id,)
        )
        submissions = cursor.fetchall()
    return templates.TemplateResponse("request_ad.html", {
        "request": request, "submissions": submissions, "error": None, "success": False
    })


@router.post("/request-ad")
async def request_ad_submit(
    request: Request,
    db=Depends(get_db),
    company_name: str = Form(...),
    website_url: Optional[str] = Form(None),
    image: UploadFile = File(...),
):
    member_id = get_member_id(request)
    if not member_id:
        return RedirectResponse(url="/login", status_code=303)
    with db.cursor() as cursor:
        cursor.execute("SELECT id FROM members WHERE id = %s AND member_type = 'current'", (member_id,))
        if not cursor.fetchone():
            return RedirectResponse(url="/login", status_code=303)

    def render_error(msg):
        with db.cursor() as c:
            c.execute("SELECT * FROM advertisers WHERE member_id = %s ORDER BY created_at DESC", (member_id,))
            subs = c.fetchall()
        return templates.TemplateResponse("request_ad.html", {
            "request": request, "submissions": subs, "error": msg, "success": False
        })

    contents = await image.read()
    if len(contents) > 5 * 1024 * 1024:
        return render_error("File is too large. Maximum size is 5 MB.")
    try:
        img = PilImage.open(io.BytesIO(contents))
        if img.size != (300, 100):
            return render_error(f"Image must be exactly 300×100 px. Yours is {img.size[0]}×{img.size[1]} px.")
    except Exception:
        return render_error("Could not read the image file. Please upload a valid image.")

    ext = os.path.splitext(image.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        return render_error("Unsupported file type. Use .jpg, .jpeg, .png, .gif, or .webp.")

    filename = secrets.token_hex(16) + ext
    os.makedirs(ADS_IMAGE_DIR, exist_ok=True)
    with open(os.path.join(ADS_IMAGE_DIR, filename), "wb") as f:
        f.write(contents)

    with db.cursor() as cursor:
        cursor.execute(
            "INSERT INTO advertisers (company_name, website_url, image_filename, member_id, status, display_order) VALUES (%s, %s, %s, %s, 'pending', 0)",
            (company_name, website_url or None, filename, int(member_id))
        )
        db.commit()

    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM advertisers WHERE member_id = %s ORDER BY created_at DESC", (member_id,))
        submissions = cursor.fetchall()
    return templates.TemplateResponse("request_ad.html", {
        "request": request, "submissions": submissions, "error": None, "success": True
    })
