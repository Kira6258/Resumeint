import os
import sys
import secrets

def setup():
    print("\033[94m")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║                                                          ║")
    print("║                Resumeint SETUP WIZARD                  ║")
    print("║                                                          ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print("\033[0m")

    print("[1/2] Configuring Environment...")
    
    # Get the key from user
    api_key = input("\n\033[96mEnter your Google Gemini API Key (from aistudio.google.com):\033[0m\n> ").strip()
    
    if not api_key.startswith("AIza"):
        print("\033[93m[WARNING] That doesn't look like a valid Google API Key. Proceed anyway? (y/n)\033[0m")
        if input("> ").lower() != 'y':
            print("Setup cancelled.")
            return

    # Generate a cryptographically secure JWT secret
    jwt_secret = secrets.token_urlsafe(48)

    # Create .env file
    env_content = f"""# Resumeint Environment Variables
DATABASE_URL=mysql+pymysql://root:1234@localhost:3306/course_to_project
JWT_SECRET={jwt_secret}
GEMINI_API_KEY={api_key}

# --- Razorpay (get from https://dashboard.razorpay.com) ---
# RAZORPAY_KEY_ID=rzp_test_XXXXXXXXXXXX
# RAZORPAY_KEY_SECRET=XXXXXXXXXXXXXXXXXXXXXX

# --- GitHub Sync (get from https://github.com/settings/tokens) ---
# GITHUB_TOKEN=ghp_XXXXXXXXXXXXXXXXXXXXXX

# --- Production ONLY settings (uncomment when deploying) ---
# ENV=production
# BASE_URL=https://yourdomain.com
# ALLOWED_ORIGINS=https://yourdomain.com
"""
    
    try:
        with open(".env", "w") as f:
            f.write(env_content)
        print("\033[92m[OK] .env file created with a secure random JWT secret!\033[0m")
    except Exception as e:
        print(f"\033[91m[ERROR] Failed to create .env file: {e}\033[0m")
        return

    print("\n[2/2] Verifying Dependencies...")
    try:
        import google.generativeai
        print("\033[92m[OK] Google AI library found.\033[0m")
    except ImportError:
        print("\033[93m[INFO] Google AI library missing. Running automatic installation...\033[0m")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "google-generativeai"])
        print("\033[92m[OK] Dependencies installed.\033[0m")

    print("\n\033[92m✨ SETUP COMPLETE! ✨\033[0m")
    print("You can now start the app by running:")
    print("\033[96mpython run.py\033[0m")

if __name__ == "__main__":
    # Enable ANSI colors on Windows
    if os.name == 'nt':
        os.system('color')
    setup()

