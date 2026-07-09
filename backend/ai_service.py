import os
import json
import requests
from typing import Optional, List, Dict, Any, AsyncGenerator
import fitz  # PyMuPDF
from docx import Document
import io

# Model priority list — tries each in order until one succeeds
MODELS_TO_TRY = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
]


def _call_groq(prompt: str, json_mode: bool = False) -> Optional[str]:
    """
    Calls Groq API.
    Returns the raw text response or None on failure.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "NOT_SET" or api_key == "gsk_your_groq_api_key_here":
        return None

    # Try SDK first
    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        for model_name in MODELS_TO_TRY:
            try:
                print(f"\033[90m[AI] Trying SDK: {model_name} (JSON: {json_mode})...\033[0m")
                kwargs = {
                    "messages": [{"role": "user", "content": prompt}],
                    "model": model_name,
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                
                response = client.chat.completions.create(**kwargs)
                text = response.choices[0].message.content.strip()
                print(f"\033[92m[AI] SUCCESS via SDK: {model_name}\033[0m")
                return text
            except Exception as e:
                print(f"\033[93m[AI] SDK {model_name} failed: {type(e).__name__}: {e}\033[0m")
                continue
    except ImportError:
        print("\033[93m[AI] groq SDK not installed, falling back to REST.\033[0m")

    # REST fallback
    for model_name in MODELS_TO_TRY:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}]
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            print(f"\033[90m[AI] Trying REST: {model_name}...\033[0m")
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                text = response.json()["choices"][0]["message"]["content"].strip()
                print(f"\033[92m[AI] SUCCESS via REST: {model_name}\033[0m")
                return text
            print(f"\033[93m[AI] REST {model_name} -> {response.status_code}: {response.text}\033[0m")
        except Exception as e:
            print(f"\033[91m[AI] REST failed for {model_name}: {e}\033[0m")
            continue
    return None


def _parse_json(text: str) -> Optional[Dict]:
    """Clean markdown fences and parse JSON."""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```json"): t = t[7:]
    elif t.startswith("```"): t = t[3:]
    if t.endswith("```"): t = t[:-3]
    t = t.strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError as e:
        print(f"\033[91m[AI] JSON parse error: {e}\033[0m")
        # Try to find JSON in the text
        start = t.find('{')
        end = t.rfind('}')
        if start != -1 and end != -1:
            try:
                return json.loads(t[start:end+1])
            except:
                pass
        start = t.find('[')
        end = t.rfind(']')
        if start != -1 and end != -1:
            try:
                return json.loads(t[start:end+1])
            except:
                pass
        return None


async def generate_project_suggestions(syllabus_text: str) -> Dict[str, Any]:
    """
    Step 1: Generate project suggestions from a syllabus.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "NOT_SET" or api_key == "gsk_your_groq_api_key_here":
        return {"error": "Groq API Key is missing. Please update your .env file."}

    prompt = f"""You are an expert project architect for computer science students.
    
    Analyze this course syllabus and suggest exactly 5 different project ideas that a student could build to demonstrate mastery of the course content. 
    
    CRITICAL: 
    - Vary the complexity: 1 Beginner, 2 Intermediate, 2 Advanced.
    - Be CREATIVE: Avoid generic "To-Do" lists or "Blog" apps unless specifically mentioned in the syllabus. 
    - Engineering Focus: Each project should require architectural thinking (database design, API structure, or complex logic).
    - Diversity: Ensure each suggestion uses a slightly different architectural pattern (e.g., Microservices, Monolithic with complex DB, Real-time with WebSockets, etc. as appropriate).

    Syllabus Content:
    {syllabus_text}
    
    Return ONLY valid JSON with this exact structure:
    {{
        "course_name": "Name of the course",
        "suggestions": [
            {{
                "id": 1,
                "title": "Project Title",
                "description": "Description here.",
                "difficulty": "Intermediate",
                "tech_stack": ["Tech1", "Tech2"],
                "key_features": ["Feature1", "Feature2"]
            }}
        ]
    }}
    Ensure exactly 5 suggestions are returned in the list. Do not include any other text or markdown formatting.
    """

    raw = _call_groq(prompt, json_mode=True)
    if raw is None:
        return {"error": "All Groq models failed. Please verify your API key and try again."}

    data = _parse_json(raw)
    if data is None:
        return {"error": "AI returned invalid JSON. Please try again."}

    return data


