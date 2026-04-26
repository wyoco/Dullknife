from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from routers import directory, membership, auth, pages, admin, questionnaire, brandbook, trends, tracking
from database import get_db

app = FastAPI()

app.mount("/static/brandbook", StaticFiles(directory="/var/www/pyengines/brandbook"), name="brandbook_static")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(directory.router)
app.include_router(membership.router)
app.include_router(auth.router)
app.include_router(pages.router)
app.include_router(admin.router)
app.include_router(questionnaire.router)
app.include_router(brandbook.router)
app.include_router(trends.router)
app.include_router(tracking.router)

@app.get("/")
def landing_page(request: Request, db=Depends(get_db)):
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT m.id, m.first_name, m.last_name, m.skills_summary,
                   GROUP_CONCAT(d.name ORDER BY d.name SEPARATOR ', ') AS disciplines,
                   mi.filename AS image_filename
            FROM members m
            LEFT JOIN member_disciplines md ON m.id = md.member_id
            LEFT JOIN disciplines d ON md.discipline_id = d.id
            LEFT JOIN member_images mi ON m.id = mi.member_id AND mi.is_active = 1
            WHERE m.member_type = 'current'
            GROUP BY m.id, mi.filename
            ORDER BY RAND()
            LIMIT 5
        """)
        featured = cursor.fetchall()
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM advertisers WHERE status = 'active' ORDER BY display_order, id")
        ads = cursor.fetchall()
    return templates.TemplateResponse("landing.html", {"request": request, "featured": featured, "ads": ads})
