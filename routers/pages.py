from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
from typing import Optional
from database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/api/wyoming-zipcodes/{city}")
def wyoming_zipcodes_api(city: str, db=Depends(get_db)):
    with db.cursor() as cursor:
        cursor.execute("SELECT zipcode FROM wyoming_zipcodes WHERE city_name = %s ORDER BY zipcode", (city,))
        zips = [row["zipcode"] for row in cursor.fetchall()]
    return JSONResponse(content=zips)

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
):
    with db.cursor() as cursor:
        cursor.execute("""
            INSERT INTO contact_us_submissions (name, email, phone, message)
            VALUES (%s, %s, %s, %s)
        """, (name, email, phone, message))
        db.commit()

    # TODO: email admin@dullknife.com when SMTP is configured

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
    member_name = f"{member['first_name']} {member['last_name']}"
    return templates.TemplateResponse("contact_link.html", {
        "request": request, "member_id": member_id, "member_name": member_name, "sent": False
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
    message: str = Form(...),
):
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
             visitor_email, visitor_phone_1, visitor_phone_2, message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (member_id, first_name, last_name, organization, email, phone_1, phone_2, message))
        db.commit()

    member_name = f"{member['first_name']} {member['last_name']}"
    print(f"[CONTACT LINK] Message for {member_name} from {first_name} {last_name} <{email}>", flush=True)
    # TODO: email message to member when SMTP is configured

    return templates.TemplateResponse("contact_link.html", {
        "request": request, "member_id": member_id, "member_name": member_name, "sent": True
    })
