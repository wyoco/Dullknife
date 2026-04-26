"""Patent attorney questionnaire — standalone login, no membership required."""
import json
from fastapi import APIRouter, Request, Depends, Form, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from database import get_db
from utils.email import send_email

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Hardcoded credentials for questionnaire access
_USERNAME = "attorney"
_PASSWORD = "questions"
_COOKIE_NAME = "questionnaire_session"
_COOKIE_VALUE = "authenticated"


def _is_authenticated(request: Request) -> bool:
    return request.cookies.get(_COOKIE_NAME) == _COOKIE_VALUE


# ── Question definitions ─────────────────────────────────────────────────────
SECTIONS = [
    ("background", "Attorney Background", [
        ("bg_specialization", "What is your primary area of patent specialization?"),
        ("bg_tech_experience", "How many years have you practiced patent law, specifically in software/technology?"),
        ("bg_music_tech", "Do you have experience with music technology, digital rights, or audio-related patents?"),
        ("bg_auction_patents", "Have you worked on patents involving auction systems, bidding algorithms, or marketplace platforms?"),
        ("bg_patent_bar", "Are you registered with the USPTO patent bar? What is your registration number?"),
    ]),
    ("experience", "Relevant Experience", [
        ("exp_similar_patents", "Can you describe similar patents you have prosecuted (software algorithms, marketplace systems)?"),
        ("exp_success_rate", "What is your approximate success rate for utility patent applications in the software space?"),
        ("exp_provisional_conversion", "How many provisional-to-utility conversions have you handled in the last 3 years?"),
        ("exp_references", "Can you provide references from clients with similar technology patents?"),
    ]),
    ("process", "Patent Process & Timeline", [
        ("proc_timeline", "What is the typical timeline from utility filing to patent grant for software patents?"),
        ("proc_provisional_review", "Will you review my existing provisional application (63/996,501) as part of the engagement?"),
        ("proc_claims_strategy", "How do you approach drafting claims for algorithm-based inventions?"),
        ("proc_drawings", "Do you handle patent drawings in-house or use an outside illustrator?"),
        ("proc_office_actions", "How do you typically handle USPTO office actions and rejections?"),
        ("proc_continuation", "Do you recommend filing continuation or divisional applications as a strategy?"),
    ]),
    ("fees", "Fees & Billing", [
        ("fee_utility_filing", "What is your total estimated fee for preparing and filing a utility patent application?"),
        ("fee_structure", "Is your fee structure flat-rate, hourly, or hybrid? Please break down the components."),
        ("fee_office_actions", "What are your fees for responding to office actions?"),
        ("fee_search", "Do you conduct a prior art search, and what does it cost?"),
        ("fee_maintenance", "What are the ongoing maintenance fees after the patent is granted?"),
        ("fee_payment_schedule", "What is your payment schedule — upfront, milestones, or upon filing?"),
    ]),
    ("communication", "Communication & Working Style", [
        ("comm_availability", "How accessible are you for questions during the drafting process?"),
        ("comm_review_rounds", "How many rounds of review/revision are included in your fee?"),
        ("comm_turnaround", "What is your typical turnaround time for draft delivery?"),
        ("comm_point_of_contact", "Will I work directly with you, or will associates/paralegals handle portions?"),
    ]),
    ("strategy", "Patent Strategy", [
        ("strat_claim_breadth", "How would you approach claim breadth for a bidding algorithm with multiple multiplier factors?"),
        ("strat_design_patent", "Do you recommend also filing a design patent for the UI/UX elements?"),
        ("strat_trade_secret", "Which aspects of the algorithm would you recommend keeping as trade secrets vs. patenting?"),
        ("strat_international", "Do you recommend PCT/international filing? If so, which jurisdictions?"),
        ("strat_defensive", "What defensive publication strategies would you recommend?"),
    ]),
    ("entity", "Entity & Ownership", [
        ("ent_small_entity", "Do I qualify for small entity or micro entity status? What are the fee savings?"),
        ("ent_assignment", "How should the patent be assigned — individual, LLC, or corporation?"),
        ("ent_joint_inventors", "If there are joint inventors, how do you handle inventorship determination?"),
    ]),
    ("wyoming", "Wyoming-Specific", [
        ("wy_incentives", "Are there any Wyoming-specific incentives or programs for patent filers?"),
        ("wy_state_law", "Are there Wyoming state law considerations for IP ownership or assignment?"),
        ("wy_local_counsel", "Do you have experience working with Wyoming-based inventors or companies?"),
    ]),
    ("prior_art", "Prior Art & Landscape", [
        ("pa_landscape", "What is your initial impression of the patent landscape for auction/bidding algorithms?"),
        ("pa_alice", "How do you address Alice Corp. / Section 101 challenges for software patents?"),
        ("pa_differentiation", "What makes a bidding algorithm patent defensible in your experience?"),
        ("pa_existing", "Are you aware of any existing patents that might conflict with a multi-factor bid multiplier system?"),
    ]),
    ("risk", "Risk Assessment", [
        ("risk_rejection", "What are the most likely grounds for rejection, and how would you preemptively address them?"),
        ("risk_infringement", "What is your approach to freedom-to-operate analysis?"),
        ("risk_enforcement", "If the patent is granted, how enforceable do you think it would be?"),
        ("risk_timeline_risk", "What risks do you see with the December 2026 filing target?"),
    ]),
    ("closing", "Closing Questions", [
        ("close_why_you", "Why should I choose your firm for this patent?"),
        ("close_next_steps", "What are the immediate next steps if I engage you?"),
        ("close_conflicts", "Do you have any conflicts of interest with music technology or auction platform companies?"),
        ("close_anything_else", "Is there anything else I should know or ask?"),
    ]),
]

