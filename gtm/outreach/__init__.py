"""Outreach stage — generate personalized emails + Outlook-ready .eml drafts."""

from .runner import run_outreach
from .email_gen import generate_email, render_template
from .eml import write_eml

__all__ = ["run_outreach", "generate_email", "render_template", "write_eml"]
