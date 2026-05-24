import re
import unicodedata

_TURKISH_MAP = str.maketrans(
    {
        "ş": "s",
        "Ş": "S",
        "ğ": "g",
        "Ğ": "G",
        "ı": "i",
        "İ": "I",
        "ö": "o",
        "Ö": "O",
        "ü": "u",
        "Ü": "U",
        "ç": "c",
        "Ç": "C",
    }
)


def ascii_sanitize(text: str) -> str:
    """Normalize Turkish characters and produce a safe ASCII identifier."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text.translate(_TURKISH_MAP))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"\s+", "_", ascii_text.strip())
    ascii_text = re.sub(r"[^\w]", "_", ascii_text)
    ascii_text = re.sub(r"_+", "_", ascii_text).strip("_")
    return ascii_text


def scale_initials(scale_name: str) -> str:
    """Derive short prefix from scale name (e.g. Perfectionism → PERF, ÇBMÖ → CBMO)."""
    safe = ascii_sanitize(scale_name)
    if not safe:
        return "ITEM"
    parts = [p for p in re.split(r"[_\s]+", safe) if p]
    if len(parts) > 1:
        initials = "".join(p[0] for p in parts).upper()
    else:
        word = parts[0]
        consonants = "".join(c for c in word if c.upper() not in "AEIOU")
        initials = (consonants or word)[:4].upper()
    return initials or "ITEM"
