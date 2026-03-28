from fastapi import APIRouter, Request, Depends, Query    
from fastapi.templating import Jinja2Templates
from typing import Optional
from database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/directory")
def member_directory(
    request: Request,
    db=Depends(get_db),
    discipline_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None)
):
    with db.cursor() as cursor:
        cursor.execute("SELECT id, name FROM disciplines ORDER BY name")
        disciplines = cursor.fetchall()

        if discipline_id or search:
            query = """
                SELECT DISTINCT m.id, m.first_name, m.last_name, m.skills_summary,
                       GROUP_CONCAT(d.name ORDER BY d.name SEPARATOR ', ') AS disciplines,
                       mi.filename AS image
                FROM members m
                LEFT JOIN member_disciplines md ON m.id = md.member_id
                LEFT JOIN disciplines d ON md.discipline_id = d.id
                LEFT JOIN member_images mi ON m.id = mi.member_id AND mi.is_active = 1
                WHERE m.member_type = 'current'
            """
            params = []
            if discipline_id:
                query += " AND m.id IN (SELECT member_id FROM member_disciplines WHERE discipline_id = %s)"
                params.append(discipline_id)
            if search:
                query += " AND (m.skills_summary LIKE %s OR m.first_name LIKE %s OR m.last_name LIKE %s)"
                like = f"%{search}%"
                params.extend([like, like, like])
            query += " GROUP BY m.id ORDER BY m.last_name, m.first_name"
            cursor.execute(query, params)
        else:
            cursor.execute("""
                SELECT m.id, m.first_name, m.last_name, m.skills_summary,
                       GROUP_CONCAT(d.name ORDER BY d.name SEPARATOR ', ') AS disciplines,
                       mi.filename AS image
                FROM members m
                LEFT JOIN member_disciplines md ON m.id = md.member_id
                LEFT JOIN disciplines d ON md.discipline_id = d.id
                LEFT JOIN member_images mi ON m.id = mi.member_id AND mi.is_active = 1
                WHERE m.member_type = 'current'
                GROUP BY m.id
                ORDER BY m.last_name, m.first_name
            """)

        members = cursor.fetchall()

    return templates.TemplateResponse("directory.html", {
        "request": request,
        "members": members,
        "disciplines": disciplines,
        "selected_discipline": discipline_id,
        "search": search or ""
    })

