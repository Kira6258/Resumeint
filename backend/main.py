from dotenv import load_dotenv
import os
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

from fastapi import FastAPI, Depends, HTTPException, Response, Request
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from api import router as api_router
from payments import router as payments_router
from database import engine, Base
import models
import auth
import crud
from sqlalchemy.orm import Session
from database import get_db
import schemas
import uvicorn
import logging
from datetime import datetime, timedelta
import secrets
import httpx
import asyncio

logger = logging.getLogger("uvicorn.error")

# Mock Email Storage for Development
mock_emails = []

# Configure logging to see errors in the console
logging.basicConfig(level=logging.INFO)



# Initialize DB tables and self-heal schema
def heal_database():
    print("\033[90m[INFO] Verifying database schema...\033[0m")
    models.Base.metadata.create_all(bind=engine)
    
    # Check for missing columns in users table
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('users')]
    
    with engine.connect() as conn:
        if 'reset_token' not in columns:
            print("\033[94m[PATCH] Adding 'reset_token' column to users table...\033[0m")
            conn.execute(text("ALTER TABLE users ADD COLUMN reset_token VARCHAR(255) UNIQUE AFTER subscription_expires_at"))
            conn.commit()
        if 'reset_token_expires' not in columns:
            print("\033[94m[PATCH] Adding 'reset_token_expires' column to users table...\033[0m")
            conn.execute(text("ALTER TABLE users ADD COLUMN reset_token_expires DATETIME AFTER reset_token"))
            conn.commit()
        if 'bio' not in columns:
            print("\033[94m[PATCH] Adding 'bio' column to users table...\033[0m")
            conn.execute(text("ALTER TABLE users ADD COLUMN bio TEXT"))
            conn.commit()
        if 'github_url' not in columns:
            print("\033[94m[PATCH] Adding 'github_url' column to users table...\033[0m")
            conn.execute(text("ALTER TABLE users ADD COLUMN github_url VARCHAR(512)"))
            conn.commit()
            
        # Razorpay Migration
        if 'razorpay_customer_id' not in columns:
            print("\033[94m[PATCH] Adding 'razorpay_customer_id' column to users table...\033[0m")
            conn.execute(text("ALTER TABLE users ADD COLUMN razorpay_customer_id VARCHAR(255) UNIQUE"))
            conn.commit()
        if 'razorpay_subscription_id' not in columns:
            print("\033[94m[PATCH] Adding 'razorpay_subscription_id' column to users table...\033[0m")
            conn.execute(text("ALTER TABLE users ADD COLUMN razorpay_subscription_id VARCHAR(255) UNIQUE"))
            conn.commit()
            
        if 'linkedin_url' not in columns:
            print("\033[94m[PATCH] Adding 'linkedin_url' column to users table...\033[0m")
            conn.execute(text("ALTER TABLE users ADD COLUMN linkedin_url VARCHAR(512)"))
            conn.commit()
        if 'leetcode_url' not in columns:
            print("\033[94m[PATCH] Adding 'leetcode_url' column to users table...\033[0m")
            conn.execute(text("ALTER TABLE users ADD COLUMN leetcode_url VARCHAR(512)"))
            conn.commit()
        if 'portfolio_url' not in columns:
            print("\033[94m[PATCH] Adding 'portfolio_url' column to users table...\033[0m")
            conn.execute(text("ALTER TABLE users ADD COLUMN portfolio_url VARCHAR(512)"))
            conn.commit()
            
        # Check for missing columns in projects table
        project_columns = [col['name'] for col in inspector.get_columns('projects')]
        if 'milestone_progress' not in project_columns:
            print("\033[94m[PATCH] Adding 'milestone_progress' column to projects table...\033[0m")
            conn.execute(text("ALTER TABLE projects ADD COLUMN milestone_progress JSON"))
            conn.commit()
            
        # Check for missing columns in check_ins table
        checkin_columns = [col['name'] for col in inspector.get_columns('check_ins')]
        if 'status' not in checkin_columns:
            print("\033[94m[PATCH] Adding 'status' column to check_ins table...\033[0m")
            conn.execute(text("ALTER TABLE check_ins ADD COLUMN status VARCHAR(50) DEFAULT 'pending'"))
            conn.commit()
            
        # Force cascade delete patch for SQLite/MySQL (dropping and recreating constraint is hard, so we just ensure it's handled in ORM or try a simple drop if MySQL)
        # Actually, let's try a safer way: just make sure SQLAlchemy ORM handles it (which I already did with cascade="all, delete-orphan").
        # If it's still failing, it might be that the DB is SQLite and doesn't enforce FK by default.
        if engine.name == 'sqlite':
            conn.execute(text("PRAGMA foreign_keys = ON"))
            
    print("\033[92m[OK] Database schema verified.\033[0m")

heal_database()

app = FastAPI(title="Resumeint API")