async def generate_full_roadmap(syllabus_text: str, chosen_project: Dict, duration_weeks: int = 4) -> Dict[str, Any]:
    """
    Step 2: Given the user's chosen project, generate a full roadmap for the specified duration.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "NOT_SET" or api_key == "gsk_your_groq_api_key_here":
        return {"error": "Groq API Key is missing. Please update your .env file."}

    prompt = f"""You are an expert project architect. A student(for his final year project) has chosen the following project for their course:

Project Title: {chosen_project.get('title', 'Untitled')}
Project Description: {chosen_project.get('description', '')}
Tech Stack: {', '.join(chosen_project.get('tech_stack', []))}
Key Features: {', '.join(chosen_project.get('key_features', []))}

Original Syllabus:
{syllabus_text}

Generate a detailed {duration_weeks}-week implementation roadmap for this project.

Return ONLY valid JSON (no markdown, no code fences) with this exact structure:
{{
    "project_title": "{chosen_project.get('title', 'Untitled')}",
    "description": "{chosen_project.get('description', '')}",
    "course_name": "Name of the course",
    "weeks": [
        {{
            "week": 1,
            "goal": "Goal for week 1",
            "milestones": ["milestone 1", "milestone 2"],
            "deliverable": "Deliverable for week 1",
            "hints": ["Hint 1"]
        }}
        // ... continue for exactly {duration_weeks} weeks
    ],
    "repo_structure": {{
        "backend": ["main.py", "models.py", "routes.py"],
        "frontend": ["index.html", "style.css", "app.js"],
        "docs": ["README.md"]
    }},
    "mysql_schema": "CREATE TABLE example (\\n  id INT PRIMARY KEY AUTO_INCREMENT,\\n  name VARCHAR(255) NOT NULL\\n);"
}}

Make the milestones specific and actionable. Each hint should help the student get started on that week's work.
If this project does not require a database (like a static HTML site), set "mysql_schema" to an empty string ""."""

    raw = _call_groq(prompt, json_mode=True)
    if raw is None:
        return {"error": "All Groq models failed. Please verify your API key and try again."}

    data = _parse_json(raw)
    if data is None:
        return {"error": "AI returned invalid JSON. Please try again."}

    return data


async def generate_roadmap(syllabus_text: str, duration_weeks: int = 4) -> Dict[str, Any]:
    """
    Legacy single-shot roadmap generation (fallback).
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "NOT_SET" or api_key == "gsk_your_groq_api_key_here":
        return {"error": "Groq API Key is missing. Please update your .env file."}

    prompt = f"""You are an expert project architect. Analyze this course syllabus and generate a structured 4-week project plan.

Syllabus Content:
{syllabus_text}

Generate a structured {duration_weeks}-week project plan.

Return ONLY valid JSON (no markdown, no code fences) with this exact structure:
{{
    "project_title": "A descriptive project title",
    "description": "Brief project description",
    "course_name": "Name of the course",
    "weeks": [
        {{
            "week": 1,
            "goal": "Goal for week 1",
            "milestones": ["milestone 1"],
            "deliverable": "Deliverable for week 1",
            "hints": ["Hint 1"]
        }}
        // ... continue for exactly {duration_weeks} weeks
    ],
    "repo_structure": {{
        "backend": ["main.py", "models.py", "routes.py"],
        "frontend": ["index.html", "style.css", "app.js"],
        "docs": ["README.md"]
    }},
    "mysql_schema": "CREATE TABLE example (id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(255));"
}}

If this project does not require a database, set "mysql_schema" to an empty string ""."""

    raw = _call_groq(prompt, json_mode=True)
    if raw is None:
        return {"error": "All Groq models failed. Please verify your API key and try again."}

    data = _parse_json(raw)
    if data is None:
        return {"error": "AI returned invalid JSON. Please try again."}

    return data


async def stream_code_review(milestone_goals: str, code_content: str) -> AsyncGenerator[str, None]:
    """Provides AI feedback on submitted code."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "gsk_your_groq_api_key_here":
        yield "Error: No API key configured."
        return

    prompt = f"""You are a senior engineer reviewing a student's weekly code submission. Be concise and direct.

Context — Milestone Goals: {milestone_goals}

Student's Code:
```
{code_content}
```

RESPOND IN THIS EXACT FORMAT (keep it SHORT — max 250 words total):

[SCORE: X.X / 10]

## Verdict
One sentence summary of overall quality. Use an encouraging but honest tone.

## What You Nailed
2-3 bullet points of what was done well. Be specific.

## What Needs Work
2-3 bullet points of concrete issues. Reference specific code if possible.

## Quick Wins
1-2 small, actionable improvements they can make right now (with brief code snippet if helpful).

