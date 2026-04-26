"""
Trends — FastAPI router for site traffic visualization.
Serves at /trends on the dullknife app.
"""

from fastapi import APIRouter, Request, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
import sqlite3
from datetime import datetime, timedelta

router = APIRouter()
templates = Jinja2Templates(directory="templates")

TRENDS_DB = "/var/www/pyengines/trends/trends.db"


def get_trends_db():
    conn = sqlite3.connect(TRENDS_DB)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/trends")
def trends_page(request: Request):
    return templates.TemplateResponse("trends.html", {"request": request})


@router.get("/trends/data")
def trends_data(days: int = Query(7, ge=1, le=365)):
    """Return traffic data as JSON for Chart.js."""
    db = get_trends_db()
    try:
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

        rows = db.execute("""
            SELECT period_start, site, visits
            FROM traffic
            WHERE period_start >= ?
            ORDER BY period_start
        """, (cutoff,)).fetchall()

        # Build datasets keyed by site
        sites = {
            'hearit.com': {'labels': [], 'data': []},
            'dullknife.com': {'labels': [], 'data': []},
            'brandbook': {'labels': [], 'data': []},
        }

        # Get all unique timestamps
        all_times = sorted(set(r['period_start'] for r in rows))

        # Build lookup: (time, site) -> visits
        lookup = {}
        for r in rows:
            lookup[(r['period_start'], r['site'])] = r['visits']

        # Fill in data for each site, using 0 for missing windows
        labels = []
        hearit_data = []
        dullknife_data = []
        brandbook_data = []

        for t in all_times:
            # Format label for display
            dt = datetime.strptime(t, '%Y-%m-%d %H:%M:%S')
            labels.append(dt.strftime('%b %d %H:%M'))

            hearit_data.append(lookup.get((t, 'hearit.com'), 0))
            dullknife_data.append(lookup.get((t, 'dullknife.com'), 0))
            brandbook_data.append(lookup.get((t, 'brandbook'), 0))

        return JSONResponse({
            'labels': labels,
            'datasets': [
                {
                    'label': 'hearit.com',
                    'data': hearit_data,
                    'borderColor': '#e74c3c',
                    'backgroundColor': 'rgba(231, 76, 60, 0.1)',
                },
                {
                    'label': 'dullknife.com',
                    'data': dullknife_data,
                    'borderColor': '#3498db',
                    'backgroundColor': 'rgba(52, 152, 219, 0.1)',
                },
                {
                    'label': 'brandbook',
                    'data': brandbook_data,
                    'borderColor': '#2ecc71',
                    'backgroundColor': 'rgba(46, 204, 113, 0.1)',
                },
            ]
        })
    finally:
        db.close()
