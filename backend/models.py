from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True)
    hashed_password = Column(String(255), nullable=True) # Nullable for OAuth users
    name = Column(String(255))
    avatar_url = Column(String(512))
    subscription_tier = Column(String(50), default="free")
    razorpay_customer_id = Column(String(255), unique=True)
    razorpay_subscription_id = Column(String(255), unique=True)
    subscription_expires_at = Column(DateTime)
    reset_token = Column(String(255), unique=True, nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    
    # Profile Extensions
    bio = Column(Text, nullable=True)
    linkedin_url = Column(String(512), nullable=True)
    github_url = Column(String(512), nullable=True)
    leetcode_url = Column(String(512), nullable=True)
    portfolio_url = Column(String(512), nullable=True)


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    title = Column(String(255))
    course_name = Column(String(255))
    roadmap_data = Column(JSON)
    repo_structure_data = Column(JSON)
    mysql_schema_sql = Column(Text)
    milestone_progress = Column(JSON, default=dict)  # Store as {"week_num": [milestone_indices]}
    status = Column(String(50), default="active")
    created_at = Column(DateTime, server_default=func.now())

    from sqlalchemy.orm import relationship
    check_ins = relationship("CheckIn", back_populates="project", cascade="all, delete-orphan")

class CheckIn(Base):
    __tablename__ = "check_ins"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), index=True)
    week_number = Column(Integer)
    code_submitted = Column(Text)
    github_link = Column(String(512))
    ai_feedback = Column(Text)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime, server_default=func.now())

    from sqlalchemy.orm import relationship
    project = relationship("Project", back_populates="check_ins")
