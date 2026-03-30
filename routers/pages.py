from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse, Response
from typing import Optional
from database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")

BASE_URL = "https://www.dullknife.com"

STATIC_URLS = [
    {"loc": f"{BASE_URL}/",          "changefreq": "daily",   "priority": "1.0"},
    {"loc": f"{BASE_URL}/directory", "changefreq": "daily",   "priority": "0.9"},
    {"loc": f"{BASE_URL}/apply",     "changefreq": "monthly", "priority": "0.8"},
    {"loc": f"{BASE_URL}/about",     "changefreq": "monthly", "priority": "0.7"},
    {"loc": f"{BASE_URL}/contact",   "changefreq": "monthly", "priority": "0.6"},
]

@router.get("/sitemap.xml")
def sitemap(db=Depends(get_db)):
    urls = list(STATIC_URLS)
    with db.cursor() as cursor:
        cursor.execute("SELECT id FROM members WHERE member_type = 'current' ORDER BY id")
        for row in cursor.fetchall():
            urls.append({
                "loc": f"{BASE_URL}/profile/{row['id']}",
                "changefreq": "weekly",
                "priority": "0.7",
            })
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{u['loc']}</loc>")
        lines.append(f"    <changefreq>{u['changefreq']}</changefreq>")
        lines.append(f"    <priority>{u['priority']}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return Response(content="\n".join(lines), media_type="application/xml")

@router.get("/robots.txt")
def robots_txt():
    content = f"User-agent: *\nDisallow: /admin/\nDisallow: /member\nSitemap: {BASE_URL}/sitemap.xml\n"
    return Response(content=content, media_type="text/plain")

@router.get("/api/check-username")
def check_username(username: str = "", db=Depends(get_db)):
    if not username:
        return JSONResponse(content={"available": True})
    with db.cursor() as cursor:
        cursor.execute("SELECT id FROM members WHERE username = %s", (username,))
        taken = cursor.fetchone() is not None
    return JSONResponse(content={"available": not taken})

@router.get("/api/check-email")
def check_email(email: str = "", db=Depends(get_db)):
    if not email:
        return JSONResponse(content={"available": True})
    with db.cursor() as cursor:
        cursor.execute("SELECT id FROM members WHERE email = %s", (email,))
        taken = cursor.fetchone() is not None
    return JSONResponse(content={"available": not taken})

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
