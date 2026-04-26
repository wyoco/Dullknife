"""
Wyoming Brand Book — FastAPI router
Serves at /brandbook on the dullknife app.
"""

from fastapi import APIRouter, Request, Query
from fastapi.templating import Jinja2Templates
import sqlite3
import os
import math

router = APIRouter()
templates = Jinja2Templates(directory="templates")

BRANDBOOK_DB = "/var/www/pyengines/brandbook/brands.db"
BRANDS_PER_PAGE = 20


def get_brand_db():
    conn = sqlite3.connect(BRANDBOOK_DB)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/brandbook")
def brandbook_search(
    request: Request,
    q: str = Query("", description="Search query"),
    state: str = Query("", description="Filter by state"),
    page: int = Query(1, ge=1, description="Page number"),
):
    db = get_brand_db()
    try:
        # Build query
        conditions = []
        params = []

        if q:
            conditions.append("""
                (registrar_name LIKE ? OR brand_number LIKE ?
                 OR registrar_city LIKE ? OR registrar_address LIKE ?
                 OR location_raw LIKE ?)
            """)
            like = f"%{q}%"
            params.extend([like, like, like, like, like])

        if state:
            conditions.append("registrar_state = ?")
            params.append(state.upper())

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        # Count total
        count_sql = f"SELECT COUNT(*) FROM brands {where}"
        total = db.execute(count_sql, params).fetchone()[0]
        total_pages = max(1, math.ceil(total / BRANDS_PER_PAGE))
        page = min(page, total_pages)

        # Fetch page
        offset = (page - 1) * BRANDS_PER_PAGE
        data_sql = f"""
            SELECT * FROM brands {where}
            ORDER BY brand_number
            LIMIT ? OFFSET ?
        """
        brands = db.execute(data_sql, params + [BRANDS_PER_PAGE, offset]).fetchall()

        # Get distinct states for filter dropdown
        states = db.execute(
            "SELECT DISTINCT registrar_state FROM brands WHERE registrar_state != '' ORDER BY registrar_state"
        ).fetchall()

        # Total brands in database
        total_brands = db.execute("SELECT COUNT(*) FROM brands").fetchone()[0]

        return templates.TemplateResponse("brandbook_browse.html", {
            "request": request,
            "brands": brands,
            "q": q,
            "state": state,
            "states": [s[0] for s in states],
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "total_brands": total_brands,
        })
    finally:
        db.close()


@router.get("/brandbook/brand/{brand_number}")
def brandbook_detail(request: Request, brand_number: str):
    db = get_brand_db()
    try:
        brand = db.execute(
            "SELECT * FROM brands WHERE brand_number = ?", (brand_number,)
        ).fetchone()

        if not brand:
            return templates.TemplateResponse("brandbook_browse.html", {
                "request": request,
                "brands": [],
                "q": brand_number,
                "state": "",
                "states": [],
                "page": 1,
                "total_pages": 1,
                "total": 0,
                "total_brands": 0,
                "error": f"Brand {brand_number} not found.",
            })

        return templates.TemplateResponse("brandbook_detail.html", {
            "request": request,
            "brand": brand,
        })
    finally:
        db.close()
