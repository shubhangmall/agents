import os
from html import escape

import sendgrid
from sendgrid.helpers.mail import Content, Email, Mail, To


def send_email(subject: str, markdown_report: str) -> dict[str, str]:
    """Send a report only when the caller explicitly enables this optional action."""
    api_key = os.environ.get("SENDGRID_API_KEY")
    if not api_key:
        raise RuntimeError("SENDGRID_API_KEY is not configured")

    sg = sendgrid.SendGridAPIClient(api_key=api_key)
    mail = Mail(
        Email("shubhangm96@gmail.com"),
        To("shubhangm96@gmail.com"),
        subject,
        Content("text/html", f"<pre>{escape(markdown_report)}</pre>"),
    ).get()
    response = sg.client.mail.send.post(request_body=mail)
    print("Email response", response.status_code)
    return {"status": "success"}
