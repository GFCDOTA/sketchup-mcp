import re

def slugify(text: str) -> str:
    return re.sub(r" +", "-", text.strip().lower())
