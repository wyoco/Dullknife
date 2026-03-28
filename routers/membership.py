from fastapi import APIRouter, Request, Depends, Form                                                                              
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse                                                                                     
from typing import Optional, List                         
from database import get_db
from utils.recaptcha import verify_recaptcha                                                                                                        
                                                          
router = APIRouter()
templates = Jinja2Templates(directory="templates")

def get_disciplines(db):
    with db.cursor() as cursor:
        cursor.execute("SELECT id, name FROM disciplines ORDER BY name")
        return cursor.fetchall()

@router.get("/apply")
def apply_page(request: Request, db=Depends(get_db)):
    return templates.TemplateResponse("apply.html", {
        "request": request,
        "disciplines": get_disciplines(db),
        "error": None
    })

@router.post("/apply")
def apply_submit(
    request: Request,
    db=Depends(get_db),
    recaptcha_token: Optional[str] = Form(None, alias="g-recaptcha-response"),
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
    discipline_ids: List[int] = Form(...)
):
    with db.cursor() as cursor:
        cursor.execute("SELECT id FROM members WHERE username = %s", (username,))
        if cursor.fetchone():
            return templates.TemplateResponse("apply.html", {
                "request": request,
                "disciplines": get_disciplines(db),
                "error": f"Username '{username}' is already taken. Please choose another."
            })
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
    return RedirectResponse(url="/apply/thankyou", status_code=303)

@router.get("/apply/thankyou")
def apply_thankyou(request: Request):
    return templates.TemplateResponse("apply_thankyou.html", {"request": request})
