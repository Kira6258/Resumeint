import os
import requests
from dotenv import load_dotenv
import sys

def check_setup():
    print("\n" + "="*50)
    print("        Resumeint SETUP DIAGNOSTIC")
    print("="*50 + "\n")

    # 1. Check .env
    print("[1/3] Checking .env file...")
    if not os.path.exists(".env"):
        print("[X] FAIL: .env file not found!")
        return
    load_dotenv(".env")
    
    # Gemini
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "NOT_SET":
        print("[X] FAIL: GEMINI_API_KEY is not set in .env")
        return
        
    # Razorpay
    rzp_id = os.getenv("RAZORPAY_KEY_ID")
    rzp_secret = os.getenv("RAZORPAY_KEY_SECRET")
    if not rzp_id or rzp_id == "NOT_SET":
        print("[!] WARNING: RAZORPAY_KEY_ID is missing. Payments will fail.")
    
    print(f"[OK] .env loaded.")

    # 2. Check API Key Validity
    print("\n[2/3] Checking Gemini API Key validity...")
    # Trying v1beta which is common for AI Studio keys
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": "hi"}]}]}, timeout=10)
        if res.status_code == 200:
            print("[OK] SUCCESS: Your API Key is ACTIVE and working!")
        else:
            print(f"[X] FAIL: Google rejected your key (Error {res.status_code})")
            print(f"    Message: {res.json().get('error', {}).get('message', 'Unknown Error')}")
            print("\n    TIP: Get a fresh key at https://aistudio.google.com/app/apikey")
    except Exception as e:
        print(f"[X] FAIL: Connection error ({e})")

    # 3. Check Database
    print("\n[3/3] Checking Database...")
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("[X] FAIL: DATABASE_URL not set.")
    else:
        print(f"[OK] Database URL configured.")

    print("\n" + "="*50)
    print("   Ready? Restart 'python run.py' and enjoy!")
    print("="*50 + "\n")

if __name__ == "__main__":
    check_setup()
