"""Sends email through SMTP when configured (used for password recovery)."""
import smtplib
from email.message import EmailMessage

from config import Config


def configured():
    return bool(Config.SMTP_HOST)


def send(to, subject, body):
    if not configured():
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = Config.MAIL_FROM, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=15) as smtp:
            smtp.starttls()
            if Config.SMTP_USER:
                smtp.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError):
        return False
