"""
Utilities for parsing embedded data blocks from agent response text.
Used by both the Streamlit UI and the FastAPI layer.
"""

import json
import re
from typing import Any


_DATA_BLOCK_RE = re.compile(r"```data\n(.*?)\n```", re.DOTALL)


def parse_data_blocks(text: str) -> tuple[str, list[dict[str, Any]]]:
    """
    Extract all ```data ... ``` blocks from agent response text.

    Returns:
        (cleaned_text, list_of_parsed_blocks)
        cleaned_text has the data blocks stripped out.
    """
    blocks: list[dict[str, Any]] = []

    def _extract(match: re.Match) -> str:
        try:
            blocks.append(json.loads(match.group(1)))
        except json.JSONDecodeError:
            pass
        return ""

    cleaned = _DATA_BLOCK_RE.sub(_extract, text).strip()
    return cleaned, blocks
