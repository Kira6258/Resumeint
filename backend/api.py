from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional, List
import json
import os
from datetime import datetime

from database import get_db
import crud
import schemas
import auth
import ai_service

router = APIRouter()

@router.get("/me", response_model=schemas.UserResponse)
async def get_me(current_user=Depends(auth.get_current_user)):
    return current_user

@router.put("/me", response_model=schemas.UserResponse)
async def update_me(update_data: schemas.UserUpdate, db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    # Basic URL validation for profile links
    urls = {
        "linkedin": update_data.linkedin_url,
        "github": update_data.github_url,
        "leetcode": update_data.leetcode_url,
        "portfolio": update_data.portfolio_url
    }
    
    for key, url in urls.items():
        if url and not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail=f"Invalid {key} URL. Must start with http:// or https://")

    user = crud.update_user_profile(db, current_user, update_data)
    return user

@router.put("/me/password")
async def change_password(data: schemas.ChangePasswordRequest, db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    """Allow a logged-in user to change their own password by verifying the current one first."""
    if not current_user.hashed_password:
        raise HTTPException(status_code=400, detail="Password change is not available for Google-authenticated accounts.")
    if not crud.verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    crud.update_user_password(db, current_user, data.new_password)
    return {"message": "Password updated successfully."}


@router.get("/projects", response_model=List[schemas.ProjectResponse])
async def get_projects(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    return crud.get_user_projects(db, current_user.id)


@router.post("/suggestions")
async def get_suggestions(
    text_syllabus: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user=Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """
    Step 1: Takes syllabus and returns 5 project suggestions.
    """
    # Rate Limiting / Subscription Check
    user_projects = crud.get_user_projects(db, current_user.id)

    # 1. Free Tier Check (1 Project)
    if current_user.subscription_tier != "pro":
        if len(user_projects) >= 1:
            now = datetime.utcnow()
            if not current_user.subscription_expires_at or current_user.subscription_expires_at < now:
                raise HTTPException(status_code=402, detail="Free limit reached (1 project). Please upgrade to Pro for unlimited architectures.")
    # Pro users: Unlimited — no cap

    syllabus_content = text_syllabus or ""
    if file:
        content = await file.read()
        if file.filename.endswith(".pdf"):
            syllabus_content = await ai_service.extract_text_from_pdf(content)
        elif file.filename.endswith(".docx"):
            syllabus_content = await ai_service.extract_text_from_docx(content)
        else:
            syllabus_content = content.decode("utf-8")

    if not syllabus_content or len(syllabus_content.strip()) < 10:
        raise HTTPException(status_code=400, detail="Please provide valid syllabus content (at least a few words).")

    # Add a variation parameter if it's a refresh (optional, we'll just let the AI randomize)
    ai_data = await ai_service.generate_project_suggestions(syllabus_content)
    if "error" in ai_data:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {ai_data['error']}")

    # Return suggestions + the extracted syllabus text (needed for step 2)
    return {
        "syllabus_text": syllabus_content,
        "course_name": ai_data.get("course_name", "Course"),
        "suggestions": ai_data.get("suggestions", [])
    }


@router.post("/projects", response_model=schemas.ProjectResponse)
async def create_project(
    title: Optional[str] = Form(None),
    course_name: Optional[str] = Form(None),
    text_syllabus: Optional[str] = Form(None),
    selected_project: Optional[str] = Form(None),
    duration_weeks: int = Form(4),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user)
):
    """
    Step 2: Creates a project. If selected_project is provided, generates a full roadmap for it.
    Otherwise falls back to single-shot generation.
    """
    # 1. Extract text if file provided
    syllabus_content = text_syllabus or ""
    if file:
        content = await file.read()
        if file.filename.endswith(".pdf"):
            syllabus_content = await ai_service.extract_text_from_pdf(content)
        elif file.filename.endswith(".docx"):
            syllabus_content = await ai_service.extract_text_from_docx(content)
        else:
            syllabus_content = content.decode("utf-8")

    if not syllabus_content:
        raise HTTPException(status_code=400, detail="No syllabus content provided")

    # Final subscription check before creation
    user_projects = crud.get_user_projects(db, current_user.id)
    
    # 1. Free Tier Check
    if current_user.subscription_tier != "pro":
        if len(user_projects) >= 1:
            now = datetime.utcnow()
            if not current_user.subscription_expires_at or current_user.subscription_expires_at < now:
                raise HTTPException(status_code=402, detail="Free limit reached. Upgrade to Pro for unlimited projects.")
    # Pro users: Unlimited — no cap

    # 2. Call AI
    if selected_project:
        # New flow: generate roadmap for the chosen project
        try:
            chosen = json.loads(selected_project)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid project selection data")
        ai_data = await ai_service.generate_full_roadmap(syllabus_content, chosen, duration_weeks)
    else:
        # Legacy flow: single-shot
        ai_data = await ai_service.generate_roadmap(syllabus_content, duration_weeks)

    if "error" in ai_data:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {ai_data['error']}")

    # 3. Create project in DB
    new_project = schemas.ProjectCreate(
        user_id=current_user.id,
        title=title or ai_data.get("project_title", "New Project"),
        course_name=course_name or ai_data.get("course_name", "Extracted Course"),
        roadmap_data=ai_data.get("weeks"),
        repo_structure_data=ai_data.get("repo_structure"),
        mysql_schema_sql=ai_data.get("mysql_schema"),
        status="active"
    )

    return crud.create_project(db, new_project)


@router.get("/projects/{project_id}", response_model=schemas.ProjectResponse)
async def get_project(project_id: int, db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    project = crud.get_project(db, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.delete("/projects/{project_id}")
async def delete_project(project_id: int, db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    project = crud.get_project(db, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    crud.delete_project(db, project_id)
    return {"message": "Project deleted successfully"}

@router.get("/projects/{project_id}/checkins", response_model=List[schemas.CheckInResponse])
async def get_checkins(project_id: int, db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    project = crud.get_project(db, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return crud.get_project_checkins(db, project_id)

@router.get("/checkins/{checkin_id}", response_model=schemas.CheckInResponse)
async def get_checkin(checkin_id: int, db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    checkin = crud.get_checkin(db, checkin_id)
    if not checkin:
        raise HTTPException(status_code=404, detail="Check-in not found")
    # Verify ownership via project
    project = crud.get_project(db, checkin.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return checkin

@router.patch("/projects/{project_id}/milestones", response_model=schemas.ProjectResponse)
async def update_milestone(
    project_id: int,
    update: schemas.MilestoneUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user)
):
    project = crud.get_project(db, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")
        
    return crud.update_milestone_progress(db, project, update.week_number, update.milestone_index, update.completed)

@router.post("/checkins")
async def submit_checkin(
    project_id: int = Form(...),
    week_number: int = Form(...),
    code_submitted: str = Form(...),
    github_link: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user)
):
    # Verify ownership
    project = crud.get_project(db, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    # Create check-in
    checkin_data = schemas.CheckInCreate(
        project_id=project_id,
        week_number=week_number,
        code_submitted=code_submitted,
        github_link=github_link
    )
    db_checkin = crud.create_checkin(db, checkin_data)

    # Stream AI Review
    milestones = ""
    if project.roadmap_data and isinstance(project.roadmap_data, list):
        for w in project.roadmap_data:
            if w.get("week") == week_number:
                milestones = ", ".join(w.get("milestones", []))

    async def generate_feedback():
        feedback_full = ""
        async for chunk in ai_service.stream_code_review(milestones, code_submitted):
            feedback_full += chunk
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"

        # Save complete feedback at the end
        db_checkin.ai_feedback = feedback_full
        
        # Parse score: [SCORE: X.X / 10] or SCORE: X.X / 10
        import re
        score_match = re.search(r"(?:\[)?SCORE:\s*([\d\.]+)\s*/\s*10(?:\])?", feedback_full, re.IGNORECASE)
        if score_match:
            try:
                score = float(score_match.group(1))
                db_checkin.status = "accepted" if score >= 6.5 else "redo"
            except ValueError:
                db_checkin.status = "pending"
        else:
            # Fallback if AI didn't follow format exactly
            db_checkin.status = "pending"
            
        db.commit()
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate_feedback(), media_type="text/event-stream")


@router.post("/projects/{project_id}/sync-github")
async def sync_github(project_id: int, db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    """
    Creates a GitHub repository and pushes the initial folder structure.
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token or token == "NOT_SET":
        raise HTTPException(status_code=500, detail="GitHub integration not configured on server.")

    project = crud.get_project(db, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    from github import Github, GithubException
    g = Github(token)
    
    try:
        user = g.get_user()
        repo_name = project.title.replace(" ", "-").lower() + "-" + str(project_id)
        
        # 1. Create Repo
        repo = user.create_repo(
            repo_name,
            description=f"Auto-generated architecture for: {project.course_name}. Built via Resumeint.",
            private=True
        )
        
        # 2. Push Structure (Initial Files)
        # repo_structure_data looks like {"backend": ["main.py", ...], "frontend": [...]}
        structure = project.repo_structure_data or {}
        
        # Add a default README
        readme_content = f"# {project.title}\n\n## Course: {project.course_name}\n\n### Architecture Roadmap\nThis project was architected using Resumeint.\n\n### Initial Schema\n```sql\n{project.mysql_schema_sql or '-- No schema required'}\n```"
        repo.create_file("README.md", "Initial commit: README", readme_content)

        # Create folders and dummy files
        for folder, files in structure.items():
            for filename in files:
                path = f"{folder}/{filename}"
                content = f"# {filename}\n# Placeholder for {project.title}"
                try:
                    repo.create_file(path, f"Add {filename}", content)
                except:
                    pass # Skip if exists or error
        
        return {
            "message": "Repository created and synced successfully!",
            "repo_url": repo.html_url,
            "repo_name": repo_name
        }
    except GithubException as e:
        print(f"GitHub Error: {e}")
        if e.status == 422:
            raise HTTPException(status_code=422, detail="A repository with this name already exists.")
        raise HTTPException(status_code=500, detail=f"GitHub Error: {e.data.get('message', 'Unknown error')}")
    except Exception as e:
        print(f"Sync Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to sync with GitHub")

