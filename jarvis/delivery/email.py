"""Email delivery over SMTP+STARTTLS.

Gmail needs an App Password (Google Account -> Security -> App passwords), not the
account password, and not OAuth. The brief goes out as both plain text and a very
plain HTML part — readable on a phone, nothing to render wrong.
"""

from __future__ import annotations

import html
import re
import smtplib
from email.message import EmailMessage

DEFAULT_TIMEOUT = 30.0


class EmailError(RuntimeError):
    pass


def subject_for(date: str, brief: dict) -> str:
    """Front-load the answer so the notification alone is often enough."""
    attention = brief.get("needs_attention") or []
    if attention:
        first = (attention[0].get("what") or "").strip()
        head = f"{len(attention)} to look at" if len(attention) > 1 else (first[:60] or "1 to look at")
        return f"Jarvis {date} — {head}"
    matters = brief.get("matters") or []
    if matters:
        return f"Jarvis {date} — {len(matters)} worth knowing, nothing to do"
    return f"Jarvis {date} — nothing needs you"


_BOLD = re.compile(r"\*\*(.+?)\*\*")


def markdown_to_html(markdown: str) -> str:
    """Just enough conversion for this document's own shapes."""
    lines_out: list[str] = []
    in_list = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            if in_list:
                lines_out.append("</ul>")
                in_list = False
            continue

        if stripped.startswith("# "):
            if in_list:
                lines_out.append("</ul>")
                in_list = False
            lines_out.append(f"<h2>{html.escape(stripped[2:])}</h2>")
            continue
        if stripped.startswith("## "):
            if in_list:
                lines_out.append("</ul>")
                in_list = False
            lines_out.append(f"<h3>{html.escape(stripped[3:])}</h3>")
            continue

        if stripped.startswith("- "):
            if not in_list:
                lines_out.append("<ul>")
                in_list = True
            body = _inline(stripped[2:])
            lines_out.append(f"<li>{body}</li>")
            continue

        if in_list:  # continuation line of the previous bullet
            lines_out[-1] = lines_out[-1].replace("</li>", f"<br>{_inline(stripped)}</li>")
            continue

        if stripped.startswith("> "):
            lines_out.append(f'<p style="color:#8a6d3b">{_inline(stripped[2:])}</p>')
            continue

        lines_out.append(f"<p>{_inline(stripped)}</p>")

    if in_list:
        lines_out.append("</ul>")

    body = "\n".join(lines_out)
    return (
        '<html><body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
        'font-size:15px;line-height:1.5;color:#1b1b1d;max-width:640px">'
        f"{body}</body></html>"
    )


def _inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = _BOLD.sub(r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"_(.+?)_", r"<em>\1</em>", escaped)
    return escaped


def send(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    sender: str,
    to: str,
    subject: str,
    markdown: str,
    timeout: float = DEFAULT_TIMEOUT,
    smtp_factory=None,
) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to
    message.set_content(markdown)
    message.add_alternative(markdown_to_html(markdown), subtype="html")

    factory = smtp_factory or (lambda: smtplib.SMTP(host, port, timeout=timeout))
    try:
        with factory() as smtp:
            smtp.ehlo()
            if smtp.has_extn("starttls"):
                smtp.starttls()
                smtp.ehlo()
            smtp.login(user, password)
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise EmailError(
            "SMTP login rejected — for Gmail this must be an App Password, not your account password"
        ) from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailError(f"could not send email: {exc}") from exc
