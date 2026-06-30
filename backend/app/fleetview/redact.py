"""PII / identifier redaction for text sent to external LLMs.

Removes UUIDs, VINs, and email addresses from arbitrary strings so that raw
identifiers are never transmitted to the Anthropic API.

No DB access.  No tier_a imports.
"""
from __future__ import annotations

import re

# RFC 4122 UUID (all variants)
_UUID_RE = re.compile(
    r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}'
    r'-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'
)

# ISO 3779 VIN: 17 chars, uppercase letters (excl. I, O, Q) and digits
_VIN_RE = re.compile(r'\b[A-HJ-NPR-Z0-9]{17}\b')

# Email address (simple pattern sufficient for redaction)
_EMAIL_RE = re.compile(r'\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b')


def redact(text: str) -> str:
    """Return *text* with UUIDs, VINs, and emails replaced by placeholders."""
    text = _UUID_RE.sub("[id]", text)
    text = _VIN_RE.sub("[vin]", text)
    text = _EMAIL_RE.sub("[email]", text)
    return text