# --- Keep-Alive / Self-Ping Logic ---
@app.on_event("startup")
async def self_ping():
    """Background task to ping itself to stay awake on free tiers."""
    base_url = os.getenv("BASE_URL")
    if not base_url or "127.0.0.1" in base_url or "localhost" in base_url:
        return
        
    print(f"\033[94m[SYSTEM] Starting self-ping task for: {base_url}\033[0m")
    async def ping_loop():
        while True:
            # Ping every 10 minutes (Render sleep is 15 mins)
            await asyncio.sleep(600) 
            try:
                async with httpx.AsyncClient() as client:
                    # Ping the docs or a simple root endpoint
                    await client.get(f"{base_url}/")
                    print(f"\033[90m[PING] Keep-alive ping sent to {base_url}\033[0m")
            except Exception as e:
                print(f"\033[91m[PING ERROR] {e}\033[0m")
                
    asyncio.create_task(ping_loop())


# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.middleware.sessions import SessionMiddleware
app.add_middleware(SessionMiddleware, secret_key=os.getenv("JWT_SECRET", "session-secret"))

# 1. Authentication Routes
@app.post("/auth/register")
async def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, user.email)
    if db_user:
        # Use 409 Conflict for existing resource
        raise HTTPException(status_code=409, detail="This email is already registered.")
    try:
        crud.create_user(db, user)
    except Exception as e:
        print(f"Registration Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create user. Please check your data.")
    return {"message": "User created successfully"}


@app.post("/auth/login")
async def login(login_data: schemas.LoginRequest, response: Response, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, login_data.email)
    if not db_user or not crud.verify_password(login_data.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = auth.create_access_token(data={"sub": db_user.email})
    
    # Set cookie as primary session
    response.set_cookie(
        key="jwt_token",
        value=token,
        httponly=True,
        max_age=auth.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=os.getenv("ENV") == "production",
        path="/"
    )
    
    print(f"\033[92m[AUTH] User logged in: {db_user.email}\033[0m")
    # Return token in body as backup/fallback for frontend
    return {
        "message": "Login successful", 
        "access_token": token,
        "token_type": "bearer",
        "user": {"email": db_user.email, "name": db_user.name}
    }



@app.get("/auth/google")
async def google_login(request: Request):
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", f"{os.getenv('BASE_URL', 'http://127.0.0.1:8000')}/auth/google/callback")
    return await auth.oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/google/callback")
async def google_callback(request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        token = await auth.oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        if not user_info:
            raise HTTPException(status_code=400, detail="Failed to get user info from Google")
        
        email = user_info.get('email')
        name = user_info.get('name')
        avatar = user_info.get('picture')

        # Check if user exists, else create
        db_user = crud.get_user_by_email(db, email)
        if not db_user:
            user_in = schemas.UserCreate(email=email, name=name, password=None, avatar_url=avatar)
            db_user = crud.create_user(db, user_in)
            print(f"\033[92m[AUTH] New user created via Google: {email}\033[0m")
        
        # Create JWT
        jwt_token = auth.create_access_token(data={"sub": db_user.email})
        
        response = RedirectResponse(url="/dashboard.html")
        response.set_cookie(
            key="jwt_token",
            value=jwt_token,
            httponly=True,
            max_age=auth.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            samesite="lax",
            secure=os.getenv("ENV") == "production",
            path="/"
        )
        return response
    except Exception as e:
        print(f"\033[91m[AUTH ERROR] Google Login failed: {e}\033[0m")
        return RedirectResponse(url="/login.html?error=google_failed")

@app.get("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("jwt_token")
    return {"message": "Successfully logged out"}

@app.post("/auth/forgot-password")
async def forgot_password(request: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, request.email)
    if not db_user:
        # Don't reveal user existence
        return {"message": "If this email exists, a reset link has been sent."}
    
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=1)
    crud.set_user_reset_token(db, request.email, token, expires_at)
    
    # Real Email Sending
    reset_url = f"{os.getenv('BASE_URL', 'http://127.0.0.1:8000')}/reset-password.html?token={token}"
    email_body = f"Hello,\n\nYou requested a password reset for your Resumeint account. Click the link below to set a new password:\n\n{reset_url}\n\nThis link will expire in 1 hour.\n\nIf you did not request this, please ignore this email."
    
    from email_service import send_real_email
    success = send_real_email(request.email, "Reset your Resumeint password", email_body)
    
    if not success:
        # Fallback to mock for dev visibility if real fails
        print(f"\033[93m[FALLBACK] Real email failed, logging reset link: {reset_url}\033[0m")
        mock_emails.append({
            "to": request.email,
            "url": reset_url,
            "timestamp": datetime.now().isoformat()
        })
    
    return {"message": "Reset link sent successfully."}

@app.post("/auth/reset-password")
async def reset_password(request: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_reset_token(db, request.token)
    if not db_user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    crud.update_user_password(db, db_user, request.new_password)
    return {"message": "Password reset successfully"}




# 2. Main API
app.include_router(api_router, prefix="/api")
app.include_router(payments_router, prefix="/api/payments")

# 3. Static Files (Served at root)
# Mounting at "/" must come LAST so API routes take precedence
app.mount("/", StaticFiles(directory="../frontend", html=True), name="static")

if __name__ == "__main__":
    # Use 127.0.0.1 as the host for more reliable cookie handling
    print("\033[94m[INFO] Project will be served at: \033[96mhttp://127.0.0.1:8000\033[0m")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
