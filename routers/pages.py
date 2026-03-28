from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
from utils.recaptcha import verify_recaptcha
from utils.email import send_contact_us_notification, send_contact_member_message
from typing import Optional
from database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/about")
def about_page(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})

@router.get("/contact")
def contact_page(request: Request):
    return templates.TemplateResponse("contact.html", {"request": request, "sent": False, "error": None, "form": {}})

@router.post("/contact")
def contact_submit(
    request: Request,
    db=Depends(get_db),
    name: str = Form(...),
    email: str = Form(...),
    phone: Optional[str] = Form(None),
    message: str = Form(...),
    recaptcha_token: Optional[str] = Form(None, alias="g-recaptcha-response"),
):
    if not verify_recaptcha(recaptcha_token or "", request.client.host):
        return templates.TemplateResponse("contact.html", {
            "request": request, "sent": False,
            "error": "reCAPTCHA verification failed. Please try again.",
            "form": {"name": name, "email": email, "phone": phone, "message": message}
        })
    with db.cursor() as cursor:
        cursor.execute("""
            INSERT INTO contact_us_submissions (name, email, phone, message)
            VALUES (%s, %s, %s, %s)
        """, (name, email, phone, message))
        db.commit()

    send_contact_us_notification(name, email, phone, message)

    return templates.TemplateResponse("contact.html", {
        "request": request,
        "sent": True,
        "error": None,
        "form": {}
    })

@router.get("/contact/{member_id}")
def contact_link_page(member_id: int, request: Request, db=Depends(get_db)):
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT id, first_name, last_name FROM members WHERE id = %s AND member_type = 'current'",
            (member_id,)
        )
        member = cursor.fetchone()
    if not member:
        return RedirectResponse(url="/directory", status_code=303)
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT filename FROM member_images WHERE member_id = %s AND is_active = 1",
            (member_id,)
        )
        img = cursor.fetchone()
    with db.cursor() as cursor:
        cursor.execute("SELECT name FROM wyoming_cities ORDER BY name")
        wyoming_cities = [r["name"] for r in cursor.fetchall()]
    with db.cursor() as cursor:
        cursor.execute("SELECT name FROM countries ORDER BY name")
        countries = [r["name"] for r in cursor.fetchall()]
    member_name = f"{member['first_name']} {member['last_name']}"
    member_image = img["filename"] if img else None
    return templates.TemplateResponse("contact_link.html", {
        "request": request, "member_id": member_id, "member_name": member_name,
        "member_image": member_image, "sent": False,
        "wyoming_cities": wyoming_cities, "countries": countries
    })

@router.post("/contact/{member_id}")
def contact_link_submit(
    member_id: int,
    request: Request,
    db=Depends(get_db),
    first_name: str = Form(...),
    last_name: str = Form(...),
    organization: Optional[str] = Form(None),
    email: str = Form(...),
    phone_1: Optional[str] = Form(None),
    phone_2: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
    zipcode: Optional[str] = Form(None),
    country: Optional[str] = Form(None),
    message: str = Form(...),
    recaptcha_token: Optional[str] = Form(None, alias="g-recaptcha-response"),
):
    if not verify_recaptcha(recaptcha_token or "", request.client.host):
        with db.cursor() as cursor:
            cursor.execute("SELECT id, first_name, last_name FROM members WHERE id = %s AND member_type = 'current'", (member_id,))
            member = cursor.fetchone()
        if not member:
            return RedirectResponse(url="/directory", status_code=303)
        with db.cursor() as cursor:
            cursor.execute("SELECT filename FROM member_images WHERE member_id = %s AND is_active = 1", (member_id,))
            img = cursor.fetchone()
        with db.cursor() as cursor:
            cursor.execute("SELECT name FROM wyoming_cities ORDER BY name")
            wyoming_cities = [r["name"] for r in cursor.fetchall()]
        with db.cursor() as cursor:
            cursor.execute("SELECT name FROM countries ORDER BY name")
            countries = [r["name"] for r in cursor.fetchall()]
        return templates.TemplateResponse("contact_link.html", {
            "request": request, "member_id": member_id,
            "member_name": f"{member['first_name']} {member['last_name']}",
            "member_image": img['filename'] if img else None,
            "sent": False, "wyoming_cities": wyoming_cities, "countries": countries,
            "error": "reCAPTCHA verification failed. Please try again."
        })
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT id, first_name, last_name FROM members WHERE id = %s AND member_type = 'current'",
            (member_id,)
        )
        member = cursor.fetchone()
    if not member:
        return RedirectResponse(url="/directory", status_code=303)

    with db.cursor() as cursor:
        cursor.execute("""
            INSERT INTO contact_submissions
            (member_id, visitor_first_name, visitor_last_name, visitor_organization,
             visitor_email, visitor_phone_1, visitor_phone_2, visitor_city, visitor_state, visitor_zipcode, visitor_country, message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (member_id, first_name, last_name, organization, email, phone_1, phone_2, city, state, zipcode, country, message))
        db.commit()

    member_name = f"{member['first_name']} {member['last_name']}"
    with db.cursor() as cursor:
        cursor.execute("SELECT email FROM members WHERE id = %s", (member_id,))
        member_row = cursor.fetchone()
    if member_row:
        send_contact_member_message(
            member_row["email"], member_name,
            first_name, last_name, organization,
            email, phone_1, phone_2,
            city, state, zipcode, country, message
        )

    return templates.TemplateResponse("contact_link.html", {
        "request": request, "member_id": member_id, "member_name": member_name, "sent": True
    })

@router.get("/api/wyoming-zipcodes/{city_name}")
def wyoming_zipcodes_api(city_name: str, db=Depends(get_db)):
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT zipcode FROM wyoming_zipcodes WHERE city_name = %s ORDER BY zipcode",
            (city_name,)
        )
        rows = cursor.fetchall()
    return JSONResponse([r["zipcode"] for r in rows])
