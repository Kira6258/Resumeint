# Resumeint Setup Guide

This project is a full-stack AI platform built with **FastAPI** (Python) and a **Vanilla HTML/CSS/JS** frontend.

## Prerequisites
- Python 3.9+
- MySQL Server

## Environment Variables

### Backend (.env)
Create a `.env` in the `backend/` directory:
```
DATABASE_URL=mysql+pymysql://root:1234@localhost:3306/course_to_project
ANTHROPIC_API_KEY=your_key
JWT_SECRET=your_secret
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
STRIPE_SECRET_KEY=...
GITHUB_TOKEN=...
```

## Running Locally

There are three ways to start Resumeint:

1. **Python Runner (Recommended):**
   Run `python run.py` from the root directory. This provides a professional, colored console output.

2. **VS Code Integration:**
   - Press **F5** (or go to "Run and Debug") to start the server with debugging enabled.
   - Or, run the task **"Start Resumeint"** from the Command Palette (`Ctrl+Shift+P`).

3. **Directly (Backend):**
   Run `python main.py` from inside the `backend/` directory.

Visit `http://localhost:8000` to start using Resumeint. 
The static frontend is served automatically from the `/frontend` directory.


## Tech Stack
- **Backend:** FastAPI, SQLAlchemy, MySQL, Claude 3.5 Sonnet.
- **Frontend:** Vanilla HTML5, Vanilla CSS3 (Carbon-Dark Theme), Vanilla JavaScript (ES6+).
- **Auth:** JWT with httpOnly cookies.
