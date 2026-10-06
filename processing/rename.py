import os
import re
from utils.validation import sanitize_filename


def apply_rename_template(template: str, context: dict) -> str:
    """
    Apply a rename template with {key} placeholders.
    Context keys: name, title, year, author, size, user
    Returns a sanitized filename (without extension).
    """
    def replacer(match):
        key = match.group(1).strip()
        return str(context.get(key, ""))

    result = re.sub(r"\{(\w+)\}", replacer, template)
    result = sanitize_filename(result)
    return result


def build_filename(
    original_path: str,
    template: str | None,
    context: dict,
) -> str:
    """
    Return the final filename for a file.
    If template is given, apply it and keep the original extension.
    """
    original_name = os.path.basename(original_path)
    base, ext = os.path.splitext(original_name)

    if template:
        context.setdefault("name", base)
        new_base = apply_rename_template(template, context)
        return (new_base or base) + ext

    return original_name
