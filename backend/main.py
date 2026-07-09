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
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from limiter import limiter

logger = logging.getLogger("uvicorn.error")

# Mock Email Storage for Development
mock_emails = []

# Configure logging to see errors in the console
logging.basicConfig(level=logging.INFO)



# Initialize DB tables and self-heal schema
def heal_database():
    print("\033[90m[INFO] Verifying database schema...\033[0m")
    # create_all is safe to call on existing DBs — only creates missing tables
    models.Base.metadata.create_all(bind=engine)
    
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    
    try:
        columns = [col['name'] for col in inspector.get_columns('users')]
    except Exception:
        # Tables may not exist yet on a brand-new deployment — create_all above handles it
        print("\033[92m[OK] Fresh database detected — tables created.\033[0m")
        return

    with engine.connect() as conn:
        # --- Users table patches ---
        # NOTE: AFTER clause removed — not supported by PostgreSQL (columns added at end, which is fine)
        if 'reset_token' not in columns:
            print("\033[94m[PATCH] Adding 'reset_token' column...\033[0m")
            conn.execute(text("ALTER TABLE users ADD COLUMN reset_token VARCHAR(255) UNIQUE"))
            conn.commit()
        if 'reset_token_expires' not in columns:
            print("\033[94m[PATCH] Adding 'reset_token_expires' column...\033[0m")
            conn.execute(text("ALTER TABLE users ADD COLUMN reset_token_expires TIMESTAMP"))
            conn.commit()
        if 'bio' not in columns:
            print("\033[94m[PATCH] Adding 'bio' column...\033[0m")
            conn.execute(text("ALTER TABLE users ADD COLUMN bio TEXT"))
            conn.commit()
        if 'github_url' not in columns:
            print("\033[94m[PATCH] Adding 'github_url' column...\033[0m")
            conn.execute(text("ALTER TABLE users ADD COLUMN github_url VARCHAR(512)"))
            conn.commit()
        if 'razorpay_customer_id' not in columns:
            print("\033[94m[PATCH] Adding 'razorpay_customer_id' column...\033[0m")
            conn.execute(text("ALTER TABLE users ADD COLUMN razorpay_customer_id VARCHAR(255) UNIQUE"))
            conn.commit()
        if 'razorpay_subscription_id' not in columns:
            print("\033[94m[PATCH] Adding 'razorpay_subscription_id' column...\033[0m")
            conn.execute(text("ALTER TABLE users ADD COLUMN razorpay_subscription_id VARCHAR(255) UNIQUE"))
            conn.commit()
        if 'linkedin_url' not in columns:
            print("\033[94m[PATCH] Adding 'linkedin_url' column...\033[0m")
            conn.execute(text("ALTER TABLE users ADD COLUMN linkedin_url VARCHAR(512)"))
            conn.commit()
        if 'leetcode_url' not in columns:
            print("\033[94m[PATCH] Adding 'leetcode_url' column...\033[0m")
            conn.execute(text("ALTER TABLE users ADD COLUMN leetcode_url VARCHAR(512)"))
            conn.commit()
        if 'portfolio_url' not in columns:
            print("\033[94m[PATCH] Adding 'portfolio_url' column...\033[0m")
            conn.execute(text("ALTER TABLE users ADD COLUMN portfolio_url VARCHAR(512)"))
            conn.commit()

        # --- Projects table patches ---
        project_columns = [col['name'] for col in inspector.get_columns('projects')]
        if 'milestone_progress' not in project_columns:
            print("\033[94m[PATCH] Adding 'milestone_progress' column...\033[0m")
            conn.execute(text("ALTER TABLE projects ADD COLUMN milestone_progress JSON"))
            conn.commit()

        # --- Check-ins table patches ---
        checkin_columns = [col['name'] for col in inspector.get_columns('check_ins')]
        if 'status' not in checkin_columns:
            print("\033[94m[PATCH] Adding 'status' column to check_ins...\033[0m")
            # Use standard SQL quoting for DEFAULT value (works on MySQL + PostgreSQL)
            conn.execute(text("ALTER TABLE check_ins ADD COLUMN status VARCHAR(50) DEFAULT 'pending'"))
            conn.commit()

        # SQLite-only foreign key enforcement
        if engine.name == 'sqlite':
            conn.execute(text("PRAGMA foreign_keys = ON"))

    print("\033[92m[OK] Database schema verified.\033[0m")


