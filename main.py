import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from bson import ObjectId

from database import db, create_document, get_documents

app = FastAPI(title="LearnHub API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# Helpers
# -----------------------------

def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


def now_utc():
    return datetime.now(timezone.utc)


# Simple token store (tokens collection) for demo auth
TOKEN_TTL_HOURS = 48

def require_auth(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    tok = db["tokens"].find_one({"token": token})
    if not tok:
        raise HTTPException(status_code=401, detail="Invalid token")
    if tok.get("expires_at") and tok["expires_at"] < now_utc():
        raise HTTPException(status_code=401, detail="Token expired")
    user = db["user"].find_one({"_id": tok["user_id"]})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    user["id"] = str(user.pop("_id"))
    return user


def hash_password(password: str) -> str:
    # Lightweight hash for demo (not for production): salted sha256
    import hashlib, secrets
    salt = secrets.token_hex(8)
    digest = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    import hashlib
    try:
        salt, digest = password_hash.split("$")
    except ValueError:
        return False
    return hashlib.sha256((salt + password).encode()).hexdigest() == digest


# -----------------------------
# Models
# -----------------------------
class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChatRequest(BaseModel):
    course_id: Optional[str] = None
    user_id: Optional[str] = None
    message: str


class ProgressUpdate(BaseModel):
    lecture_id: str
    watched_seconds: int
    completed: bool = False
    bookmark: Optional[int] = None


class QuizSubmission(BaseModel):
    course_id: str
    quiz_id: str
    answers: Dict[str, Any]


class DiscussionCreate(BaseModel):
    course_id: str
    title: str
    content: str
    tags: List[str] = Field(default_factory=list)


class MessageCreate(BaseModel):
    discussion_id: str
    content: str


# -----------------------------
# Root & Health
# -----------------------------
@app.get("/")
def read_root():
    return {"message": "LearnHub API is running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()[:10]
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# -----------------------------
# Auth
# -----------------------------
@app.post("/auth/register")
def register(req: RegisterRequest):
    existing = db["user"].find_one({"email": req.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_doc = {
        "name": req.name,
        "email": req.email,
        "password_hash": hash_password(req.password),
        "interests": [],
        "roles": ["user"],
        "is_active": True,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    res = db["user"].insert_one(user_doc)
    # auto sign-in
    token = str(uuid4())
    db["tokens"].insert_one({
        "token": token,
        "user_id": res.inserted_id,
        "created_at": now_utc(),
        "expires_at": now_utc() + timedelta(hours=TOKEN_TTL_HOURS)
    })
    return {"token": token, "user": {"id": str(res.inserted_id), "name": req.name, "email": req.email}}


@app.post("/auth/login")
def login(req: LoginRequest):
    user = db["user"].find_one({"email": req.email})
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = str(uuid4())
    db["tokens"].insert_one({
        "token": token,
        "user_id": user["_id"],
        "created_at": now_utc(),
        "expires_at": now_utc() + timedelta(hours=TOKEN_TTL_HOURS)
    })
    return {"token": token, "user": {"id": str(user["_id"]), "name": user.get("name"), "email": user.get("email")}}


@app.get("/auth/me")
def me(user=Depends(require_auth)):
    return {"user": user}


# -----------------------------
# Courses & Content
# -----------------------------

def seed_course_if_empty():
    if db["course"].count_documents({}) == 0:
        sample_course = {
            "title": "Modern React Foundations",
            "description": "Build production-grade UIs with hooks, context, and performance patterns.",
            "category": "Web Development",
            "skills": ["React", "JavaScript", "UI", "Hooks"],
            "thumbnail_url": "https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?q=80&w=1200&auto=format&fit=crop",
            "level": "Beginner",
            "duration_minutes": 120,
            "playlist": [
                {"id": "lec1", "title": "Welcome & Setup", "url": "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4", "duration": 300, "chapter": "Intro"},
                {"id": "lec2", "title": "Components & Props", "url": "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4", "duration": 600, "chapter": "Core"},
                {"id": "lec3", "title": "State & Effects", "url": "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4", "duration": 900, "chapter": "Core"}
            ],
            "quizzes": [
                {"id": "q1", "title": "Basics Quiz", "questions": [
                    {"id": "q1-1", "question": "What hook manages state?", "choices": ["useState", "useEffect", "useMemo"], "answer": 0},
                    {"id": "q1-2", "question": "What renders UI?", "choices": ["Components", "Reducers", "Routers"], "answer": 0}
                ]}
            ],
            "certificate_threshold": 70,
            "created_at": now_utc(),
            "updated_at": now_utc()
        }
        db["course"].insert_one(sample_course)


@app.get("/courses")
def list_courses():
    seed_course_if_empty()
    items = []
    for c in db["course"].find({}).limit(50):
        c["id"] = str(c.pop("_id"))
        items.append(c)
    return {"items": items}


@app.get("/courses/{course_id}")
def get_course(course_id: str):
    c = db["course"].find_one({"_id": oid(course_id)})
    if not c:
        raise HTTPException(status_code=404, detail="Course not found")
    c["id"] = str(c.pop("_id"))
    return c


@app.get("/courses/{course_id}/progress")
def get_course_progress(course_id: str, user=Depends(require_auth)):
    prog = db["courseprogress"].find_one({"user_id": user["id"], "course_id": course_id})
    if not prog:
        prog = {"user_id": user["id"], "course_id": course_id, "completed_lecture_ids": [], "percentage": 0.0}
    # lecture-level progress list
    lectures = list(db["lectureprogress"].find({"user_id": user["id"], "course_id": course_id}))
    for lp in lectures:
        lp["id"] = str(lp.pop("_id"))
    return {"course": course_id, "course_progress": prog, "lectures": lectures}


@app.patch("/courses/{course_id}/progress")
def update_lecture_progress(course_id: str, update: ProgressUpdate, user=Depends(require_auth)):
    # upsert lecture progress
    db["lectureprogress"].update_one(
        {"user_id": user["id"], "course_id": course_id, "lecture_id": update.lecture_id},
        {"$set": {"watched_seconds": update.watched_seconds, "completed": update.completed, "updated_at": now_utc()},
         "$setOnInsert": {"created_at": now_utc()}},
        upsert=True
    )
    # compute course progress
    course = db["course"].find_one({"_id": oid(course_id)})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    total_lectures = len(course.get("playlist", [])) or 1
    completed_ids = [lp.get("lecture_id") for lp in db["lectureprogress"].find({"user_id": user["id"], "course_id": course_id, "completed": True})]
    percent = round(len(completed_ids) * 100.0 / total_lectures, 2)
    db["courseprogress"].update_one(
        {"user_id": user["id"], "course_id": course_id},
        {"$set": {"completed_lecture_ids": completed_ids, "percentage": percent, "updated_at": now_utc()},
         "$setOnInsert": {"created_at": now_utc()}},
        upsert=True
    )
    return {"ok": True, "percentage": percent, "completed": completed_ids}


# -----------------------------
# Quizzes & Certificates
# -----------------------------
@app.post("/quizzes/submit")
def submit_quiz(sub: QuizSubmission, user=Depends(require_auth)):
    course = db["course"].find_one({"_id": oid(sub.course_id)})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    quiz = next((q for q in course.get("quizzes", []) if q.get("id") == sub.quiz_id), None)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    total = len(quiz.get("questions", [])) or 1
    correct = 0
    for q in quiz["questions"]:
        ans_index = sub.answers.get(q["id"])  # expected index of choice
        if isinstance(ans_index, int) and ans_index == q.get("answer"):
            correct += 1
    score = round(correct * 100.0 / total, 2)
    passed = score >= course.get("certificate_threshold", 70)
    res = db["quizresult"].insert_one({
        "user_id": user["id"], "course_id": sub.course_id, "quiz_id": sub.quiz_id,
        "score_percent": score, "answers": sub.answers, "passed": passed,
        "created_at": now_utc(), "updated_at": now_utc()
    })
    certificate = None
    if passed:
        code = f"LH-{uuid4().hex[:8].upper()}"
        cert_doc = {
            "user_id": user["id"], "course_id": sub.course_id, "quiz_id": sub.quiz_id,
            "score_percent": score, "certificate_code": code,
            "issued_at": now_utc(), "created_at": now_utc(), "updated_at": now_utc()
        }
        cert_res = db["certificate"].insert_one(cert_doc)
        certificate = {"id": str(cert_res.inserted_id), **{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in cert_doc.items()}}
    return {"result_id": str(res.inserted_id), "score": score, "passed": passed, "certificate": certificate}


# -----------------------------
# Discussions
# -----------------------------
@app.get("/discussions")
def list_discussions(course_id: Optional[str] = None):
    query = {"course_id": course_id} if course_id else {}
    items = []
    for d in db["discussion"].find(query).sort("created_at", -1).limit(50):
        d["id"] = str(d.pop("_id"))
        items.append(d)
    return {"items": items}


@app.post("/discussions")
def create_discussion(req: DiscussionCreate, user=Depends(require_auth)):
    doc = {
        "course_id": req.course_id, "user_id": user["id"],
        "title": req.title, "content": req.content, "tags": req.tags,
        "created_at": now_utc(), "updated_at": now_utc()
    }
    res = db["discussion"].insert_one(doc)
    return {"id": str(res.inserted_id), **doc}


@app.get("/discussions/{discussion_id}/messages")
def list_messages(discussion_id: str):
    items = []
    for m in db["message"].find({"discussion_id": discussion_id}).sort("created_at", 1):
        m["id"] = str(m.pop("_id"))
        items.append(m)
    return {"items": items}


@app.post("/discussions/{discussion_id}/messages")
def create_message(discussion_id: str, req: MessageCreate, user=Depends(require_auth)):
    doc = {"discussion_id": discussion_id, "user_id": user["id"], "content": req.content, "created_at": now_utc()}
    res = db["message"].insert_one(doc)
    return {"id": str(res.inserted_id), **doc}


# -----------------------------
# Chatbot (Rule-based demo)
# -----------------------------
@app.post("/chatbot")
def chatbot(req: ChatRequest, user=Depends(require_auth)):
    prompt = req.message.strip().lower()
    tips = []
    if "state" in prompt or "use state" in prompt:
        tips.append("Remember: useState returns [value, setValue]. Update state immutably.")
    if "effect" in prompt:
        tips.append("useEffect runs after render. Add dependencies to control when it runs.")
    if "performance" in prompt or "optimize" in prompt:
        tips.append("Consider useMemo/useCallback to memoize expensive calculations and handlers.")
    if not tips:
        tips.append("Focus on one concept at a time, review the lecture notes, and try a small hands-on example.")
    response = " ".join(tips)

    # add contextual references if course provided
    refs: List[Dict[str, Any]] = []
    if req.course_id:
        c = db["course"].find_one({"_id": oid(req.course_id)})
        if c:
            for lec in c.get("playlist", [])[:2]:
                refs.append({"lecture_id": lec.get("id"), "title": lec.get("title"), "suggested_timestamp": 60})

    msg_doc = {
        "user_id": user["id"], "course_id": req.course_id, "prompt": req.message,
        "response": response, "refs": refs, "created_at": now_utc()
    }
    db["chatlog"].insert_one(msg_doc)
    return {"reply": response, "references": refs}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
