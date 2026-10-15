"""Owner-addressed feature requests; no user-controlled recipient or mail headers."""
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
import smtplib
import ssl


def request_message(user, text, sender, now=None):
    text = text.strip()
    if not 5 <= len(text) <= 4000:
        raise ValueError('Please write between 5 and 4,000 characters.')
    if not user.get('email') or user.get('email_verified') is False:
        raise ValueError('Please sign in before submitting a request.')
    now = now or datetime.now(timezone.utc)
    message = EmailMessage()
    message['From'] = formataddr(('Asheville Soundcheck', sender))
    message['To'] = sender
    message['Subject'] = 'Asheville Soundcheck — Feature request'
    message['Message-ID'] = make_msgid(domain='gmail.com')
    message.set_content('User: '+str(user.get('name') or 'Unnamed')+'\nEmail: '+str(user['email'])+
                        '\nSubmitted: '+now.isoformat()+'\n\nRequest:\n'+text)
    return message


def submit(user, text, sender, password):
    if not sender or not password:
        raise RuntimeError('Request delivery is not configured.')
    message = request_message(user, text, sender)
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=ssl.create_default_context(), timeout=12) as smtp:
        smtp.login(sender, password.replace(' ', ''))
        smtp.send_message(message)
    return message['Message-ID']