# Rate limiter — keyed by client IP address (imported from limiter.py)

app = FastAPI(title="Resumeint API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- Startup: DB Init + Keep-Alive ---
@app.on_event("startup")
async def on_startup():
    # 1. Initialize / heal the database schema
    # Run in a thread executor so it doesn't block the async event loop
    # (Important for slow Supabase cold-start connections)
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, heal_database)
    except Exception as e:
        print(f"\033[91m[STARTUP ERROR] Database init failed: {e}\033[0m")
        print("\033[93m[WARNING] App is running but DB may not be ready. Check DATABASE_URL env var.\033[0m")

    # 2. Self-ping to stay awake on Render free tier
    base_url = os.getenv("BASE_URL")
    if not base_url or "127.0.0.1" in base_url or "localhost" in base_url:
        return

    print(f"\033[94m[SYSTEM] Starting self-ping task for: {base_url}\033[0m")
    async def ping_loop():
        while True:
            await asyncio.sleep(600)  # Ping every 10 minutes
            try:
                async with httpx.AsyncClient() as client:
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
@limiter.limit("5/minute")  # Max 5 registrations per IP per minute
async def register(request: Request, user: schemas.UserCreate, db: Session = Depends(get_db)):
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
@limiter.limit("10/minute")  # Max 10 login attempts per IP per minute (brute-force protection)
async def login(request: Request, login_data: schemas.LoginRequest, response: Response, db: Session = Depends(get_db)):
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
        
        response = RedirectResponse(url=f"/dashboard.html?token={jwt_token}")
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
@limiter.limit("3/minute")  # Max 3 requests per IP per minute (prevents email spam)
async def forgot_password(request: Request, request_body: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, request_body.email)
    if not db_user:
        # Don't reveal user existence
        return {"message": "If this email exists, a reset link has been sent."}
    
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=1)
    crud.set_user_reset_token(db, request_body.email, token, expires_at)
    
    # Real Email Sending
    reset_url = f"{os.getenv('BASE_URL', 'http://127.0.0.1:8000')}/reset-password.html?token={token}"
    email_body = f"Hello,\n\nYou requested a password reset for your Resumeint account. Click the link below to set a new password:\n\n{reset_url}\n\nThis link will expire in 1 hour.\n\nIf you did not request this, please ignore this email."
    
    from email_service import send_real_email
    success = send_real_email(request_body.email, "Reset your Resumeint password", email_body)
    
    if not success:
        # Fallback to mock for dev visibility if real fails
        print(f"\033[93m[FALLBACK] Real email failed, logging reset link: {reset_url}\033[0m")
        mock_emails.append({
            "to": request_body.email,
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




# Health check endpoint — useful for diagnosing Supabase free-tier pauses
@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        user_count = db.execute(text("SELECT COUNT(*) FROM users")).scalar()
        return {
            "status": "ok",
            "database": "connected",
            "users_in_db": user_count
        }
    except Exception as e:
        return {
            "status": "error",
            "database": "disconnected",
            "detail": str(e)
        }

# 2. Main API
app.include_router(api_router, prefix="/api")
app.include_router(payments_router, prefix="/api/payments")

# 3. Static Files (Served at root)
@app.get("/index.html", response_class=RedirectResponse)
async def redirect_index():
    return RedirectResponse(url="/", status_code=301)

# Mounting at "/" must come LAST so API routes take precedence
app.mount("/", StaticFiles(directory="../frontend", html=True), name="static")

if __name__ == "__main__":
    # Use 0.0.0.0 to accept connections from any interface (required for cloud deploys like Render)
    # For local dev, the app is still accessible at http://127.0.0.1:8000
    port = int(os.getenv("PORT", 8000))
    is_dev = os.getenv("ENV", "development") != "production"
    print(f"\033[94m[INFO] Project will be served at: \033[96mhttp://0.0.0.0:{port}\033[0m")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=is_dev)
