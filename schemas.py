"""
Database Schemas for LearnHub

Each Pydantic model represents a collection in MongoDB.
Collection name is the lowercase of the class name.

This file is used by the built-in database helper and viewers.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, EmailStr


class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Unique email address")
    password_hash: str = Field(..., description="Hashed password")
    avatar_url: Optional[str] = Field(None, description="Profile avatar")
    bio: Optional[str] = Field(None, description="Short bio")
    interests: List[str] = Field(default_factory=list, description="Skill tags user follows")
    roles: List[str] = Field(default_factory=lambda: ["user"], description="Roles: user, admin")
    is_active: bool = Field(True)
    provider: Optional[str] = Field(None, description="social auth provider if any")


class Course(BaseModel):
    title: str
    description: str
    category: str
    skills: List[str] = Field(default_factory=list)
    thumbnail_url: Optional[str] = None
    level: str = Field("Beginner", description="Beginner, Intermediate, Advanced")
    duration_minutes: int = 0
    instructor_id: Optional[str] = None
    playlist: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of lectures with {id, title, url, duration, chapter}"
    )
    quizzes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of quizzes with {id, title, questions[]}"
    )
    certificate_threshold: int = Field(70, ge=0, le=100, description="Passing score %")


class LectureProgress(BaseModel):
    user_id: str
    course_id: str
    lecture_id: str
    watched_seconds: int = 0
    completed: bool = False


class CourseProgress(BaseModel):
    user_id: str
    course_id: str
    completed_lecture_ids: List[str] = Field(default_factory=list)
    percentage: float = 0.0


class QuizResult(BaseModel):
    user_id: str
    course_id: str
    quiz_id: str
    score_percent: float
    answers: Dict[str, Any]
    passed: bool


class Certificate(BaseModel):
    user_id: str
    course_id: str
    quiz_id: Optional[str] = None
    score_percent: Optional[float] = None
    certificate_code: str
    issued_at: Optional[str] = None


class Discussion(BaseModel):
    course_id: str
    user_id: str
    title: str
    content: str
    tags: List[str] = Field(default_factory=list)


class Message(BaseModel):
    discussion_id: str
    user_id: str
    content: str


class Achievement(BaseModel):
    user_id: str
    title: str
    description: Optional[str] = None
    points: int = 0
    icon: Optional[str] = None