ALL_FIELD_KEYS = []
for _section_key, _title, _questions in SECTIONS:
    for _field_key, _question_text in _questions:
        ALL_FIELD_KEYS.append(_field_key)


def _send_questionnaire_email(attorney_name, firm_name, attorney_email,
                               attorney_phone, responses, notes, action_items):
    """Format and email questionnaire results to john@hearit.com."""
    lines = []
    lines.append(f"Patent Attorney Questionnaire — {attorney_name}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Attorney:  {attorney_name}")
    if firm_name:
        lines.append(f"Firm:      {firm_name}")
    if attorney_email:
        lines.append(f"Email:     {attorney_email}")
    if attorney_phone:
        lines.append(f"Phone:     {attorney_phone}")
    lines.append("")

    for section_key, title, questions in SECTIONS:
        section_has_answers = False
        section_lines = []
        section_lines.append(f"--- {title} ---")
        section_lines.append("")
        for field_key, question_text in questions:
            answer = responses.get(field_key, "")
            if answer:
                section_has_answers = True
                section_lines.append(f"Q: {question_text}")
                section_lines.append(f"A: {answer}")
                section_lines.append("")
        if section_has_answers:
            lines.extend(section_lines)

    if notes:
        lines.append("--- Notes ---")
        lines.append("")
        lines.append(notes)
        lines.append("")

    if action_items:
        lines.append("--- Action Items ---")
        lines.append("")
        lines.append(action_items)
        lines.append("")

    lines.append("=" * 60)
    lines.append("View all saved questionnaires:")
    lines.append("https://www.dullknife.com/questionnaire/viewall")
    lines.append("")

    body = "\n".join(lines)
    subject = f"Patent Attorney Questionnaire — {attorney_name}"
    send_email("john@hearit.com", subject, body)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/questionnaire/login")
def questionnaire_login(request: Request):
    if _is_authenticated(request):
        return RedirectResponse(url="/questionnaire", status_code=303)
    next_url = request.query_params.get("next", "")
    return templates.TemplateResponse("questionnaire_login.html", {
        "request": request,
        "error": None,
        "next": next_url,
    })


