from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from typing import Optional, List
from database import get_db
from routers.auth import US_STATES
from utils.email import send_email, ADMIN_EMAIL
from utils.recaptcha import verify_recaptcha
from utils.security import get_client_ip

router = APIRouter()
templates = Jinja2Templates(directory="templates")

def get_disciplines(db):
    with db.cursor() as cursor:
        cursor.execute("SELECT id, name FROM disciplines ORDER BY name")
        return cursor.fetchall()

def get_wy_cities(db):
    with db.cursor() as cursor:
        cursor.execute("SELECT name FROM wyoming_cities ORDER BY name")
        return [row["name"] for row in cursor.fetchall()]

@router.get("/apply")
def apply_page(request: Request, db=Depends(get_db)):
    return templates.TemplateResponse("apply.html", {
        "request": request,
        "disciplines": get_disciplines(db),
        "wy_cities": get_wy_cities(db),
        "us_states": US_STATES,
        "error": None
    })

@router.post("/apply")
def apply_submit(
    request: Request,
    db=Depends(get_db),
    username: str = Form(...),
    first_name: str = Form(...),
    middle_name: Optional[str] = Form(None),
    last_name: str = Form(...),
    email: str = Form(...),
    address: str = Form(...),
    city: str = Form(...),
    state: str = Form(...),
    zipcode: str = Form(...),
    phone_1: str = Form(...),
    phone_2: Optional[str] = Form(None),
    skills_summary: str = Form(...),
    discipline_ids: List[int] = Form(default=[]),
    recaptcha_token: str = Form(default="", alias="g-recaptcha-response"),
):
    def render_error(msg):
        return templates.TemplateResponse("apply.html", {
            "request": request,
            "disciplines": get_disciplines(db),
            "wy_cities": get_wy_cities(db),
            "us_states": US_STATES,
            "error": msg
        })

    if not verify_recaptcha(recaptcha_token, get_client_ip(request)):
        return render_error("reCAPTCHA verification failed. Please try again.")

    if not discipline_ids:
        return render_error("Please select at least one discipline.")

    with db.cursor() as cursor:
        cursor.execute("SELECT id FROM members WHERE username = %s", (username,))
        if cursor.fetchone():
            return render_error(f"Username '{username}' is already taken. Please choose another.")
        cursor.execute("SELECT id FROM members WHERE email = %s", (email,))
        if cursor.fetchone():
            return render_error(f"An account with email '{email}' already exists.")
        cursor.execute("""
            INSERT INTO members
             (username, email, password_hash, member_type, first_name, middle_name,
              last_name, address, city, state, zipcode, phone_1, phone_2, skills_summary)
              VALUES (%s, %s, %s, 'applicant', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (username, email, 'temporary', first_name, middle_name,
              last_name, address, city, state, zipcode, phone_1, phone_2, skills_summary))
        member_id = cursor.lastrowid
        for discipline_id in discipline_ids:
            cursor.execute("""
                INSERT INTO member_disciplines (member_id, discipline_id)
                VALUES (%s, %s)
            """, (member_id, discipline_id))
        db.commit()

    # Notify admin
    subject = f"New Membership Application — {first_name} {last_name}"
    body = f"""A new membership application has been submitted.

Name:     {first_name} {last_name}
Username: {username}
Email:    {email}
City:     {city}, {state} {zipcode}
Phone:    {phone_1}

Review and approve at https://www.dullknife.com/admin/manage-users
"""
    send_email(ADMIN_EMAIL, subject, body)

    return RedirectResponse(url="/apply/thankyou", status_code=303)

@router.get("/apply/thankyou")
def apply_thankyou(request: Request):
    return templates.TemplateResponse("apply_thankyou.html", {"request": request})
