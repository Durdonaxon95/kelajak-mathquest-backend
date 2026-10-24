import os
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./kelajak_mathquest.db")
engine_args = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()

app = FastAPI(title="Kelajak Markazi Math Quest API", version="2.0.0")

# GitHub Pages saytiga brauzerdan API chaqirishga ruxsat beradi.
# Ishlab chiqarishdan oldin faqat o'zingizning aniq domenlaringizni qoldiring.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://durdonaxon95.github.io",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(80), nullable=False)
    grade = Column(Integer, nullable=False)

class Score(Base):
    __tablename__ = "scores"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(100), index=True, nullable=False)
    points = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)

Base.metadata.create_all(bind=engine)

class StudentIn(BaseModel):
    telegram_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=80)
    grade: int = Field(ge=1, le=4)

class AnswerIn(BaseModel):
    telegram_id: str = Field(min_length=1, max_length=100)
    correct: bool

def week_start_utc():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

@app.get("/")
def root():
    return {"name": "Kelajak Markazi Math Quest API", "status": "ok", "docs": "/docs"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/register")
def register(data: StudentIn):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Ism bo'sh bo'lmasin")
    db = SessionLocal()
    try:
        student = db.query(Student).filter_by(telegram_id=data.telegram_id).first()
        if student:
            student.name = name
            student.grade = data.grade
        else:
            student = Student(telegram_id=data.telegram_id, name=name, grade=data.grade)
            db.add(student)
        db.commit()
        return {"ok": True, "name": student.name, "grade": student.grade}
    finally:
        db.close()

@app.post("/api/answer")
def answer(data: AnswerIn):
    # SINOV UCHUN: client "correct" qiymatini yuboradi, shu sabab bu endpoint
    # ommaviy foydalanish uchun xavfsiz emas. Ishga tushirishdan oldin server
    # savol va javobni o'zi tekshirishi hamda Telegram initData ni tasdiqlashi shart.
    db = SessionLocal()
    try:
        student = db.query(Student).filter_by(telegram_id=data.telegram_id).first()
        if not student:
            raise HTTPException(status_code=404, detail="Avval ro'yxatdan o'ting")
        points = 10 if data.correct else 0
        if points:
            db.add(Score(telegram_id=data.telegram_id, points=points))
            db.commit()
        return {"ok": True, "added_points": points}
    finally:
        db.close()

@app.get("/api/leaderboard")
def leaderboard():
    db = SessionLocal()
    try:
        monday = week_start_utc()
        rows = (
            db.query(Student.name, Student.grade, func.sum(Score.points).label("points"))
            .join(Score, Student.telegram_id == Score.telegram_id)
            .filter(Score.created_at >= monday)
            .group_by(Student.telegram_id, Student.name, Student.grade)
            .order_by(func.sum(Score.points).desc(), Student.name.asc())
            .limit(10).all()
        )
        return {
            "week_start": monday.date().isoformat(),
            "week_end": (monday + timedelta(days=6)).date().isoformat(),
            "top10": [
                {"place": i, "name": row.name, "grade": row.grade, "points": int(row.points or 0)}
                for i, row in enumerate(rows, start=1)
            ]
        }
    finally:
        db.close()

@app.get("/api/history")
def history(weeks: int = Query(default=8, ge=1, le=52)):
    """Oxirgi haftalardagi umumiy ballar tarixi; haftalar dushanbadan boshlanadi."""
    db = SessionLocal()
    try:
        this_monday = week_start_utc()
        result = []
        for offset in range(weeks - 1, -1, -1):
            start = this_monday - timedelta(days=7 * offset)
            end = start + timedelta(days=7)
            total = db.query(func.coalesce(func.sum(Score.points), 0)).filter(
                Score.created_at >= start, Score.created_at < end
            ).scalar()
            count = db.query(func.count(Score.id)).filter(
                Score.created_at >= start, Score.created_at < end
            ).scalar()
            result.append({
                "week_start": start.date().isoformat(),
                "week_end": (end - timedelta(days=1)).date().isoformat(),
                "points": int(total or 0),
                "answers_scored": int(count or 0)
            })
        return {"weeks": result}
    finally:
        db.close()
