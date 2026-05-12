import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Header, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from database import get_db
import crud
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
import logging

logger = logging.getLogger("uvicorn.error")

# Ensure env is loaded even if imported directly
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# JWT Config
SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-dev-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 1 week

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """
    Dependency that retrieves the current authenticated user.
    Checks 'Authorization' header first, then 'jwt_token' cookie.
    """
    auth_header = request.headers.get("Authorization")
    token = None
    
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        logger.debug("[AUTH] Found Bearer token in header")
    else:
        # Check httpOnly cookie
        token = request.cookies.get("jwt_token")
        if token:
            logger.debug("[AUTH] Found jwt_token in cookies")
        else:
            cookie_names = list(request.cookies.keys())
            logger.debug(f"[AUTH] No 'jwt_token' found. Browser sent: {cookie_names}")
            if not cookie_names:
                logger.debug("[TIP] Ensure you are using http://127.0.0.1:8000 and NOT localhost!")

        
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    payload = verify_token(token)
    if not payload:
        logger.debug("[AUTH] Token verification failed (invalid or expired)")
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    email = payload.get("sub")
    logger.debug(f"[AUTH] Token valid for user: {email}")
    
    if not email:
        raise HTTPException(status_code=401, detail="Token missing identity")

    user = crud.get_user_by_email(db, email)
    if not user:
        logger.warning(f"[AUTH] User not found in database for email: {email}")
        raise HTTPException(status_code=401, detail="User not found")
        
    return user