RULES:
- Score MUST be the very first line
- Keep each section to 2-3 bullet points MAX
- No filler phrases like "Great job overall!" — be direct
- Use markdown formatting (**, `, ##)
- Total response under 250 words"""

    raw = _call_groq(prompt, json_mode=False)
    if raw:
        yield raw
    else:
        yield "Error: AI Review engine currently offline."


async def extract_text_from_pdf(content: bytes) -> str:
    doc = fitz.open(stream=content, filetype="pdf")
    text = ""
    for page in doc: text += page.get_text()
    return text

async def extract_text_from_docx(content: bytes) -> str:
    doc = Document(io.BytesIO(content))
    return "\n".join([para.text for para in doc.paragraphs])


async def analyze_resume_ats(resume_text: str, target_role: str) -> Dict[str, Any]:
    """
    Analyzes a candidate's resume against a target job role.
    Returns structured suggestions, score, gap list, and bullet point improvements.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "NOT_SET" or api_key == "gsk_your_groq_api_key_here":
        return {"error": "Groq API Key is missing. Please update your .env file."}

    # --- Pre-flight: Ask AI to confirm this is actually a resume ---
    preflight_prompt = f"""You are a strict document classifier. Your ONLY job: is the text below a resume or CV?

A resume/CV has: a person's name, contact info, work experience or projects, education, skills sections.
NOT a resume: essays, stories, articles, code files, invoices, assignments, letters, random text.

Respond ONLY with valid JSON, nothing else:
{{"is_resume": true}} — if it IS a resume/CV
{{"is_resume": false}} — if it is NOT a resume/CV

Document (first 1500 chars):
{resume_text[:1500]}"""

    preflight_raw = _call_groq(preflight_prompt, json_mode=True)
    if preflight_raw:
        preflight = _parse_json(preflight_raw)
        if preflight and preflight.get("is_resume") is False:
            return {"not_resume": True}

    prompt = f"""You are an elite, senior technical recruiter and ATS (Applicant Tracking System) specialist.
    
    Evaluate the following candidate's resume content against the target job role: "{target_role}".
    Provide a highly objective, mathematical, and actionable ATS audit.
    
    CRITICAL INSTRUCTIONS:
    - Target Role Alignment: Look for specific keywords, libraries, databases, architectures, and practices expected for a modern "{target_role}" candidate.
    - SCORE CALCULATION (most important — DO NOT use a placeholder value):
        * You MUST calculate the "score" integer yourself by evaluating the actual resume text provided below.
        * Count matching vs. missing technical keywords, assess bullet point quality, check for quantified achievements.
        * Score range: 0-100. 85+ = interview-ready, 70-84 = good but has gaps, 50-69 = needs work, <50 = significant technical gaps.
        * NEVER use 74, 75, or any hardcoded number — compute a unique, accurate score for THIS specific resume.
    - STAR Bullet Improvements: Identify 3 bullet points in the resume that are weak, passive, or lack impact. Rewrite them using the STAR (Situation, Task, Action, Result) methodology. Provide the original, the improved version, and a brief 1-sentence rationale explaining why it is better.
    - Gaps & Missing Skills: Highlight 4-6 specific technical skills (languages, frameworks, architectures, databases, or patterns) that are expected for a "{target_role}" but are missing or underrepresented in their current resume.
      CRITICAL: Provide a highly detailed, rich, and constructive explanation of the gap and why it is critical for a "{target_role}" candidate.
    - Strengths: Highlight 3 specific strong engineering achievements or positive traits ACTUALLY PRESENT in the resume.
      CRITICAL: Write each strength as a short, active phrase (8-15 words max). Do NOT invent strengths not found in the resume.
    - Recommended Skill Fillers: Provide 2-3 gentle, non-mandatory, specific project suggestions or study focus areas they could build to naturally fill these gaps.
    
    Resume Text:
    ---START RESUME---
    {resume_text}
    ---END RESUME---
    
    Return ONLY valid JSON with this exact structure (replace ALL placeholder values with real computed data):
    {{
        "score": <COMPUTE A REAL INTEGER 0-100 BASED ON THE RESUME ABOVE>,
        "role": "{target_role}",
        "summary": "A concise, high-impact 2-3 sentence paragraph (around 45-60 words) summarizing candidate alignment and key focus areas.",
        "strengths": [
            "Real strength 1 found in resume (8-15 words)",
            "Real strength 2 found in resume (8-15 words)",
            "Real strength 3 found in resume (8-15 words)"
        ],
        "gaps": [
            "Detailed missing keyword gap 1 with actionable explanation",
            "Detailed missing keyword gap 2 with actionable explanation",
            "Detailed missing keyword gap 3 with actionable explanation"
        ],
        "bullet_improvements": [
            {{
                "original": "An actual weak bullet from the resume above.",
                "improved": "Rewritten STAR-method version with active verbs and quantified results.",
                "rationale": "One sentence explaining what was improved and why."
            }}
        ],
        "suggested_projects": [
            {{
                "title": "Specific project title",
                "description": "Short 1-2 sentence description targeting the missing skills.",
                "tech_stack": ["Tech1", "Tech2"]
            }}
        ]
    }}
    IMPORTANT: The "score" field MUST be a real integer you calculated, NOT a template placeholder. Ensure the JSON is strictly valid.
    """

    raw = _call_groq(prompt, json_mode=True)
    if raw is None:
        return {"error": "All Groq models failed. Please verify your API key."}

    data = _parse_json(raw)
    if data is None:
        return {"error": "AI returned invalid JSON evaluation. Please try again."}

    return data


async def stream_mock_interview(project_title: str, schema: str, repo: dict, checkins: list, history: list) -> AsyncGenerator[str, None]:
    """
    Manages the mock interview state, evaluates responses, handles strikes,
    and returns a streaming chat response.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "gsk_your_groq_api_key_here":
        yield "Error: No API key configured."
        return

    # Formulate recent checkins review summary for the AI
    checkin_summary = ""
    if checkins:
        for idx, c in enumerate(checkins):
            checkin_summary += f"- Week {c.get('week_number', idx+1)} (Status: {c.get('status', 'unknown')}): Feedback Summary: {c.get('ai_feedback', '')[:200]}...\n"
    else:
        checkin_summary = "No code check-ins completed yet."

    # Parse state from history
    strike_count = 0
    question_count = 0
    
    # We ignore the very first greeting in some counts, but let's count all assistant messages as turns
    for msg in history:
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if "[STRIKE]" in content:
                strike_count += 1
            question_count += 1

    # Format history for Gemini context
    chat_formatted = ""
    for msg in history:
        role = "Student (Candidate)" if msg.get("role") == "user" else "Interviewer (FAANG Lead)"
        chat_formatted += f"{role}: {msg.get('content')}\n"

    prompt = f"""You are a strict, elite FAANG Lead Software Engineer conducting a high-pressure technical mock interview.
Your candidate is a student presenting their milestone project: "{project_title}".

Project Technical Blueprint:
- Folder structure & Repository layout: {json.dumps(repo or {})}
- MySQL DDL Database Schema: {schema or "No relational database schema used."}
- Candidate's Weekly Check-ins & Code Quality:
{checkin_summary}

---
INTERVIEW STATE (Calculated):
- Current Technical Questions Asked: {question_count}
- Current Candidate Strikes: {strike_count} / 3
---

Interviewing Directives:
1. Grill the student deeply on their system architecture, normalization decisions, potential scaling bottlenecks, race conditions, edge case validation, security holes, and choices of technologies.
2. Ask ONE technical, challenging question at a time.
3. Be professional, slightly tough but supportive, just like a real Senior FAANG engineer. Keep responses concise (under 120 words).
4. Do NOT output long paragraphs. Use clear, direct sentences.
5. Answer Verification & Strikes:
   - Actively evaluate the student's last response.
   - If their response is technically incorrect, evasive, complete nonsense (e.g. key-mashing "asdfasdf" or completely off-topic), or they admit they do not know, you MUST call them out on it and append `[STRIKE]` at the very end of your response text.
   - If they answered exceptionally well, award them Skill Points by including `[XP: +X]` (X is 15 to 30 based on answer quality). Do not award XP if their answer was mediocre or had strikes.
6. Termination Rule:
   - If the student reaches 3 total strikes (i.e. strike_count + new strike == 3), you must immediately terminate the interview.
   - State that the interview has failed due to insufficient technical knowledge, and append `[TERMINATED]` at the absolute end of your response. Do not ask any more questions.
7. Completion Rule:
   - If the candidate reaches 5 questions asked without hitting 3 strikes, you must successfully conclude the interview, congratulate them, give a brief technical summary of their strengths, and append `[PASSED]` at the absolute end of your response. Do not ask any more questions.
8. Read the conversation history to avoid repeating your questions.

Chat History:
{chat_formatted}

Provide your next response as the Interviewer. Speak directly as the interviewer, do not speak for the candidate."""

    raw = _call_groq(prompt, json_mode=False)
    if raw:
        yield raw
    else:
        yield "Error: Mock interview engine offline."

