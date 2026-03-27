from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
import pymysql
from database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/directory")
def member_directory(request: Request, db=Depends(get_db)):
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT m.id, m.first_name, m.last_name, m.skills_summary,
                   GROUP_CONCAT(d.name ORDER BY d.name SEPARATOR ', ') AS disciplines
            FROM members m
            LEFT JOIN member_disciplines md ON m.id = md.member_id
            LEFT JOIN disciplines d ON md.discipline_id = d.id
            WHERE m.member_type = 'current'
            GROUP BY m.id
            ORDER BY m.last_name, m.first_name
        """)
        members = cursor.fetchall()
    return templates.TemplateResponse("directory.html", {
        "request": request,
        "members": members
    })
