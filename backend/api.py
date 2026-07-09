from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks, Response, Request
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
from pydantic import BaseModel
from limiter import limiter

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


@router.delete("/account/delete")
async def delete_account(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    """
    Permanently deletes the authenticated user's account and all associated data.
    Projects and check-ins are cascade-deleted via the ORM relationship.
    """
    try:
        import models as models_module
        # Delete all user projects first (cascade handles check_ins)
        projects = db.query(models_module.Project).filter(models_module.Project.user_id == current_user.id).all()
        for project in projects:
            db.delete(project)

        # Delete the user record itself
        user = db.query(models_module.User).filter(models_module.User.id == current_user.id).first()
        if user:
            db.delete(user)

        db.commit()
        return {"message": "Account and all associated data have been permanently deleted."}
    except Exception as e:
        db.rollback()
        print(f"[ACCOUNT DELETE] Error deleting user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete account. Please try again or contact support.")


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
    """
    Submits a weekly check-in and automatically triggers AI code review.
    """
    if len(code_submitted) > 10000:
        raise HTTPException(status_code=400, detail="Code submission too large. Please keep it under 10,000 characters.")

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




class CreateOrderDirectRequest(BaseModel):
    amount: int
    currency: str = "INR"
    receipt: Optional[str] = None

class VerifyPaymentRequestDirect(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan: Optional[str] = None

@router.post("/create-order")
async def create_order_direct(
    body: CreateOrderDirectRequest,
    current_user=Depends(auth.get_current_user)
):
    """
    Creates a Razorpay order directly with given amount, currency, and receipt.
    Amount must be in paise (minimum 100 paise).
    """
    if body.amount < 100:
        raise HTTPException(status_code=400, detail="Amount must be at least 100 paise (₹1)")
    
    try:
        from payments import client as razorpay_client
        order_data = {
            "amount": body.amount,
            "currency": body.currency,
            "receipt": body.receipt or f"receipt_{current_user.id}_{int(datetime.utcnow().timestamp())}",
            "payment_capture": 1
        }
        order = razorpay_client.order.create(data=order_data)
        return {
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"]
        }
    except Exception as e:
        print(f"Razorpay API Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create payment order due to payment gateway error.")

def verify_razorpay_signature(order_id: str, payment_id: str, signature: str, secret: str) -> bool:
    import hmac
    import hashlib
    msg = f"{order_id}|{payment_id}".encode('utf-8')
    generated = hmac.new(secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(generated, signature)

@router.post("/verify-payment")
async def verify_payment_direct(
    body: VerifyPaymentRequestDirect,
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user)
):
    """
    Verifies Razorpay payment signature and updates user subscription.
    """
    if not body.razorpay_order_id or not body.razorpay_payment_id or not body.razorpay_signature:
        raise HTTPException(status_code=400, detail="Missing payment verification details")
    
    # 1. Signature Verification
    secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    if not verify_razorpay_signature(body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature, secret):
        raise HTTPException(status_code=400, detail="Payment verification failed due to signature mismatch.")
    
    # 2. Complete subscription activation
    days = 30
    if body.plan == "yearly":
        days = 365
    else:
        try:
            from payments import client as razorpay_client
            order = razorpay_client.order.fetch(body.razorpay_order_id)
            if order and order.get("amount") == 49900:
                days = 365
        except Exception as e:
            print(f"Failed to fetch order details from Razorpay: {e}. Defaulting to 30 days.")
    
    from datetime import datetime, timedelta
    expires_at = datetime.utcnow() + timedelta(days=days)
    
    try:
        crud.update_user_subscription(
            db,
            current_user.id,
            tier="pro",
            razorpay_cust_id=f"pay_{body.razorpay_payment_id}",
            razorpay_sub_id=f"order_{body.razorpay_order_id}",
            expires_at=expires_at
        )
        plan_label = "Pro Yearly" if days == 365 else "Pro Monthly"
        return {"message": f"Payment verified — {plan_label} active!", "status": "success"}
    except Exception as e:
        print(f"Database Subscription Update Error: {e}")
        raise HTTPException(status_code=500, detail="Payment verified, but failed to update subscription in database.")


@router.post("/resume/analyze")
@limiter.limit("5/minute")
async def analyze_resume(
    request: Request,
    target_role: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user=Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """
    Endpoint to upload a resume and analyze it for a target role using AI.
    Validates that the uploaded file is actually a readable document (not an image or binary).
    """
    # --- 0. Validate target role ---
    target_role = target_role.strip() if target_role else ""
    if not target_role:
        raise HTTPException(status_code=400, detail="Target role is required. Please enter a job title (e.g. 'Backend Developer').")
    if len(target_role) > 200:
        raise HTTPException(status_code=400, detail="Target role is too long. Please keep it under 200 characters.")

    # --- 1. File size guard (5 MB max) ---
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File is too large. Maximum allowed size is 5 MB.")

    filename = file.filename.lower() if file.filename else ""

    # --- 2. Extension whitelist check ---
    ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt")
    if not any(filename.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        if filename.endswith(".doc"):
            raise HTTPException(
                status_code=400,
                detail="The older .doc format is not supported. Please save your resume as .docx (Word 2007+) or PDF and try again."
            )
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Please upload your resume as a PDF, DOCX, or TXT file."
        )

    # --- 3. Content-type guard (block images, binaries, etc.) ---
    content_type = (file.content_type or "").lower()
    BLOCKED_CONTENT_TYPES = (
        "image/", "video/", "audio/",
        "application/zip", "application/x-rar",
        "application/x-executable", "application/octet-stream"
    )
    if any(content_type.startswith(blocked) for blocked in BLOCKED_CONTENT_TYPES):
        raise HTTPException(
            status_code=400,
            detail=f"This looks like a {content_type.split('/')[0]} file, not a resume document. Please upload a PDF, DOCX, or TXT file."
        )

    # --- 4. Extract text ---
    extracted_text = ""
    try:
        if filename.endswith(".pdf"):
            # Magic-bytes check for PDF (starts with %PDF)
            if not content.startswith(b"%PDF"):
                raise HTTPException(
                    status_code=400,
                    detail="The uploaded file does not appear to be a valid PDF. Please check the file and try again."
                )
            extracted_text = await ai_service.extract_text_from_pdf(content)
        elif filename.endswith(".docx"):
            # Magic-bytes check for DOCX (ZIP-based Office format)
            if not content.startswith(b"PK"):
                raise HTTPException(
                    status_code=400,
                    detail="The uploaded file does not appear to be a valid DOCX. Please check the file and try again."
                )
            extracted_text = await ai_service.extract_text_from_docx(content)
        elif filename.endswith(".txt"):
            try:
                extracted_text = content.decode("utf-8")
            except UnicodeDecodeError:
                extracted_text = content.decode("latin-1", errors="ignore")
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[RESUME] Error parsing file '{filename}': {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to read your resume. Make sure the file isn't password-protected or corrupted."
        )

    # --- 5. Minimum text length check ---
    clean_text = extracted_text.strip()
    if not clean_text or len(clean_text) < 100:
        raise HTTPException(
            status_code=400,
            detail="Could not extract enough readable text from the file. The document may be scanned as an image, password-protected, or not a text-based resume. Try a different file."
        )

    # --- 6. Sanity check: does it look like a resume? ---
    # Split into STRONG resume indicators (highly specific) and COMMON indicators
    STRONG_RESUME_INDICATORS = [
        "experience", "education", "skills", "resume", "cv", "curriculum vitae",
        "work history", "employment", "objective", "summary", "qualifications",
        "certifications", "achievements", "awards", "references"
    ]
    COMMON_RESUME_INDICATORS = [
        "project", "university", "college", "bachelor", "master", "engineer",
        "developer", "intern", "github", "linkedin", "gpa", "cgpa",
        "python", "java", "javascript", "sql", "html", "css", "react",
        "node", "flask", "django", "aws", "docker", "git"
    ]
    lower_text = clean_text.lower()
    word_count = len(clean_text.split())

    # Must have at least 150 words to be a real resume
    if word_count < 150:
        raise HTTPException(
            status_code=400,
            detail="The document is too short to be a resume. Please upload your actual resume/CV file."
        )

    strong_matches = sum(1 for kw in STRONG_RESUME_INDICATORS if kw in lower_text)
    common_matches = sum(1 for kw in COMMON_RESUME_INDICATORS if kw in lower_text)

    # Must have at least 2 strong indicators AND at least 3 common indicators
    if strong_matches < 2 or common_matches < 3:
        raise HTTPException(
            status_code=400,
            detail="The uploaded document doesn't appear to be a resume. It is missing key resume sections (e.g. Experience, Education, Skills). Please upload your actual resume/CV file."
        )


    # --- 7. AI Analysis ---
    analysis = await ai_service.analyze_resume_ats(clean_text, target_role)

    if "error" in analysis:
        raise HTTPException(status_code=500, detail=analysis["error"])

    return analysis


class MockInterviewChatRequest(BaseModel):
    history: List[dict]

@router.post("/projects/{project_id}/interview/chat")
async def mock_interview_chat(
    project_id: int,
    body: MockInterviewChatRequest,
    db: Session = Depends(get_db),
    current_user = Depends(auth.get_current_user)
):
    """
    Handles conversational mock interview turns with streaming responses from the AI.
    """
    project = crud.get_project(db, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    checkins = crud.get_project_checkins(db, project_id)
    checkins_list = []
    for c in checkins:
        checkins_list.append({
            "week_number": c.week_number,
            "ai_feedback": c.ai_feedback or "",
            "status": c.status or "pending"
        })

    async def generate_chat():
        async for chunk in ai_service.stream_mock_interview(
            project_title=project.title,
            schema=project.mysql_schema_sql,
            repo=project.repo_structure_data,
            checkins=checkins_list,
            history=body.history
        ):
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate_chat(), media_type="text/event-stream")


@router.get("/projects/{project_id}/scaffold")
async def scaffold_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(auth.get_current_user)
):
    """
    Generates a pre-configured ZIP archive of the project's folder structure,
    starter boilerplate code, custom database schema, and active roadmap.
    """
    project = crud.get_project(db, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    import io
    import zipfile

    # Create in-memory zip file
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # 1. Add MySQL DDL Schema
        schema_sql = project.mysql_schema_sql or ""
        zip_file.writestr("schema.sql", schema_sql)

        # 2. Add an elite README
        readme_content = f"""# {project.title}

Generated via **Resumeint** — The Architectural Standard for Learning.

## 🎓 Course Alignment
This project aligns directly with the curriculum for **{project.course_name}**.

## 🛠️ Tech Stack & Database
- **Database:** MySQL (See [schema.sql](./schema.sql) for schema definitions)
- **Folder Structure:** See the structured packages inside this repository.

## 📁 Repository Map
"""
        # Append repo tree structure to README
        structure = project.repo_structure_data or {}
        for folder, files in structure.items():
            readme_content += f"- **{folder}/**\n"
            for f in files:
                readme_content += f"  - `{f}`\n"

        readme_content += "\n## 📋 AI Implementation Roadmap\n"
        if project.roadmap_data and isinstance(project.roadmap_data, list):
            for w in project.roadmap_data:
                readme_content += f"\n### Week {w.get('week')}: {w.get('goal')}\n"
                readme_content += f"**Core Deliverable:** {w.get('deliverable')}\n"
                readme_content += "**Milestones:**\n"
                for m in w.get("milestones", []):
                    readme_content += f"- [ ] {m}\n"
                readme_content += "**Mentor Hints:**\n"
                for h in w.get("hints", []):
                    readme_content += f"- *{h}*\n"
        else:
            readme_content += "No active roadmap found."

        zip_file.writestr("README.md", readme_content)

        # 3. Add .env.example
        env_content = f"""# {project.title} Environment Variables
DATABASE_URL=mysql+pymysql://root:password@localhost:3306/{project.title.replace(' ', '_').lower()}
PORT=8000
DEBUG=True
"""
        zip_file.writestr(".env.example", env_content)

        # 4. Determine package/dependency manifest based on file extensions
        has_python = False
        has_js = False
        for folder, files in structure.items():
            for f in files:
                if f.endswith(".py"):
                    has_python = True
                if f.endswith(".js") or f.endswith(".json"):
                    has_js = True

        if has_python:
            requirements = "fastapi>=0.95.0\nuvicorn>=0.20.0\nsqlalchemy>=2.0.0\npymysql>=1.0.0\npydantic>=2.0.0\nrequests>=2.28.0\n"
            zip_file.writestr("requirements.txt", requirements)

        if has_js:
            package_json = {
                "name": project.title.replace(" ", "-").lower(),
                "version": "1.0.0",
                "description": f"Scaffolded workspace for {project.title}",
                "main": "index.js",
                "scripts": {
                    "start": "node index.js",
                    "dev": "nodemon index.js"
                },
                "dependencies": {
                    "express": "^4.18.2",
                    "dotenv": "^16.0.3"
                }
            }
            zip_file.writestr("package.json", json.dumps(package_json, indent=2))

        # 5. Build physical folders and files with custom starters
        for folder, files in structure.items():
            for filename in files:
                path = f"{folder}/{filename}"
                content = ""
                
                # Dynamic Boilerplates
                if filename.endswith(".py"):
                    content = f"""# {filename}
# Scaffolded starter code for {project.title}
import os
import sys

def main():
    print("Initializing {project.title} - {folder}/{filename} starter module.")
    # TODO: Implement your application logic here
    
if __name__ == "__main__":
    main()
"""
                elif filename.endswith(".html"):
                    content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{project.title} - {filename}</title>
    <style>
        body {{
            font-family: system-ui, -apple-system, sans-serif;
            background: #0d0e11;
            color: #e4e6eb;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
        }}
        .card {{
            background: #1a1c23;
            border: 1px solid #2d313f;
            border-radius: 12px;
            padding: 40px;
            text-align: center;
            box-shadow: 0 8px 30px rgba(0,0,0,0.5);
        }}
        h1 {{ color: #d4a24e; margin-top: 0; }}
        code {{ background: #2d313f; padding: 4px 8px; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>{project.title}</h1>
        <p>Starter HTML file scaffolded successfully at <code>{folder}/{filename}</code>.</p>
        <p>Start editing this file to build your application interface!</p>
    </div>
</body>
</html>
"""
                elif filename.endswith(".css"):
                    content = f"""/* {filename} - Baseline reset and CSS variables */
:root {{
    --bg-primary: #0d0e11;
    --bg-secondary: #161821;
    --text-primary: #e4e6eb;
    --text-secondary: #9ea3b0;
    --accent: #d4a24e;
    --border: #2d313f;
}}

* {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}}

body {{
    background-color: var(--bg-primary);
    color: var(--text-primary);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}}
"""
                elif filename.endswith(".js"):
                    content = f"""// {filename} - Asynchronous modular ES6 starter logic
console.log("{project.title} - {folder}/{filename} initialized.");

async function initializeApp() {{
    try {{
        console.log("Loading module resources...");
    }} catch (error) {{
        console.error("Failed to load application modules:", error);
    }}
}}

document.addEventListener("DOMContentLoaded", initializeApp);
"""
                else:
                    content = f"# {filename}\n# Placeholder for {project.title} -> {folder}\n"

                zip_file.writestr(path, content)

    # Reset buffer position
    zip_buffer.seek(0)
    
    # Generate clean, standard filename
    clean_title = "".join(c if c.isalnum() else "-" for c in project.title).lower()
    filename = f"{clean_title}-scaffold.zip"

    
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/x-zip-compressed",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )



