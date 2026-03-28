import smtplib
from email.mime.text import MIMEText

SMTP_HOST = "localhost"
SMTP_PORT = 25
FROM_ADDRESS = "noreply@dullknife.com"
ADMIN_EMAIL = "john@dullknife.com"
SITE_URL = "https://www.dullknife.com"


def send_email(to, subject, body, from_addr=FROM_ADDRESS):
    """Send a plain-text email. `to` can be a string or list of strings."""
    if isinstance(to, str):
        to = [to]
    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.sendmail(from_addr, to, msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}", flush=True)
        return False


def send_password_reset(to_email, reset_url):
    subject = "Dullknife — Password Reset Request"
    body = f"""\
You requested a password reset for your Dullknife Developer Alliance account.

Click the link below to set a new password. This link expires in 20 minutes.

{reset_url}

If you did not request a password reset, you can safely ignore this email.

— The Dullknife Team
{SITE_URL}
"""
    return send_email(to_email, subject, body)


def send_contact_us_notification(name, email, phone, message):
    subject = f"Contact Form — {name}"
    body = f"""\
A visitor has submitted the Dullknife contact form.

Name:    {name}
Email:   {email}
Phone:   {phone or 'Not provided'}

Message:
{message}
"""
    return send_email(ADMIN_EMAIL, subject, body)


def send_contact_member_message(member_email, member_name,
                                 first_name, last_name, organization,
                                 email, phone_1, phone_2,
                                 city, state, zipcode, country, message):
    subject = f"Dullknife Message from {first_name} {last_name}"
    location_parts = [p for p in [city, state, zipcode] if p]
    location = ", ".join(location_parts)
    if country and country != "United States":
        location = f"{location} — {country}" if location else country

    body = f"""\
You have received a message through your Dullknife profile.

From:         {first_name} {last_name}
Organization: {organization or 'Not provided'}
Email:        {email}
Phone 1:      {phone_1 or 'Not provided'}
Phone 2:      {phone_2 or 'Not provided'}
Location:     {location or 'Not provided'}

Message:
{message}

---
Reply directly to {email} to respond.
"""
    return send_email(member_email, subject, body)


def send_approval_email(to_email, first_name, username):
    subject = "Welcome to Dullknife — Application Approved"
    body = f"""\
Hi {first_name},

Great news! Your application to join the Dullknife Developer Alliance has been approved.

You can log in now at {SITE_URL}/login using:

  Username:  {username}
  Password:  temporary

You will be prompted to set a new password on your first login.

Welcome aboard!
— The Dullknife Team
{SITE_URL}
"""
    return send_email(to_email, subject, body)


def send_rejection_email(to_email, first_name):
    subject = "Dullknife — Membership Application Update"
    body = f"""\
Hi {first_name},

Thank you for your interest in the Dullknife Developer Alliance.

After careful review, we are unable to approve your membership application at this time.

If you have questions or would like more information, please reach out to us at:
{SITE_URL}/contact

— The Dullknife Team
{SITE_URL}
"""
    return send_email(to_email, subject, body)


def send_group_email(members, subject, message):
    """Send `message` individually to each member dict with keys email/first_name."""
    sent = 0
    for m in members:
        body = f"Hi {m['first_name']},\n\n{message}\n\n— The Dullknife Team\n{SITE_URL}"
        if send_email(m["email"], subject, body):
            sent += 1
    return sent