@router.post("/questionnaire/login")
def questionnaire_login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(default=""),
):
    if username == _USERNAME and password == _PASSWORD:
        dest = next if next.startswith("/questionnaire") else "/questionnaire"
        resp = RedirectResponse(url=dest, status_code=303)
        resp.set_cookie(_COOKIE_NAME, _COOKIE_VALUE, httponly=True, samesite="Lax")
        return resp
    return templates.TemplateResponse("questionnaire_login.html", {
        "request": request,
        "error": "Invalid username or password.",
        "next": next,
    })


@router.get("/questionnaire/logout")
def questionnaire_logout():
    resp = RedirectResponse(url="/questionnaire/login", status_code=303)
    resp.delete_cookie(_COOKIE_NAME)
    return resp


@router.get("/questionnaire")
def questionnaire_form(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/questionnaire/login", status_code=303)
    return templates.TemplateResponse("questionnaire.html", {
        "request": request,
        "sections": SECTIONS,
        "form": {},
        "error": None,
        "success": False,
    })


@router.post("/questionnaire")
async def questionnaire_submit(request: Request, db=Depends(get_db)):
    if not _is_authenticated(request):
        return RedirectResponse(url="/questionnaire/login", status_code=303)

    form_data = await request.form()
    form = {k: v for k, v in form_data.items()}

    attorney_name = form.get("attorney_name", "").strip()
    firm_name = form.get("firm_name", "").strip()
    attorney_email = form.get("attorney_email", "").strip()
    attorney_phone = form.get("attorney_phone", "").strip()
    notes = form.get("notes", "").strip()
    action_items = form.get("action_items", "").strip()

    if not attorney_name:
        return templates.TemplateResponse("questionnaire.html", {
            "request": request,
            "sections": SECTIONS,
            "form": form,
            "error": "Attorney name is required.",
            "success": False,
        })

    responses = {}
    for field_key in ALL_FIELD_KEYS:
        val = form.get(field_key, "").strip()
        if val:
            responses[field_key] = val

    responses_json = json.dumps(responses)

    with db.cursor() as cursor:
        cursor.execute("""
            INSERT INTO patent_questionnaires
                (attorney_name, firm_name, attorney_email,
                 attorney_phone, responses, notes, action_items)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (attorney_name, firm_name or None,
              attorney_email or None, attorney_phone or None,
              responses_json, notes or None,
              action_items or None))
        db.commit()

    _send_questionnaire_email(attorney_name, firm_name, attorney_email,
                               attorney_phone, responses, notes, action_items)

    return templates.TemplateResponse("questionnaire.html", {
        "request": request,
        "sections": SECTIONS,
        "form": {},
        "error": None,
        "success": True,
        "saved_attorney": attorney_name,
    })


@router.get("/questionnaire/viewall")
def questionnaire_results(request: Request, db=Depends(get_db)):
    if not _is_authenticated(request):
        return RedirectResponse(url="/questionnaire/login?next=/questionnaire/viewall", status_code=303)

    with db.cursor() as cursor:
        cursor.execute("""
            SELECT id, attorney_name, firm_name, attorney_email,
                   consultation_date, created_at
            FROM patent_questionnaires
            ORDER BY created_at DESC
        """)
        questionnaires = cursor.fetchall()

    return templates.TemplateResponse("questionnaire_viewall.html", {
        "request": request,
        "questionnaires": questionnaires,
    })


@router.get("/questionnaire/view/{questionnaire_id}")
def questionnaire_view(request: Request, questionnaire_id: int, db=Depends(get_db)):
    if not _is_authenticated(request):
        return RedirectResponse(url=f"/questionnaire/login?next=/questionnaire/view/{questionnaire_id}", status_code=303)

    with db.cursor() as cursor:
        cursor.execute("""
            SELECT * FROM patent_questionnaires
            WHERE id = %s
        """, (questionnaire_id,))
        q = cursor.fetchone()

    if not q:
        return RedirectResponse(url="/questionnaire/viewall", status_code=303)

    responses = q["responses"]
    if isinstance(responses, str):
        responses = json.loads(responses)

    return templates.TemplateResponse("questionnaire_view.html", {
        "request": request,
        "q": q,
        "responses": responses,
        "sections": SECTIONS,
    })
