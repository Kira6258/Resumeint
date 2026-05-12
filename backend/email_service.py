import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_real_email(to_email: str, subject: str, body: str):
    """
    Sends a real email using SMTP configuration from environment variables.
    """
    smtp_server = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("MAIL_PORT", "587"))
    smtp_user = os.getenv("MAIL_USERNAME")
    smtp_password = os.getenv("MAIL_PASSWORD")
    from_email = os.getenv("MAIL_FROM", smtp_user)

    if not all([smtp_user, smtp_password]):
        print("\033[91m[EMAIL ERROR] SMTP credentials missing in .env!\033[0m")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        
        print(f"\033[92m[EMAIL] Sent successfully to {to_email}\033[0m")
        return True
    except Exception as e:
        print(f"\033[91m[EMAIL ERROR] Failed to send: {e}\033[0m")
        return False
