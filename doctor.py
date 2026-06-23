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
    
    # Groq
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "NOT_SET" or api_key == "gsk_your_groq_api_key_here":
        print("[X] FAIL: GROQ_API_KEY is not set or is still the placeholder in .env")
        return
        
    # Razorpay
    rzp_id = os.getenv("RAZORPAY_KEY_ID")
    rzp_secret = os.getenv("RAZORPAY_KEY_SECRET")
    if not rzp_id or rzp_id == "NOT_SET":
        print("[!] WARNING: RAZORPAY_KEY_ID is missing. Payments will fail.")
    
    print(f"[OK] .env loaded.")

    # 2. Check API Key Validity
    print("\n[2/3] Checking Groq API Key validity...")
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": "hi"}]
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            print("[OK] SUCCESS: Your Groq API Key is ACTIVE and working!")
        else:
            print(f"[X] FAIL: Groq rejected your key (Error {res.status_code})")
            print(f"    Message: {res.json().get('error', {}).get('message', 'Unknown Error')}")
            print("\n    TIP: Get a fresh key at https://console.groq.com/")
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
