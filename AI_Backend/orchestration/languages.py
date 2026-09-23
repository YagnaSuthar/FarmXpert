"""
Indian languages: registry and script detection
===============================================
One place that knows, for each language a farmer may write or speak in:
its code, its scripts and how well the language model handles it (tier).
Adding a language is a new row here, not a code change elsewhere.

Script detection is deterministic (Unicode blocks) and runs before the model
does. It is what tells "mera gehu sukh raha hai" (Hindi in Latin letters) from
English, and it pins the language outright for scripts only one language uses
- Gujarati, Tamil, Telugu, Kannada, Malayalam, Odia, Gurmukhi - so a model
guess can never answer a Tamil farmer in Hindi.

Tiers
    strong  the LLM reads and writes it reliably; used directly
    medium  used directly, flagged for review in the evaluation set
    weak    used directly and flagged (`understanding.tier`), so answers in these
            languages can be reviewed; the place to route them through an
            Indian-language translation provider when one is contracted
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class Language:
    code: str              # ISO 639-1 where one exists, else 639-3
    name: str              # English name, used in prompts
    native: str            # the language's own name for itself
    scripts: Tuple[str, ...]  # ISO 15924, most common first
    tier: str              # strong | medium | weak


# The 22 languages of the Eighth Schedule, plus English and Hinglish handling
# (Hinglish is Hindi in Latin script: language "hi", script "latn").
LANGUAGES: Dict[str, Language] = {lang.code: lang for lang in (
    Language("en", "English", "English", ("latn",), "strong"),
    Language("hi", "Hindi", "हिन्दी", ("deva", "latn"), "strong"),
    Language("bn", "Bengali", "বাংলা", ("beng",), "strong"),
    Language("mr", "Marathi", "मराठी", ("deva", "latn"), "strong"),
    Language("te", "Telugu", "తెలుగు", ("telu",), "strong"),
    Language("ta", "Tamil", "தமிழ்", ("taml",), "strong"),
    Language("gu", "Gujarati", "ગુજરાતી", ("gujr", "latn"), "strong"),
    Language("kn", "Kannada", "ಕನ್ನಡ", ("knda",), "strong"),
    Language("ml", "Malayalam", "മലയാളം", ("mlym",), "medium"),
    Language("pa", "Punjabi", "ਪੰਜਾਬੀ", ("guru", "latn"), "medium"),
    Language("ur", "Urdu", "اردو", ("arab",), "medium"),
    Language("or", "Odia", "ଓଡ଼ିଆ", ("orya",), "weak"),
    Language("as", "Assamese", "অসমীয়া", ("beng",), "weak"),
    Language("ne", "Nepali", "नेपाली", ("deva",), "medium"),
    Language("sa", "Sanskrit", "संस्कृतम्", ("deva",), "weak"),
    Language("ks", "Kashmiri", "کٲشُر", ("arab", "deva"), "weak"),
    Language("sd", "Sindhi", "سنڌي", ("arab", "deva"), "weak"),
    Language("kok", "Konkani", "कोंकणी", ("deva",), "weak"),
    Language("mai", "Maithili", "मैथिली", ("deva",), "weak"),
    Language("doi", "Dogri", "डोगरी", ("deva",), "weak"),
    Language("mni", "Manipuri", "ꯃꯤꯇꯩꯂꯣꯟ", ("mtei", "beng"), "weak"),
    Language("sat", "Santali", "ᱥᱟᱱᱛᱟᱲᱤ", ("olck",), "weak"),
    Language("brx", "Bodo", "बड़ो", ("deva",), "weak"),
)}

SCRIPT_NAMES = {
    "latn": "Latin (English letters)", "deva": "Devanagari", "beng": "Bengali-Assamese",
    "guru": "Gurmukhi", "gujr": "Gujarati", "orya": "Odia", "taml": "Tamil",
    "telu": "Telugu", "knda": "Kannada", "mlym": "Malayalam", "arab": "Perso-Arabic",
    "olck": "Ol Chiki", "mtei": "Meetei Mayek",
}

# Unicode block -> script. Ordered ranges; checked per character.
_BLOCKS = (
    (0x0900, 0x097F, "deva"), (0x0980, 0x09FF, "beng"), (0x0A00, 0x0A7F, "guru"),
    (0x0A80, 0x0AFF, "gujr"), (0x0B00, 0x0B7F, "orya"), (0x0B80, 0x0BFF, "taml"),
    (0x0C00, 0x0C7F, "telu"), (0x0C80, 0x0CFF, "knda"), (0x0D00, 0x0D7F, "mlym"),
    (0x0600, 0x06FF, "arab"), (0x0750, 0x077F, "arab"), (0x1C50, 0x1C7F, "olck"),
    (0xABC0, 0xABFF, "mtei"), (0xA8E0, 0xA8FF, "deva"),
)
# A script only one registered language uses pins the language.
_SCRIPT_TO_LANGUAGE = {"gujr": "gu", "taml": "ta", "telu": "te", "knda": "kn", "mlym": "ml",
                       "orya": "or", "guru": "pa", "olck": "sat", "mtei": "mni"}

_ALIASES = {"hindi": "hi", "hinglish": "hi", "gujarati": "gu", "marathi": "mr", "tamil": "ta",
            "telugu": "te", "kannada": "kn", "malayalam": "ml", "bengali": "bn", "bangla": "bn",
            "punjabi": "pa", "odia": "or", "oriya": "or", "assamese": "as", "urdu": "ur",
            "english": "en", "nepali": "ne", "konkani": "kok", "maithili": "mai", "santali": "sat"}


def normalise_code(value: Optional[str]) -> Optional[str]:
    """'hi-IN', 'HI', 'Hindi', 'hin' -> 'hi'. None when unrecognised."""
    if not value:
        return None
    raw = str(value).strip().lower().replace("_", "-")
    if raw in _ALIASES:
        return _ALIASES[raw]
    base = raw.split("-")[0]
    if base in LANGUAGES:
        return base
    iso3 = {"hin": "hi", "guj": "gu", "mar": "mr", "tam": "ta", "tel": "te", "kan": "kn",
            "mal": "ml", "ben": "bn", "pan": "pa", "ori": "or", "ory": "or", "asm": "as",
            "urd": "ur", "eng": "en", "nep": "ne"}
    return iso3.get(base)


def get(code: Optional[str]) -> Language:
    return LANGUAGES.get(normalise_code(code) or "en", LANGUAGES["en"])


def detect_script(text: str) -> str:
    """The dominant script of the letters in `text` ('latn' when none)."""
    counts: Dict[str, int] = {}
    for ch in text:
        if not ch.isalpha() and unicodedata.category(ch) not in ("Mn", "Mc"):
            continue
        cp = ord(ch)
        script = "latn" if cp < 0x0250 else next(
            (s for lo, hi, s in _BLOCKS if lo <= cp <= hi), None)
        if script:
            counts[script] = counts.get(script, 0) + 1
    if not counts:
        return "latn"
    # Indic letters outweigh stray Latin (units, brand names, "NPK").
    indic = {k: v for k, v in counts.items() if k != "latn"}
    return max(indic, key=indic.get) if indic else "latn"


# Common romanized Hindi/Gujarati/Marathi farm words. Enough to flag Latin text
# as probably not English when the model is unavailable; the model decides
# otherwise.
_ROMANIZED_HINTS = re.compile(
    r"\b(mera|meri|mere|mujhe|kya|kab|kaise|kitna|kitni|hai|hain|nahi|nahin|aur|ko|ka|ki|ke|"
    r"mein|pani|paani|khet|fasal|gehu|gehun|dhan|kapas|khad|beej|barish|baarish|mitti|"
    r"sinchai|dawa|keeda|kide|kheti|shu|che|nathi|kem|shetkari|pik)\b", re.I)


def looks_romanized_indic(text: str) -> bool:
    words = re.findall(r"[A-Za-z]+", text)
    return bool(words) and len(_ROMANIZED_HINTS.findall(text)) >= max(2, len(words) // 6)


@dataclass(frozen=True)
class Detected:
    language: str
    script: str
    pinned: bool     # the script alone decided the language


def detect(text: str, hint: Optional[str] = None) -> Detected:
    """Deterministic first guess: script from Unicode, language where the script
    decides it, else the caller's hint (the farmer's profile language)."""
    script = detect_script(text or "")
    pinned = _SCRIPT_TO_LANGUAGE.get(script)
    if pinned:
        return Detected(pinned, script, True)
    hint_code = normalise_code(hint)
    if script == "latn":
        if not looks_romanized_indic(text):
            return Detected("en", "latn", False)
        latin_capable = hint_code and hint_code != "en" and "latn" in get(hint_code).scripts
        return Detected(hint_code if latin_capable else "hi", "latn", False)
    # Shared scripts (Devanagari, Bengali, Perso-Arabic): trust a compatible hint.
    if hint_code and script in get(hint_code).scripts:
        return Detected(hint_code, script, False)
    default = {"deva": "hi", "beng": "bn", "arab": "ur"}.get(script, "hi")
    return Detected(default, script, False)


def reconcile(model_language: Optional[str], detected: Detected) -> str:
    """The model's language, unless the script proves it wrong."""
    code = normalise_code(model_language)
    if detected.pinned or not code:
        return detected.language
    if detected.script not in get(code).scripts:
        # e.g. the model says "hi" for Bengali script: the script wins.
        return detected.language
    return code


def answer_instruction(code: str, script: str) -> str:
    """How the answer must be written, for the answer prompt."""
    lang = get(code)
    if lang.code == "en":
        return "Write in simple English."
    if script == "latn":
        return (f"Write in {lang.name}, using English (Latin) letters exactly as the farmer did "
                f"- romanized {lang.name}, not {SCRIPT_NAMES.get(lang.scripts[0], 'native')} script.")
    return f"Write in {lang.name} ({lang.native}), in {SCRIPT_NAMES.get(script, script)} script."
