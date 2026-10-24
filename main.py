
import os
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./kelajak_mathquest.db"
)

engine_args = {}
if DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_args)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, index=True)
    name = Column(String, nullable=False)
    grade = Column(Integer, nullable=False)

class Score(Base):
    __tablename__ = "scores"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, index=True, nullable=False)
    points = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Kelajak Markazi Math Quest")

class StudentIn(BaseModel):
    telegram_id: str
    name: str = Field(min_length=1, max_length=80)
    grade: int = Field(ge=1, le=4)

class AnswerIn(BaseModel):
    telegram_id: str
    correct: bool

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/register")
def register(data: StudentIn):
    db = SessionLocal()
    try:
        student = db.query(Student).filter_by(
            telegram_id=data.telegram_id
        ).first()
        if student:
            student.name = data.name
            student.grade = data.grade
        else:
            student = Student(
                telegram_id=data.telegram_id,
                name=data.name,
                grade=data.grade
            )
            db.add(student)
        db.commit()
        return {"ok": True, "name": student.name, "grade": student.grade}
    finally:
        db.close()

@app.post("/api/answer")
def answer(data: AnswerIn):
    db = SessionLocal()
    try:
        student = db.query(Student).filter_by(
            telegram_id=data.telegram_id
        ).first()
        if not student:
            raise HTTPException(404, "Avval ro'yxatdan o'ting")
        points = 10 if data.correct else 0
        if points:
            db.add(Score(telegram_id=data.telegram_id, points=points))
            db.commit()
        return {"added_points": points}
    finally:
        db.close()

@app.get("/api/leaderboard")
def leaderboard():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        monday = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        rows = (
            db.query(
                Student.name,
                Student.grade,
                func.sum(Score.points).label("points")
            )
            .join(Score, Student.telegram_id == Score.telegram_id)
            .filter(Score.created_at >= monday.replace(tzinfo=None))
            .group_by(Student.telegram_id, Student.name, Student.grade)
            .order_by(func.sum(Score.points).desc())
            .limit(10)
            .all()
        )
        return {
            "week_start": monday.date().isoformat(),
            "top10": [
                {"place": i, "name": r.name, "grade": r.grade,
                 "points": r.points}
                for i, r in enumerate(rows, start=1)
            ]
        }
    finally:
        db.close()
