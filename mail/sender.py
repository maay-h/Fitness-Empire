import json
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, HtmlContent

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')

MAIL_AVAILABLE = False
SENDGRID_API_KEY = ''


def load_config():
    global MAIL_AVAILABLE, SENDGRID_API_KEY
    SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY', '')
    if not SENDGRID_API_KEY:
        try:
            with open(CONFIG_PATH, 'r') as f:
                cfg = json.load(f)
            SENDGRID_API_KEY = cfg.get('sendgrid', {}).get('api_key', '') or SENDGRID_API_KEY
        except:
            pass
    MAIL_AVAILABLE = bool(SENDGRID_API_KEY)


LOGO_URL = "https://raw.githubusercontent.com/BhuvanR10/fitness/refs/heads/main/2023-12-23.png"
GYM_ADDRESS = "F-27/1C, 16th Main, opp. Kalyani Motors, beside NIE College, Vidyaranyapura, Mysuru, Visveshwara Nagar, Karnataka 570008"
GYM_PHONE = "078290 73184"
GYM_YEAR = os.getenv('GYM_YEAR', str(__import__('datetime').datetime.now().year))


def _base_template(title, body):
    import datetime
    year = datetime.datetime.now().year
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8" />
    <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:Arial,Helvetica,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td align="center" style="padding:30px 0;">

      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;">

        <!-- HEADER -->
        <tr>
          <td style="background:#111827;padding:20px;text-align:center;">

            <img
                src="{LOGO_URL}"
                alt="Gym Logo"
                width="120"
                style="display:block;margin:0 auto 10px;"
            />

            <h2 style="margin:0;color:#ffffff;">Fitness Empire</h2>
            <p style="margin:5px 0 0;font-size:14px;color:#d1d5db;">
                Fitness &bull; Strength &bull; Health &bull; Zumba
            </p>
          </td>
        </tr>

        <!-- BODY -->
        <tr>
          <td style="padding:30px;color:#333333;">
            {body}
          </td>
        </tr>

        <!-- FOOTER -->
        <tr>
          <td style="background:#f1f5f9;padding:15px;text-align:center;font-size:12px;color:#555;">
            &copy; {year} Fitness Empire <br/>
            &#128205; {GYM_ADDRESS} | &#128222; {GYM_PHONE}
          </td>
        </tr>

      </table>

    </td>
  </tr>
</table>

</body>
</html>"""


def _welcome_body(name, plan, end_date):
    return f"""
    <h3>Hello {name},</h3>
    <p>Welcome to <strong>Fitness Empire</strong>! We are excited to have you.</p>

    <p><strong>Membership Plan:</strong> {plan}</p>
    <p><strong>Valid Till:</strong> {end_date}</p>

    <p>Stay consistent, stay strong &#128170;</p>

    <p style="margin-top:30px;">
      Regards,<br/>
      <strong>Gym Admin</strong>
    </p>
    """


def _expiry_body(name, days_left, end_date):
    if days_left == 7:
        message = f"Your membership will expire in <strong>7 days</strong>."
    elif days_left == 3:
        message = f"Your membership will expire in <strong>3 days</strong>."
    elif days_left == 1:
        message = f"Your membership will expire <strong>tomorrow</strong>."
    else:
        message = f"Your membership <strong>expires today</strong>."

    return f"""
    <h3>Hello {name},</h3>
    <p>{message}</p>

    <p><strong>Expiry Date:</strong> {end_date}</p>

    <p>Please renew your membership to continue enjoying gym services.</p>

    <p style="margin-top:30px;">
      &#128170; <strong>Your Gym Team</strong>
    </p>
    """


def _send_email(to_email, subject, html_body):
    global MAIL_AVAILABLE, SENDGRID_API_KEY
    if not MAIL_AVAILABLE:
        load_config()
    if not MAIL_AVAILABLE:
        return False, "SendGrid not configured. Set SENDGRID_API_KEY environment variable."

    message = Mail(
        from_email=Email(os.environ.get('FROM_EMAIL', 'noreply@fitnessempiremysuru.in')),
        to_emails=To(to_email),
        subject=subject,
        html_content=HtmlContent(html_body)
    )

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        if response.status_code in (200, 201, 202):
            return True, "Email sent successfully"
        return False, f"SendGrid error: {response.status_code}"
    except Exception as e:
        return False, str(e)


def send_welcome_email(to_email, name, plan, joining_date, expiry_date):
    subject = f"Welcome to Fitness Empire, {name}!"
    html = _base_template("Welcome to Our Gym", _welcome_body(name, plan, expiry_date))
    return _send_email(to_email, subject, html)


def _balance_body(name, amount, due_date):
    return f"""
    <h3>Hello {name},</h3>
    <p>This is a reminder regarding your <strong>pending balance</strong> at Fitness Empire.</p>

    <p><strong>Amount Due:</strong> ₹{amount}</p>
    <p><strong>Due Date:</strong> {due_date}</p>

    <p>Please clear your dues at the earliest to continue enjoying our services without interruption.</p>

    <p style="margin-top:30px;">
      &#128170; <strong>Your Gym Team</strong>
    </p>
    """


def send_balance_reminder_email(to_email, name, amount, due_date):
    subject = f"Pending Balance Reminder - {name}"
    html = _base_template("Pending Balance Reminder", _balance_body(name, amount, due_date))
    return _send_email(to_email, subject, html)


def send_expiry_reminder_email(to_email, name, plan, expiry_date, days_remaining):
    if days_remaining > 0:
        subject = f"Membership Expiry Reminder - {name}"
    else:
        subject = f"Membership Expired - {name}"
    html = _base_template("Membership Expiry Reminder", _expiry_body(name, days_remaining, expiry_date))
    return _send_email(to_email, subject, html)
