import subprocess
import os
import sys
import importlib.util

def print_banner():
    """Prints a professional banner for the application."""
    banner = """
    \033[94m
    ╔══════════════════════════════════════════════════════════╗
    ║                                                          ║
    ║                Resumeint PROJECT RUNNER                ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    \033[0m
    """
    print(banner)

def install_requirements():
    """Attempts to install missing requirements."""
    print("\033[94m[INFO] Installing missing dependencies from backend/requirements.txt...\033[0m")
    print("\033[90mThis may take a minute. Trying to find pre-built binaries to avoid build errors.\033[0m")
    
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "backend/requirements.txt"])
        print("\033[92m[OK] Dependencies installed successfully!\033[0m")
        return True
    except Exception as e:
        print(f"\033[91m[ERROR] Failed to install dependencies: {e}\033[0m")
        return False

def check_requirements():
    """Checks if basic requirements are met."""
    print("\033[90m[INFO] Checking environment...\033[0m")
    
    # Check for .env file in root (Keeping it separate)
    if not os.path.exists(".env"):
        print("\033[93m[WARNING] .env file not found in root directory!\033[0m")
        print("Please run 'python setup.py' to configure your environment.")
    else:
        # Check if GEMINI_API_KEY is present
        with open(".env", "r") as f:
            if "GEMINI_API_KEY" not in f.read():
                print("\033[93m[WARNING] GEMINI_API_KEY not found in .env!\033[0m")
                print("Please run 'python setup.py' to add your free Google API key.")
            else:
                print("\033[92m[OK] Environment variables (.env) ready.\033[0m")


    # Check if core dependencies are installed
    core_modules = ["uvicorn", "fastapi", "pydantic", "email_validator", "requests"]


    missing = []
    
    for m in core_modules:
        try:
            importlib.import_module(m.replace("-", "_"))
        except ImportError:
            missing.append(m)
    
    if missing:
        print(f"\033[93m[INFO] Missing dependencies: {', '.join(missing)}. Attempting automatic installation...\033[0m")
        if not install_requirements():
            print("\033[91m[ERROR] Could not prepare environment. Please run 'pip install -r backend/requirements.txt' manually.\033[0m")
            sys.exit(1)
    else:
        print("\033[92m[OK] Core dependencies found.\033[0m")



def start_server():
    """Launches the FastAPI server."""
    print("\033[94m[INFO] Starting FastAPI backend (Uvicorn)...\033[0m")
    print("\033[90m[INFO] App will be accessible at: \033[96mhttp://127.0.0.1:8000\033[0m")
    print("-" * 60)
    
    # Change directory to backend to ensure imports work correctly
    # Use absolute path to avoid confusion if script is moved
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(os.path.join(script_dir, "backend"))
    
    try:
        # Use sys.executable -m uvicorn for better compatibility and reliable pathing
        subprocess.run([sys.executable, "-m", "uvicorn", "main:app", "--reload", "--port", "8000"])
    except KeyboardInterrupt:
        print("\n\033[93m[INFO] Stopping Resumeint...\033[0m")
    except Exception as e:
        print(f"\033[91m[ERROR] Failed to start server: {e}\033[0m")
        sys.exit(1)

if __name__ == "__main__":
    # Enable ANSI colors and UTF-8 on Windows
    if os.name == 'nt':
        os.system('color')
        os.system('chcp 65001 >nul 2>&1')
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        
    print_banner()
    check_requirements()
    start_server()
