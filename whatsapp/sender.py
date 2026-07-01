import webbrowser
import urllib.parse

WHATSAPP_AVAILABLE = True


def _build_url(phone, message):
    return f"https://web.whatsapp.com/send?phone={phone}&text={urllib.parse.quote(message)}"


def send_welcome_message(phone, name, plan, joining_date, expiry_date, return_url=False):
    message = f"""Welcome to Fitness Empire, {name}!

Thank you for joining us! Here are your membership details:

Plan: {plan}
Joining Date: {joining_date}
Expiry Date: {expiry_date}

We're excited to have you on board. Get ready to transform your fitness journey!

Fitness Empire"""

    url = _build_url(phone, message)
    if return_url:
        return True, url
    try:
        webbrowser.open(url)
        return True, "WhatsApp chat opened. Press Enter to send."
    except Exception as e:
        return False, str(e)


def send_balance_reminder(phone, name, amount, due_date, return_url=False):
    message = f"""Pending Balance Reminder

Hi {name},

You have a pending balance of ₹{amount} due on {due_date} at Fitness Empire.

Please clear your dues at the earliest to continue uninterrupted service.

Thank you,
Fitness Empire"""

    url = _build_url(phone, message)
    if return_url:
        return True, url
    try:
        webbrowser.open(url)
        return True, "WhatsApp chat opened. Press Enter to send."
    except Exception as e:
        return False, str(e)


def send_expiry_reminder(phone, name, plan, expiry_date, days_remaining, return_url=False):
    if days_remaining > 0:
        message = f"""Membership Expiry Reminder

Hi {name},

Your {plan} membership at Fitness Empire is expiring in {days_remaining} days.

Expiry Date: {expiry_date}

Please renew your membership to continue your fitness journey without interruption!

Fitness Empire"""
    else:
        message = f"""Membership Expired

Hi {name},

Your {plan} membership at Fitness Empire has expired today.

Expiry Date: {expiry_date}

Please renew your membership to continue accessing the gym!

Fitness Empire"""

    url = _build_url(phone, message)
    if return_url:
        return True, url
    try:
        webbrowser.open(url)
        return True, "WhatsApp chat opened. Press Enter to send."
    except Exception as e:
        return False, str(e)
