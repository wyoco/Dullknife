from fastapi import APIRouter, Request, Depends, Query
from fastapi.templating import Jinja2Templates
from typing import List, Optional
from urllib.parse import quote
from database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")

PAGE_SIZE = 10

@router.get("/directory")
def member_directory(
    request: Request,
    db=Depends(get_db),
    discipline_id: List[int] = Query(default=[]),
    search: Optional[str] = Query(None),
    page: int = Query(1)
):
    page = max(1, page)

    with db.cursor() as cursor:
        cursor.execute("SELECT id, name FROM disciplines ORDER BY name")
        disciplines = cursor.fetchall()

    # Build shared WHERE clause and params
    where = "WHERE m.member_type = 'current'"
    params = []
    if discipline_id:
        placeholders = ",".join(["%s"] * len(discipline_id))
        where += f" AND m.id IN (SELECT member_id FROM member_disciplines WHERE discipline_id IN ({placeholders}))"
        params.extend(discipline_id)
    if search:
        where += " AND (LOWER(m.skills_summary) LIKE %s OR LOWER(m.first_name) LIKE %s OR LOWER(m.last_name) LIKE %s OR LOWER(m.city) LIKE %s)"
        like = f"%{search.lower()}%"
        params.extend([like, like, like, like])

    # Total count
    with db.cursor() as cursor:
        cursor.execute(
            f"SELECT COUNT(DISTINCT m.id) AS total FROM members m {where}",
            params
        )
        total = cursor.fetchone()["total"]

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, total_pages)
    offset = (page - 1) * PAGE_SIZE

    # Paginated results
    with db.cursor() as cursor:
        cursor.execute(f"""
            SELECT m.id, m.first_name, m.last_name, m.skills_summary,
                   GROUP_CONCAT(d.name ORDER BY d.name SEPARATOR ', ') AS disciplines,
                   mi.filename AS image
            FROM members m
            LEFT JOIN member_disciplines md ON m.id = md.member_id
            LEFT JOIN disciplines d ON md.discipline_id = d.id
            LEFT JOIN member_images mi ON m.id = mi.member_id AND mi.is_active = 1
            {where}
            GROUP BY m.id
            ORDER BY m.last_name, m.first_name
            LIMIT %s OFFSET %s
        """, params + [PAGE_SIZE, offset])
        members = cursor.fetchall()

    # Build base query string for pagination links (without page=)
    qparts = []
    for did in discipline_id:
        qparts.append(f"discipline_id={did}")
    if search:
        qparts.append(f"search={quote(search)}")
    query_base = ("&".join(qparts) + "&") if qparts else ""

    return templates.TemplateResponse("directory.html", {
        "request": request,
        "members": members,
        "disciplines": disciplines,
        "selected_disciplines": discipline_id,
        "search": search or "",
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "query_base": query_base,
    })
