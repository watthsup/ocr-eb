"""Loads prompt templates from app/prompts/*.md and fills `<<PLACEHOLDER>>` tokens (brace-safe for Thai/markdown)."""

from __future__ import annotations

import os
from functools import lru_cache

PROMPT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    with open(os.path.join(PROMPT_DIR, f"{name}.md"), "r", encoding="utf-8") as fh:
        return fh.read().strip()


def render(name: str, **placeholders: str) -> str:
    text = load_prompt(name)
    for key, value in placeholders.items():
        text = text.replace(f"<<{key}>>", value)
    return text
