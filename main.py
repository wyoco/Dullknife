
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from routers import directory

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
app.include_router(directory.router)

@app.get("/")
def landing_page(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})
