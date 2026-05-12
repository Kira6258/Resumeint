from pydantic import BaseModel, EmailStr
from typing import Optional, List, Any
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    leetcode_url: Optional[str] = None
    portfolio_url: Optional[str] = None

class UserCreate(UserBase):
    password: Optional[str] = None # For email registration

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class UserUpdate(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    leetcode_url: Optional[str] = None
    portfolio_url: Optional[str] = None

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class MilestoneUpdate(BaseModel):
    week_number: int
    milestone_index: int
    completed: bool

class UserResponse(UserBase):
    id: int
    subscription_tier: str
    razorpay_customer_id: Optional[str] = None
    razorpay_subscription_id: Optional[str] = None
    subscription_expires_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ProjectCreate(BaseModel):
    user_id: int
    title: str
    course_name: str
    roadmap_data: Optional[Any] = None
    repo_structure_data: Optional[Any] = None
    mysql_schema_sql: Optional[str] = None
    status: str = "active"

class CheckInCreate(BaseModel):
    project_id: int
    week_number: int
    code_submitted: str
    github_link: Optional[str] = None

class CheckInResponse(CheckInCreate):
    id: int
    ai_feedback: Optional[str] = None
    status: str = "pending"
    created_at: datetime

    class Config:
        from_attributes = True

class ProjectResponse(BaseModel):
    id: int
    user_id: int
    title: str
    course_name: str
    roadmap_data: Optional[Any] = None
    repo_structure_data: Optional[Any] = None
    mysql_schema_sql: Optional[str] = None
    milestone_progress: Optional[Any] = None
    status: str
    created_at: datetime
    check_ins: List[CheckInResponse] = []

    class Config:
        from_attributes = True
