import os
import json
import requests
from typing import Optional, List, Dict, Any, AsyncGenerator
import fitz  # PyMuPDF
from docx import Document
import io

# Model priority list — tries each in order until one succeeds
MODELS_TO_TRY = [
    "models/gemini-2.5-flash",
    "models/gemini-2.0-flash",
    "models/gemini-1.5-flash",
]


def _call_gemini(prompt: str) -> Optional[str]:
    """
    Calls Gemini API 
    Returns the raw text response or None on failure.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "NOT_SET":
        return None

    # Try SDK first
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        for model_name in MODELS_TO_TRY:
            short_name = model_name.replace("models/", "")
            try:
                print(f"\033[90m[AI] Trying SDK: {short_name}...\033[0m")
                model = genai.GenerativeModel(short_name)
                response = model.generate_content(prompt)
                text = response.text.strip()
                print(f"\033[92m[AI] SUCCESS via SDK: {short_name}\033[0m")
                return text
            except Exception as e:
                print(f"\033[93m[AI] SDK {short_name} failed: {type(e).__name__}: {e}\033[0m")
                continue
    except ImportError:
        print("\033[93m[AI] google-generativeai SDK not installed, falling back to REST.\033[0m")

    # REST fallback
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    for model_name in MODELS_TO_TRY:
        for version in ["v1beta", "v1"]:
            url = f"https://generativelanguage.googleapis.com/{version}/{model_name}:generateContent?key={api_key}"
            try:
                print(f"\033[90m[AI] Trying REST: {model_name} on {version}...\033[0m")
                response = requests.post(url, json=payload, timeout=60)
                if response.status_code == 200:
                    text = response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                    print(f"\033[92m[AI] SUCCESS via REST: {model_name} on {version}\033[0m")
                    return text
                print(f"\033[93m[AI] REST {model_name} on {version} -> {response.status_code}\033[0m")
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
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "NOT_SET":
        return {"error": "Google API Key is missing. Please update your .env file."}

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

    raw = _call_gemini(prompt)
    if raw is None:
        return {"error": "All Gemini models failed. Please verify your API key and try again."}

    data = _parse_json(raw)
    if data is None:
        return {"error": "AI returned invalid JSON. Please try again."}

    return data


async def generate_full_roadmap(syllabus_text: str, chosen_project: Dict, duration_weeks: int = 4) -> Dict[str, Any]:
    """
    Step 2: Given the user's chosen project, generate a full roadmap for the specified duration.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "NOT_SET":
        return {"error": "Google API Key is missing. Please update your .env file."}

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

    raw = _call_gemini(prompt)
    if raw is None:
        return {"error": "All Gemini models failed. Please verify your API key and try again."}

    data = _parse_json(raw)
    if data is None:
        return {"error": "AI returned invalid JSON. Please try again."}

    return data


async def generate_roadmap(syllabus_text: str, duration_weeks: int = 4) -> Dict[str, Any]:
    """
    Legacy single-shot roadmap generation (fallback).
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "NOT_SET":
        return {"error": "Google API Key is missing. Please update your .env file."}

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

    raw = _call_gemini(prompt)
    if raw is None:
        return {"error": "All Gemini models failed. Please verify your API key and try again."}

    data = _parse_json(raw)
    if data is None:
        return {"error": "AI returned invalid JSON. Please try again."}

    return data


async def stream_code_review(milestone_goals: str, code_content: str) -> AsyncGenerator[str, None]:
    """Provides AI feedback on submitted code."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
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

    raw = _call_gemini(prompt)
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
