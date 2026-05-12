from sqlalchemy.orm import Session
from sqlalchemy import desc
import models, schemas
import bcrypt
from datetime import datetime


def get_password_hash(password):
    if not password:
        return None
    # Password must be bytes for bcrypt
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

def verify_password(plain_password, hashed_password):
    if not plain_password or not hashed_password:
        return False
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


# User operations
def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def create_user(db: Session, user: schemas.UserCreate):
    db_user = models.User(
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        hashed_password=get_password_hash(user.password) if user.password else None,
        subscription_tier="free"
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def set_user_reset_token(db: Session, email: str, token: str, expires_at: datetime):
    db_user = get_user_by_email(db, email)
    if db_user:
        db_user.reset_token = token
        db_user.reset_token_expires = expires_at
        db.commit()
    return db_user

def get_user_by_reset_token(db: Session, token: str):
    from datetime import datetime
    return db.query(models.User).filter(
        models.User.reset_token == token,
        models.User.reset_token_expires > datetime.utcnow()
    ).first()

def update_user_password(db: Session, user: models.User, new_password: str):
    user.hashed_password = get_password_hash(new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()
    db.refresh(user)
    return user

def update_user_profile(db: Session, user: models.User, update_data: schemas.UserUpdate):
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user

def update_user_subscription(db: Session, user_id: int, tier: str, razorpay_cust_id: str, razorpay_sub_id: str, expires_at):
    db_user = get_user(db, user_id)
    if db_user:
        db_user.subscription_tier = tier
        db_user.razorpay_customer_id = razorpay_cust_id
        db_user.razorpay_subscription_id = razorpay_sub_id
        db_user.subscription_expires_at = expires_at
        db.commit()
        db.refresh(db_user)
    return db_user

# Project operations
def get_user_projects(db: Session, user_id: int):
    from sqlalchemy.orm import joinedload
    return db.query(models.Project).options(joinedload(models.Project.check_ins)).filter(models.Project.user_id == user_id).order_by(desc(models.Project.created_at)).all()

def get_project(db: Session, project_id: int):
    from sqlalchemy.orm import joinedload
    return db.query(models.Project).options(joinedload(models.Project.check_ins)).filter(models.Project.id == project_id).first()

def create_project(db: Session, project: schemas.ProjectCreate):
    db_project = models.Project(
        user_id=project.user_id,
        title=project.title,
        course_name=project.course_name,
        roadmap_data=project.roadmap_data,
        repo_structure_data=project.repo_structure_data,
        mysql_schema_sql=project.mysql_schema_sql,
        status=project.status
    )
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

def delete_project(db: Session, project_id: int):
    # Manually delete check-ins first to be absolutely sure
    db.query(models.CheckIn).filter(models.CheckIn.project_id == project_id).delete()
    db.query(models.Project).filter(models.Project.id == project_id).delete()
    db.commit()

def update_milestone_progress(db: Session, project: models.Project, week: int, index: int, completed: bool):
    current = project.milestone_progress or {}
    # Convert week to string for JSON stability
    w_key = str(week)
    
    if w_key not in current:
        current[w_key] = []
        
    indices = set(current[w_key])
    if completed:
        indices.add(index)
    else:
        indices.discard(index)
        
    current[w_key] = list(indices)
    project.milestone_progress = current
    
    # Force SQLAlchemy to detect change in JSON field
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(project, "milestone_progress")
    
    db.commit()
    db.refresh(project)
    return project

# Check-in operations
def get_project_checkins(db: Session, project_id: int):
    return db.query(models.CheckIn).filter(models.CheckIn.project_id == project_id).order_by(models.CheckIn.week_number).all()

def create_checkin(db: Session, checkin: schemas.CheckInCreate):
    db_checkin = models.CheckIn(
        project_id=checkin.project_id,
        week_number=checkin.week_number,
        code_submitted=checkin.code_submitted,
        github_link=checkin.github_link
    )
    db.add(db_checkin)
    db.commit()
    db.refresh(db_checkin)
    return db_checkin

def get_checkin(db: Session, checkin_id: int):
    return db.query(models.CheckIn).filter(models.CheckIn.id == checkin_id).first()
