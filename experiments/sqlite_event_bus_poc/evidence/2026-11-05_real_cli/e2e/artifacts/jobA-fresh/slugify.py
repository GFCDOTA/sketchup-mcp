import re


def slugify(text: str) -> str:
    text = text.strip()
    text = text.lower()
    text = re.sub(r' +', '-', text)
    return text
