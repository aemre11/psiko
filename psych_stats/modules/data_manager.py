"""
Streamlit rules (PsychStats) — apply on every change in this module:
1. Never write to widget-backed session state key inside on_change — pending flag; consume before widgets.
2. Every rerun-surviving widget needs stable key= initialized at startup.
3. Never call st.rerun() inside a callback — flag + natural rerun (button handlers excepted).
4. Clear only downstream state keys, not upstream keys backing visible widgets.
5. Loop-rendered widgets use index-stable keys.
6. Always use .get(key, default) for nested dicts in session state.
7. Never store class instances in session state.
8. On file upload, unconditionally overwrite KEY_RAW_DF.
9. List item action buttons use stable unique ID keys, not positional index keys.
"""
import hashlib
import json
import logging
import re
import unicodedata
import uuid
import zipfile
from collections import defaultdict
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st

from utils.stats_helpers import item_total_statistics_table

_TURKISH_CHAR_MAP = str.maketrans(
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

KEY_UPLOAD_BYTES = "_upload_file_bytes"
KEY_UPLOAD_FILE_SIG = "_upload_file_sig"
KEY_XLSX_SHEETS = "_xlsx_sheet_names"
KEY_PARSE_SIG = "_data_parse_sig"
KEY_PENDING_CONFIG = "_pending_loaded_config"
KEY_SESSION_ZIP_SIG = "_session_zip_sig"

logger = logging.getLogger(__name__)

# Header-only patterns (word boundaries / phrases — never bare "zaman", which matches "her zaman").
_NAME_TIMESTAMP_PATTERNS = (
    re.compile(r"\btimestamp\b", re.I),
    re.compile(r"\bdatetime\b", re.I),
    re.compile(r"\bdate\s*submitted\b", re.I),
    re.compile(r"\btime\s*submitted\b", re.I),
    re.compile(r"zaman\s*damg", re.I),  # Zaman Damgası (Google Forms)
    re.compile(r"^zaman\s*damg", re.I),
)
_VALUE_DATE_PATTERN = re.compile(
    r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4}"
)

KEY_RAW_DF = "raw_df"
KEY_WORKING_DF = "working_df"
KEY_FINAL_DF = "final_df"
KEY_COL_ROLES = "column_roles"
KEY_SCALE_MAP = "scale_map"
KEY_SHORT_LABELS = "short_labels"
KEY_REVERSE_CONFIG = "reverse_config"
KEY_COMPOSITE_CONFIG = "composites"
KEY_UPLOAD_DONE = "upload_done"
KEY_MAPPING_DONE = "mapping_done"
KEY_ROLES_CONFIRMED = "roles_confirmed"
KEY_REVERSE_DONE = "reverse_done"
KEY_REVERSE_PRIMED = "reverse_primed"
KEY_RECODE_DONE = "recode_done"
KEY_RECODE_MAP = "recode_map"
KEY_RECODE_PRIMED = "recode_primed"
KEY_RECODE_PREVIEW = "_recode_preview"
KEY_DEFINED_SCALES = "defined_scales"
KEY_SCALE_PRESET_MAP = "scale_preset_map"
KEY_LOAD_SCALE_PRESET = "load_scale_preset_select"

CONFIG_VERSION = 1
CONFIG_STATE_KEYS = (
    KEY_COL_ROLES,
    KEY_SCALE_MAP,
    KEY_SHORT_LABELS,
    KEY_REVERSE_CONFIG,
    KEY_COMPOSITE_CONFIG,
    KEY_MAPPING_DONE,
    KEY_REVERSE_DONE,
    KEY_RECODE_MAP,
    KEY_RECODE_DONE,
)

ROLE_SCALE_ITEM = "Ölçek Maddesi"
ROLE_DEMOGRAPHIC = "Demografik"
ROLE_IGNORE = "Yok say"
ROLE_OPTIONS = [ROLE_SCALE_ITEM, ROLE_DEMOGRAPHIC, ROLE_IGNORE]
ROLE_TO_KEY = {
    ROLE_SCALE_ITEM: "scale_item",
    ROLE_DEMOGRAPHIC: "demographic",
    ROLE_IGNORE: "ignore",
}
KEY_TO_ROLE = {v: k for k, v in ROLE_TO_KEY.items()}
METHOD_SUM_LABEL = "Toplam"
METHOD_MEAN_LABEL = "Ortalama"


def _method_display(method: str) -> str:
    return METHOD_SUM_LABEL if method == "sum" else METHOD_MEAN_LABEL

KNOWN_SCALE_BOUNDS = {
    "perfectionism": (1, 5),
    "çbmö": (1, 5),
    "cbmo": (1, 5),
    "sharenting": (1, 5),
    "prfq": (1, 7),
}

PRESET_CUSTOM_OPTION = "Özel (kendiniz tanımlayın)"

SCALE_PRESETS = {
    "ÇBMÖ — Parenting Perfectionism Scale (23 items, 5-point)": {
        "name": "CBMO",
        "n_items": 23,
        "scale_range": (1, 5),
        "reverse_items": [],
    },
    "Sharenting Scale (17 items, 5-point)": {
        "name": "Sharenting",
        "n_items": 17,
        "scale_range": (1, 5),
        "reverse_items": [11, 12, 13],
    },
    "PRFQ — Turkish Adaptation, Beşiroğlu & Halfon 2025 (18 items, 7-point)": {
        "name": "PRFQ",
        "n_items": 18,
        "scale_range": (1, 7),
        "reverse_items": [],
    },
}

PENDING_RESYNC_LABELS = "pending_resync_labels"
PENDING_SHORT_LABEL_MANUAL = "pending_short_label_manual"
KEY_SCALE_BLOCKS = "scale_blocks"
KEY_PROPOSED_AUTO_BLOCKS = "proposed_auto_blocks"
KEY_SCALE_BLOCK_MESSAGES = "scale_block_messages"
KEY_AUTO_DETECT_ERROR = "auto_detect_error"
KEY_COMPOSITE_ITEMS_CHECKED = "composite_items_checked"
KEY_COMPOSITE_NAME_INPUT = "composite_name_input"
KEY_COMPOSITE_METHOD = "composite_method_selection"
KEY_COMPOSITE_SUGGESTIONS = "_composite_suggestions"
KEY_COMPOSITE_SUBMIT_ATTEMPTED = "composite_submit_attempted"
KEY_EDITING_COMPOSITE_ID = "editing_composite_id"
PENDING_START_EDITING = "pending_start_editing"
PENDING_CLEAR_COMPOSITE_FORM = "pending_clear_composite_form"
PENDING_MULTISELECT_RESET = "pending_multiselect_reset"
PENDING_CLEAR_BATCH_FORM = "pending_clear_batch_form"
PENDING_APPLY_CONFIG = "pending_apply_config"
KEY_BATCH_DEFS = "batch_subscale_defs"
KEY_BATCH_EDIT_ID = "batch_edit_def_id"
PENDING_BATCH_EDIT_LOAD = "pending_batch_edit_load"
KEY_NEW_SCALE_INPUT = "new_defined_scale_input"
# Step 2 bulk role assignment (set several columns to one role at once).
KEY_BULK_ROLE_COLS = "bulk_role_cols_select"
KEY_BULK_ROLE_VALUE = "bulk_role_value_select"
PENDING_BULK_ROLE = "pending_bulk_role"


def _role_key(col_index: int) -> str:
    return f"role_select_{col_index}"


def _scale_name_key(col_index: int) -> str:
    return f"scale_name_{col_index}"


def _short_label_key(col_index: int) -> str:
    return f"short_label_{col_index}"


def _short_label_manual_key(col_index: int) -> str:
    return f"_short_label_manual_{col_index}"


def _role_reason_key(col_index: int) -> str:
    return f"_role_default_reason_{col_index}"


def _new_composite_id() -> str:
    return uuid.uuid4().hex[:12]


def _auto_group_id() -> str:
    return uuid.uuid4().hex[:12]


def _block_widget_suffix(scale_name: str) -> str:
    return _sanitize_short_label(scale_name) or "scale"


def _block_from_key(scale_name: str) -> str:
    return f"block_from_{_block_widget_suffix(scale_name)}"


def _block_to_key(scale_name: str) -> str:
    return f"block_to_{_block_widget_suffix(scale_name)}"


def _ensure_composite_id(comp: dict) -> dict:
    entry = dict(comp)
    if not entry.get("id"):
        entry["id"] = _new_composite_id()
    return entry


def _normalize_composite_list(composites: list) -> list[dict]:
    return [_ensure_composite_id(c) for c in composites if isinstance(c, dict)]


def _sanitize_short_label(value: str) -> str:
    """Clean short labels for analysis columns (Turkish → ASCII, safe identifiers)."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value.strip().translate(_TURKISH_CHAR_MAP))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^\w]", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


# --- Value recoding (Step 2.5): text Likert responses → numbers ---------------

# Leading-integer label, e.g. "3. Beni orta...", "1.Beni hiç...", "1 ''Hiç...''".
# Inconsistent spacing/punctuation after the number is tolerated.
_LEADING_INT_RE = re.compile(r"^\s*(\d+)\s*[.\)]?")

# Pre-fill dictionary for pure-word frequency scales (pattern 2). Keys are
# Turkish-normalized (see _normalize_response_text). Unknown words stay blank.
_TR_FREQ_WORDS_5 = {
    "hiçbir zaman": 1, "hiç": 1,
    "nadiren": 2,
    "bazen": 3,
    "sıklıkla": 4, "sık sık": 4,
    "her zaman": 5,
}

# --- Role auto-detection: text-valued Likert signatures (detection only) -------
# Leading-NUMBER label, e.g. "3. Beni orta...", "1)Çok". Stricter than the recoding
# regex: a "." or ")" must follow the number, so plain numerics (handled by the
# numeric path) aren't mistaken for ordinal text labels.
_LIKERT_LEADING_LABEL_RE = re.compile(r"^\s*\d+\s*[.\)]")

# Known Turkish Likert words (agreement + frequency), Turkish-normalized. Used only
# to recognize a text column as a scale item — recoding still uses _TR_FREQ_WORDS_5.
_LIKERT_AGREE_WORDS = {
    "kesinlikle katılmıyorum", "katılmıyorum", "kısmen katılmıyorum",
    "kararsızım", "ne katılıyorum ne katılmıyorum", "kısmen katılıyorum",
    "katılıyorum", "kesinlikle katılıyorum",
    "hiç katılmıyorum", "tamamen katılıyorum",
}
_LIKERT_WORD_SET = set(_TR_FREQ_WORDS_5.keys()) | _LIKERT_AGREE_WORDS


def _tr_lower(text: str) -> str:
    """Turkish-aware lowercasing for dictionary matching.

    Python's str.lower() is locale-independent: it turns "İ" into "i̇" (i + U+0307
    combining dot) and leaves/lowers "I" to "i", which silently breaks matching
    against Turkish keys like "hiçbir"/"sıklıkla" — a bug that passes mock data and
    fails on real Turkish survey text. Map the dotted/dotless I explicitly BEFORE
    lower(): "İ"→"i" and "I"→"ı". The remaining Turkish letters (ç/ş/ğ/ö/ü) lower
    correctly under the default str.lower().
    """
    return str(text).replace("İ", "i").replace("I", "ı").lower()


def _normalize_response_text(value) -> str:
    """Turkish-lowercase + collapse internal whitespace, for word-dictionary lookup."""
    return re.sub(r"\s+", " ", _tr_lower(value)).strip()


def init_session_state():
    defaults = {
        KEY_RAW_DF: None,
        KEY_WORKING_DF: None,
        KEY_FINAL_DF: None,
        KEY_COL_ROLES: {},
        KEY_SCALE_MAP: {},
        KEY_SHORT_LABELS: {},
        KEY_REVERSE_CONFIG: {},
        KEY_COMPOSITE_CONFIG: [],
        KEY_UPLOAD_DONE: False,
        KEY_MAPPING_DONE: False,
        KEY_ROLES_CONFIRMED: False,
        KEY_REVERSE_DONE: False,
        KEY_REVERSE_PRIMED: False,
        KEY_RECODE_DONE: False,
        KEY_RECODE_MAP: {},
        KEY_RECODE_PRIMED: False,
        PENDING_RESYNC_LABELS: False,
        KEY_DEFINED_SCALES: [],
        KEY_SCALE_PRESET_MAP: {},
        KEY_SCALE_BLOCKS: {},
        KEY_PROPOSED_AUTO_BLOCKS: [],
        KEY_SCALE_BLOCK_MESSAGES: [],
        KEY_COMPOSITE_NAME_INPUT: "",
        KEY_COMPOSITE_ITEMS_CHECKED: {},
        KEY_COMPOSITE_METHOD: METHOD_SUM_LABEL,
        KEY_COMPOSITE_SUGGESTIONS: [],
        KEY_COMPOSITE_SUBMIT_ATTEMPTED: False,
        KEY_EDITING_COMPOSITE_ID: None,
        PENDING_START_EDITING: None,
        PENDING_CLEAR_COMPOSITE_FORM: False,
        PENDING_MULTISELECT_RESET: False,
        PENDING_CLEAR_BATCH_FORM: False,
        KEY_BATCH_DEFS: [],
        KEY_BATCH_EDIT_ID: None,
        PENDING_BATCH_EDIT_LOAD: None,
        PENDING_APPLY_CONFIG: None,
        KEY_BULK_ROLE_COLS: [],
        KEY_BULK_ROLE_VALUE: ROLE_SCALE_ITEM,
        PENDING_BULK_ROLE: None,
        "batch_scale_select": "",
        "batch_subscale_name": "",
        "batch_subscale_items": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _read_csv_bytes(raw_bytes: bytes) -> pd.DataFrame:
    try:
        return pd.read_csv(BytesIO(raw_bytes), encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(BytesIO(raw_bytes), encoding="latin-1")


def _read_xlsx_bytes(raw_bytes: bytes, sheet_name: str) -> pd.DataFrame:
    return pd.read_excel(BytesIO(raw_bytes), sheet_name=sheet_name, engine="openpyxl")


def _xlsx_sheet_names(raw_bytes: bytes) -> list[str]:
    with pd.ExcelFile(BytesIO(raw_bytes), engine="openpyxl") as workbook:
        return list(workbook.sheet_names)


def _sample_values(series: pd.Series, n: int = 3) -> str:
    values = series.dropna().head(n).tolist()
    return ", ".join(str(v) for v in values) if values else "—"


def _timestamp_ignore_reason(col_name: str, series: pd.Series) -> str | None:
    for pattern in _NAME_TIMESTAMP_PATTERNS:
        if pattern.search(col_name):
            return f"Sütun adı zaman damgası desenine uyuyor: {pattern.pattern!r}"
    sample = series.dropna().astype(str).head(5)
    if not sample.empty:
        date_ratio = sample.str.contains(_VALUE_DATE_PATTERN, regex=True).mean()
        if date_ratio >= 0.6:
            return f"Örnek değerler tarih gibi görünüyor (ilk satırların {date_ratio:.0%}'i)"
    return None


def _email_ignore_reason(col_name: str, series: pd.Series) -> str | None:
    lowered = col_name.lower()
    for token in ("email", "e-mail", "eposta", "e-posta"):
        if token in lowered:
            return f"Sütun adında {token!r} geçiyor"
    sample = series.dropna().astype(str).head(10)
    if not sample.empty:
        at_ratio = sample.str.contains("@", regex=False).mean()
        if at_ratio >= 0.5:
            return f"Örnek değerlerde @ var (ilk satırların {at_ratio:.0%}'i)"
    return None


def _likert_check_details(series: pd.Series) -> tuple[bool, str]:
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    if valid.empty:
        return False, "Zorlama sonrası sayısal değer yok"
    n_unique = int(valid.nunique())
    vmin, vmax = float(valid.min()), float(valid.max())
    if n_unique > 7:
        return False, f"Çok fazla benzersiz değer ({n_unique} > 7)"
    if vmin < 1 or vmax > 7:
        return False, f"1–7 aralığı dışında değerler (min={vmin:g}, maks={vmax:g})"
    return True, f"Sayısal Likert benzeri değerler (benzersiz={n_unique}, min={vmin:g}, maks={vmax:g})"


def _is_likert_scale_column(series: pd.Series) -> bool:
    ok, _ = _likert_check_details(series)
    return ok


def _text_likert_details(series: pd.Series) -> tuple[bool, str]:
    """Detect a TEXT-valued Likert item: a small set (≈3–7) of unique values whose
    labels look ordinal — either leading-number labels ("3. Beni orta...") or known
    Turkish Likert words (hiçbir zaman…her zaman / katılıyorum variants)."""
    cleaned = series.dropna().astype(str).str.strip()
    cleaned = cleaned[cleaned != ""]
    uniques = set(cleaned.tolist())
    n_unique = len(uniques)
    if not (3 <= n_unique <= 7):
        return False, ""
    leading = sum(1 for v in uniques if _LIKERT_LEADING_LABEL_RE.match(v))
    words = sum(1 for v in uniques if _normalize_response_text(v) in _LIKERT_WORD_SET)
    if leading / n_unique >= 0.6 or words / n_unique >= 0.6:
        return True, f"Metin tabanlı Likert ({n_unique} benzersiz değer, sıralı etiketler)"
    return False, ""


# Age/count column NAME signal. Word-boundary-aware so it matches "yaşı"/"yaşınız"/
# "yaş grubu" but NOT "yaşam" (as in "Yaşam Doyumu", a real scale).
_COUNT_NAME_RE = re.compile(
    r"yaş[ıi]|\byaş\b|\byas\b|\bage\b|sayı|sayi|kaç|kac|adet|number|count", re.I
)


def _is_count_like_demographic(col_name: str, series: pd.Series) -> bool:
    """Integer columns with count/age-style names (child age, household size, child
    count, etc.) — kept Demographic even when the integers fall in the Likert range."""
    if not _COUNT_NAME_RE.search(col_name or ""):
        return False
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    if valid.empty:
        return False
    if not (valid == valid.round()).all():
        return False
    vmin, vmax = float(valid.min()), float(valid.max())
    return vmin >= 0 and vmax <= 120


def _classify_column_with_reason(col_name: str, series: pd.Series) -> tuple[str, str]:
    ts_reason = _timestamp_ignore_reason(col_name, series)
    if ts_reason:
        logger.debug("Column %r → Ignore: %s", col_name, ts_reason)
        return ROLE_IGNORE, ts_reason
    email_reason = _email_ignore_reason(col_name, series)
    if email_reason:
        logger.debug("Column %r → Ignore: %s", col_name, email_reason)
        return ROLE_IGNORE, email_reason
    if _is_count_like_demographic(col_name, series):
        return (
            ROLE_DEMOGRAPHIC,
            "Sayım/yaş benzeri tamsayı sütunu (adında yaş/sayı/kaç/adet/number/count)",
        )
    is_likert, likert_detail = _likert_check_details(series)
    if is_likert:
        logger.debug("Column %r → Scale Item: %s", col_name, likert_detail)
        return ROLE_SCALE_ITEM, likert_detail
    is_text_likert, text_detail = _text_likert_details(series)
    if is_text_likert:
        logger.debug("Column %r → Scale Item: %s", col_name, text_detail)
        return ROLE_SCALE_ITEM, text_detail
    if pd.to_numeric(series, errors="coerce").notna().any():
        reason = f"Sayısal ancak Likert değil ({likert_detail})"
    else:
        reason = f"Sayısal olmayan / metin alanı ({series.nunique(dropna=True)} benzersiz değer)"
    logger.debug("Column %r → Demographic: %s", col_name, reason)
    return ROLE_DEMOGRAPHIC, reason


def _default_role(col_name: str, series: pd.Series) -> str:
    role, _ = _classify_column_with_reason(col_name, series)
    return role


def _auto_short_label(scale_name: str, col_index: int, column_count: int) -> str:
    """{ScaleName}_{n} where n counts items with the same scale name in column order."""
    base = _sanitize_short_label(scale_name.strip()) or "Item"
    target = scale_name.strip()
    n = 0
    for i in range(column_count):
        other_scale = (st.session_state.get(_scale_name_key(i)) or "").strip()
        if other_scale != target:
            continue
        n += 1
        if i == col_index:
            break
    return f"{base}_{n}"


def _resync_all_auto_short_labels(column_count: int) -> None:
    """Update short-label keys only — never read or write scale_name_* keys."""
    for i in range(column_count):
        if st.session_state.get(_role_key(i)) != ROLE_SCALE_ITEM:
            continue
        if st.session_state.get(_short_label_manual_key(i), False):
            continue
        scale_name = (st.session_state.get(_scale_name_key(i)) or "").strip()
        if not scale_name:
            continue
        suggested = _sanitize_short_label(_auto_short_label(scale_name, i, column_count))
        st.session_state[_short_label_key(i)] = suggested


def _on_scale_name_change() -> None:
    """Pending flag only — never write scale_name_* or short_label_* keys here."""
    st.session_state[PENDING_RESYNC_LABELS] = True


def _column_mapper_label(col_list: list, col: str) -> str:
    index = col_list.index(col)
    preview = col if len(col) <= 50 else col[:50] + "…"
    return f"[{index}] {preview}"


def _scale_item_columns_from_roles(col_list: list) -> list[str]:
    """Scale Item columns from confirmed KEY_COL_ROLES (Sub-phase A output)."""
    roles = st.session_state.get(KEY_COL_ROLES, {})
    return [col for col in col_list if roles.get(col) == "scale_item"]


def _scale_item_indices_from_roles(col_list: list) -> list[int]:
    roles = st.session_state.get(KEY_COL_ROLES, {})
    return [i for i, col in enumerate(col_list) if roles.get(col) == "scale_item"]


def _range_indices(col_list: list, from_col: str, to_col: str) -> set[int]:
    if from_col not in col_list or to_col not in col_list:
        return set()
    start, end = sorted((col_list.index(from_col), col_list.index(to_col)))
    return set(range(start, end + 1))


def _coerce_scale_blocks(raw, defined: list[str]) -> dict[str, dict]:
    blocks: dict[str, dict] = {}
    if isinstance(raw, dict):
        for name, entry in raw.items():
            if name in defined and isinstance(entry, dict):
                blocks[name] = {
                    "from_col": entry.get("from_col", "") or "",
                    "to_col": entry.get("to_col", "") or "",
                }
    elif isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            name = (entry.get("scale_name") or "").strip()
            if name in defined:
                blocks[name] = {
                    "from_col": entry.get("from_col", "") or "",
                    "to_col": entry.get("to_col", "") or "",
                }
    for scale in defined:
        if scale not in blocks:
            blocks[scale] = {"from_col": "", "to_col": ""}
    return blocks


def _scales_matching_max(defined: list[str], max_val: int | None) -> list[str]:
    if max_val is None:
        return []
    return [s for s in defined if _scale_bounds_for_name(s)[1] == max_val]


def _scale_item_count_in_group(col_list: list, group: dict) -> int:
    roles = st.session_state.get(KEY_COL_ROLES, {})
    start = group.get("start_idx")
    end = group.get("end_idx")
    if start is None or end is None:
        return int(group.get("n_items", 0))
    return sum(
        1
        for i in range(start, end + 1)
        if i < len(col_list) and roles.get(col_list[i]) == "scale_item"
    )


def _equal_subdivide_counts(total: int, n_scales: int) -> list[int]:
    if n_scales <= 0:
        return []
    base, remainder = divmod(total, n_scales)
    return [base + (1 if i < remainder else 0) for i in range(n_scales)]


def _is_exact_equal_subdivision(total: int, n_scales: int) -> bool:
    return n_scales > 0 and total % n_scales == 0


def _subdivision_counts_from_presets(
    subdivision_scales: list[str], n_items: int
) -> list[int] | None:
    """Use loaded preset n_items when every scale in the block has one and they sum to n_items."""
    preset_map = st.session_state.get(KEY_SCALE_PRESET_MAP, {})
    counts: list[int] = []
    for scale in subdivision_scales:
        meta = preset_map.get(scale)
        if not meta or meta.get("n_items") is None:
            return None
        counts.append(int(meta["n_items"]))
    if sum(counts) == n_items:
        return counts
    return None


def _short_label_item_number(short_label: str, scale_name: str) -> int | None:
    base = _sanitize_short_label(scale_name)
    if not base:
        return None
    match = re.match(rf"^{re.escape(base)}_(\d+)$", short_label, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _reverse_locked_key(raw_col: str) -> str:
    return f"_reverse_locked_{raw_col}"


def _lock_reverse_checkbox_choices(raw_cols: list[str]) -> None:
    """Persist checkbox choices so preset/config priming cannot overwrite them."""
    ss = st.session_state
    for raw_col in raw_cols:
        chk_key = f"reverse_chk_{raw_col}"
        ss[_reverse_locked_key(raw_col)] = bool(ss.get(chk_key, False))


def _clear_reverse_locked_keys() -> None:
    for key in list(st.session_state.keys()):
        if str(key).startswith("_reverse_locked_"):
            del st.session_state[key]


def _prime_reverse_checks_from_presets(raw_cols: list[str]) -> None:
    preset_map = st.session_state.get(KEY_SCALE_PRESET_MAP, {})
    scale_map = st.session_state.get(KEY_SCALE_MAP, {})
    short_labels = st.session_state.get(KEY_SHORT_LABELS, {})
    ss = st.session_state

    for raw_col in raw_cols:
        chk_key = f"reverse_chk_{raw_col}"
        locked_key = _reverse_locked_key(raw_col)
        if locked_key in ss:
            ss[chk_key] = bool(ss[locked_key])
            continue

        scale_name = scale_map.get(raw_col, "")
        meta = preset_map.get(scale_name)
        if not meta:
            continue
        reverse_items = meta.get("reverse_items") or []
        short = short_labels.get(raw_col, "")
        item_n = _short_label_item_number(short, scale_name)
        if item_n is not None and item_n in reverse_items and chk_key not in ss:
            ss[chk_key] = True
            lo, hi = meta.get("scale_range", (1, 5))
            if f"reverse_min_{raw_col}" not in ss:
                ss[f"reverse_min_{raw_col}"] = int(lo)
            if f"reverse_max_{raw_col}" not in ss:
                ss[f"reverse_max_{raw_col}"] = int(hi)


def _prime_reverse_checks_from_config(raw_cols: list[str]) -> None:
    reverse_config = st.session_state.get(KEY_REVERSE_CONFIG, {})
    ss = st.session_state
    for raw_col in raw_cols:
        chk_key = f"reverse_chk_{raw_col}"
        locked_key = _reverse_locked_key(raw_col)
        if locked_key in ss:
            ss[chk_key] = bool(ss[locked_key])
            continue
        bounds = reverse_config.get(raw_col)
        if not bounds:
            continue
        ss[chk_key] = True
        ss[f"reverse_min_{raw_col}"] = int(bounds.get("min", 1))
        ss[f"reverse_max_{raw_col}"] = int(bounds.get("max", 5))


def _render_preset_reverse_hints() -> None:
    preset_map = st.session_state.get(KEY_SCALE_PRESET_MAP, {})
    for scale_name, meta in preset_map.items():
        reverse_items = meta.get("reverse_items") or []
        if not reverse_items:
            continue
        items_str = ", ".join(str(n) for n in reverse_items)
        st.caption(
            f"Hazır ayardan otomatik öneri **{scale_name}**: maddeler {items_str} "
            "— uygulamadan önce doğrulayın."
        )


def _clear_block_bound_widget_keys(defined: list[str]) -> None:
    """Drop From/To widget keys so selectboxes use index= from scale_blocks on next render."""
    for scale in defined:
        for key_fn in (_block_from_key, _block_to_key):
            key = key_fn(scale)
            if key in st.session_state:
                del st.session_state[key]


def _auto_block_default_scale(group_index: int, n_groups: int, defined: list[str]) -> str:
    """Map detected blocks to defined scales by position (first block → first scale, etc.)."""
    if not defined:
        return ""
    if n_groups <= 1:
        return defined[0]
    if group_index == 0:
        return defined[0]
    if group_index >= n_groups - 1:
        return defined[-1]
    if len(defined) > n_groups and n_groups > 1:
        idx = round(group_index * (len(defined) - 1) / (n_groups - 1))
        return defined[min(idx, len(defined) - 1)]
    return defined[min(group_index, len(defined) - 1)]


def _unmatched_scales_for_group(
    defined: list[str], groups: list[dict], group_index: int, max_val: int | None
) -> list[str]:
    """Scales sharing this block's max that are not assigned to another single-scale block."""
    matching_max = _scales_matching_max(defined, max_val)
    consumed: set[str] = set()
    for j, other in enumerate(groups):
        if j == group_index:
            continue
        if other.get("needs_subdivision"):
            continue
        other_max = other.get("max_val")
        other_matching = _scales_matching_max(defined, other_max)
        if len(other_matching) == 1:
            consumed.add(other_matching[0])
        else:
            chosen = other.get("default_scale") or st.session_state.get(
                f"auto_block_scale_{other.get('id', '')}"
            )
            if chosen:
                consumed.add(chosen)
    return [s for s in matching_max if s not in consumed]


def _claimed_indices_before_scale(
    col_list: list, blocks: dict[str, dict], defined: list[str], scale_index: int
) -> set[int]:
    claimed: set[int] = set()
    for scale in defined[:scale_index]:
        entry = blocks.get(scale, {})
        from_col = entry.get("from_col")
        to_col = entry.get("to_col")
        if from_col and to_col:
            claimed |= _range_indices(col_list, from_col, to_col)
    return claimed


def _available_from_columns(
    col_list: list, scale_items: list[str], claimed: set[int]
) -> list[str]:
    return [col for col in scale_items if col_list.index(col) not in claimed]


def _available_to_columns(
    col_list: list, from_col: str | None, from_options: list[str]
) -> list[str]:
    if not from_col or from_col not in from_options:
        return from_options
    from_idx = col_list.index(from_col)
    return [col for col in from_options if col_list.index(col) >= from_idx]


def _assign_subdivided_group(
    col_list: list,
    group: dict,
    scales: list[str],
    counts: list[int],
    blocks: dict[str, dict],
) -> bool:
    roles = st.session_state.get(KEY_COL_ROLES, {})
    start = group.get("start_idx")
    end = group.get("end_idx")
    if start is None or end is None:
        return False
    item_indices = [
        i
        for i in range(start, end + 1)
        if i < len(col_list) and roles.get(col_list[i]) == "scale_item"
    ]
    if sum(counts) != len(item_indices):
        return False
    pos = 0
    for scale, count in zip(scales, counts):
        if count <= 0:
            continue
        slice_indices = item_indices[pos : pos + count]
        pos += count
        if not slice_indices:
            continue
        blocks[scale] = {
            "from_col": col_list[slice_indices[0]],
            "to_col": col_list[slice_indices[-1]],
        }
    return True


def _apply_block_assignment(
    col_list: list,
    scale: str,
    from_col: str,
    to_col: str,
    counters: dict[str, int],
) -> tuple[str | None, list[str]]:
    if not scale or not from_col or not to_col:
        return None, []
    if from_col not in col_list or to_col not in col_list:
        return None, []

    roles = st.session_state.get(KEY_COL_ROLES, {})
    scale_map = dict(st.session_state.get(KEY_SCALE_MAP, {}))
    short_labels = dict(st.session_state.get(KEY_SHORT_LABELS, {}))

    start, end = sorted((col_list.index(from_col), col_list.index(to_col)))
    counters[scale] = 0
    assigned = 0
    first_short = None
    last_short = None
    skipped: list[str] = []

    for i in range(start, end + 1):
        col = col_list[i]
        if roles.get(col) != "scale_item":
            skipped.append(col)
            continue
        counters[scale] = counters[scale] + 1
        n = counters[scale]
        short = _sanitize_short_label(f"{scale}_{n}")
        scale_map[col] = scale
        short_labels[col] = short
        assigned += 1
        if assigned == 1:
            first_short = short
        last_short = short

    st.session_state[KEY_SCALE_MAP] = scale_map
    st.session_state[KEY_SHORT_LABELS] = short_labels

    if assigned == 0:
        return None, skipped
    return f"✅ {scale}: {first_short} → {last_short} ({assigned} items)", skipped


def _auto_detect_scale_groups(df: pd.DataFrame, col_list: list) -> list[dict]:
    indices = _scale_item_indices_from_roles(col_list)
    if not indices:
        return []

    groups: list[dict] = []
    current_max: int | None = None
    current_start: int | None = None
    current_end: int | None = None

    def flush_group() -> None:
        nonlocal current_max, current_start, current_end
        if current_start is None or current_end is None or current_max is None:
            return
        groups.append(
            {
                "id": _auto_group_id(),
                "from_col": col_list[current_start],
                "to_col": col_list[current_end],
                "start_idx": current_start,
                "end_idx": current_end,
                "max_val": current_max,
                "n_items": current_end - current_start + 1,
            }
        )
        current_max = None
        current_start = None
        current_end = None

    for i in indices:
        col = col_list[i]
        numeric = pd.to_numeric(df[col], errors="coerce").dropna()
        col_max = int(numeric.max()) if not numeric.empty else None

        if current_start is None:
            current_max = col_max
            current_start = i
            current_end = i
            continue

        if col_max == current_max:
            current_end = i
        else:
            flush_group()
            current_max = col_max
            current_start = i
            current_end = i

    flush_group()
    return groups


def _apply_all_blocks_action(col_list: list) -> None:
    defined = list(st.session_state.get(KEY_DEFINED_SCALES, []))
    blocks = _coerce_scale_blocks(st.session_state.get(KEY_SCALE_BLOCKS), defined)
    roles = st.session_state.get(KEY_COL_ROLES, {})
    scale_map = dict(st.session_state.get(KEY_SCALE_MAP, {}))
    short_labels = dict(st.session_state.get(KEY_SHORT_LABELS, {}))
    for col in col_list:
        if roles.get(col) == "scale_item":
            scale_map.pop(col, None)
            short_labels.pop(col, None)
    st.session_state[KEY_SCALE_MAP] = scale_map
    st.session_state[KEY_SHORT_LABELS] = short_labels

    messages: list[str] = []
    all_skipped: list[str] = []
    counters: dict[str, int] = {}
    for scale_name in defined:
        stored = blocks.get(scale_name, {})
        from_col = (stored.get("from_col") or "") or (
            st.session_state.get(_block_from_key(scale_name), "") or ""
        )
        to_col = (stored.get("to_col") or "") or (
            st.session_state.get(_block_to_key(scale_name), "") or ""
        )
        blocks[scale_name] = {"from_col": from_col, "to_col": to_col}
        msg, skipped = _apply_block_assignment(
            col_list,
            scale_name,
            from_col,
            to_col,
            counters,
        )
        if msg:
            messages.append(msg)
        all_skipped.extend(skipped)
    st.session_state[KEY_SCALE_BLOCKS] = blocks
    if messages:
        st.session_state[KEY_SCALE_BLOCK_MESSAGES] = messages
    if all_skipped:
        preview = ", ".join(all_skipped[:8])
        extra = "…" if len(all_skipped) > 8 else ""
        st.session_state["scale_block_skip_warning"] = (
            "Skipped non–scale-item columns in block ranges: "
            f"{preview}{extra}"
        )


def _run_auto_detect_blocks_action(col_list: list) -> None:
    """Auto-assign each defined scale a contiguous, non-overlapping block using its
    preset item count — a sequential walk over the scale-item columns (in dataframe
    order). For each scale: start = cursor, end = cursor + preset_count − 1, then
    advance the cursor past it. Writes KEY_SCALE_BLOCKS; the Başlangıç/Bitiş
    selectboxes re-sync from it at the top of the panel on the next render
    (pending-flag pattern). Upstream of reverse/composite/recode — none touched.

    (Replaces the old col-max grouping, which collapsed for text Likert columns —
    every scale got a 1-item, overlapping block.)"""
    defined = list(st.session_state.get(KEY_DEFINED_SCALES, []))
    # Clear leftover propose/subdivide state from the old grouping flow.
    for key in list(st.session_state.keys()):
        if str(key).startswith("auto_subdivide_"):
            del st.session_state[key]
    st.session_state[KEY_PROPOSED_AUTO_BLOCKS] = []
    st.session_state["auto_detect_single_group"] = False

    scale_item_cols = _scale_item_columns_from_roles(col_list)  # ordered column names
    n_items = len(scale_item_cols)
    preset_map = st.session_state.get(KEY_SCALE_PRESET_MAP, {})
    blocks = _coerce_scale_blocks(st.session_state.get(KEY_SCALE_BLOCKS), defined)

    cursor = 0
    missing_preset: list[str] = []
    for scale in defined:
        count = int(preset_map.get(scale, {}).get("n_items") or 0)
        if count <= 0:
            missing_preset.append(scale)
            blocks[scale] = {"from_col": "", "to_col": ""}
            continue
        if cursor >= n_items:
            blocks[scale] = {"from_col": "", "to_col": ""}
            continue
        start = cursor
        end = min(cursor + count - 1, n_items - 1)
        blocks[scale] = {
            "from_col": scale_item_cols[start],
            "to_col": scale_item_cols[end],
        }
        cursor = end + 1

    st.session_state[KEY_SCALE_BLOCKS] = blocks
    # Drop the From/To widget keys so the selectboxes re-sync from KEY_SCALE_BLOCKS.
    _clear_block_bound_widget_keys(defined)

    # Edge handling: don't silently produce garbage on a column/preset mismatch.
    expected = sum(int(preset_map.get(s, {}).get("n_items") or 0) for s in defined)
    if missing_preset:
        st.session_state["scale_block_skip_warning"] = (
            "Hazır ayar madde sayısı olmayan ölçek(ler) atlandı: "
            + ", ".join(missing_preset)
            + " — bu ölçekler için blokları elle ayarlayın."
        )
    elif expected != n_items:
        st.session_state["scale_block_skip_warning"] = (
            f"Ölçek maddesi sütun sayısı ({n_items}), hazır ayar madde toplamı "
            f"({expected}) ile eşleşmiyor. Bloklar sırayla atandı; rolleri veya "
            "blokları elle doğrulayın."
        )


def _confirm_auto_blocks_action(col_list: list) -> bool:
    """Apply proposed auto blocks. Returns True on success."""
    defined = list(st.session_state.get(KEY_DEFINED_SCALES, []))
    proposed = st.session_state.get(KEY_PROPOSED_AUTO_BLOCKS, [])
    blocks = _coerce_scale_blocks(st.session_state.get(KEY_SCALE_BLOCKS), defined)
    errors: list[str] = []
    for block_num, group in enumerate(proposed, start=1):
        group_id = group["id"]
        subdivision_scales = group.get("subdivision_scales") or group.get(
            "matching_scales"
        ) or _unmatched_scales_for_group(
            defined, proposed, block_num - 1, group.get("max_val")
        )
        n_scale_items = group.get(
            "n_scale_items",
            _scale_item_count_in_group(col_list, group),
        )
        start_disp = group.get("start_idx", 0) + 1
        end_disp = group.get("end_idx", 0) + 1

        if group.get("needs_subdivision") and len(subdivision_scales) > 1:
            counts = []
            for scale in subdivision_scales:
                sub_key = f"auto_subdivide_{group_id}_{_block_widget_suffix(scale)}"
                counts.append(int(st.session_state.get(sub_key, 0)))
            if sum(counts) != n_scale_items:
                errors.append(
                    f"Block {block_num} (columns {start_disp}–{end_disp}): "
                    f"item counts must sum to {n_scale_items} (got {sum(counts)})."
                )
                continue
            if not _assign_subdivided_group(
                col_list, group, subdivision_scales, counts, blocks
            ):
                errors.append(
                    f"Block {block_num} (columns {start_disp}–{end_disp}): "
                    "could not apply subdivision."
                )
        else:
            scale_name = (
                group.get("default_scale")
                or st.session_state.get(f"auto_block_scale_{group_id}")
                or _auto_block_default_scale(block_num - 1, len(proposed), defined)
            )
            if scale_name:
                blocks[scale_name] = {
                    "from_col": group.get("from_col", ""),
                    "to_col": group.get("to_col", ""),
                }

    if errors:
        st.session_state[KEY_AUTO_DETECT_ERROR] = " ".join(errors)
        return False
    st.session_state[KEY_SCALE_BLOCKS] = blocks
    _clear_block_bound_widget_keys(defined)
    st.session_state[KEY_PROPOSED_AUTO_BLOCKS] = []
    st.session_state.pop(KEY_AUTO_DETECT_ERROR, None)
    return True


def _remove_defined_scale(scale: str) -> None:
    scales = st.session_state.get(KEY_DEFINED_SCALES, [])
    st.session_state[KEY_DEFINED_SCALES] = [s for s in scales if s != scale]
    defined = st.session_state[KEY_DEFINED_SCALES]
    blocks = _coerce_scale_blocks(st.session_state.get(KEY_SCALE_BLOCKS), defined)
    blocks.pop(scale, None)
    st.session_state[KEY_SCALE_BLOCKS] = blocks
    preset_map = dict(st.session_state.get(KEY_SCALE_PRESET_MAP, {}))
    preset_map.pop(scale, None)
    st.session_state[KEY_SCALE_PRESET_MAP] = preset_map


def _add_scale_preset(label: str) -> None:
    if not label or label == PRESET_CUSTOM_OPTION:
        return
    preset = SCALE_PRESETS.get(label)
    if not preset:
        return
    name = (preset.get("name") or "").strip()
    if not name:
        return
    scales = list(st.session_state.get(KEY_DEFINED_SCALES, []))
    if name not in scales:
        scales.append(name)
        st.session_state[KEY_DEFINED_SCALES] = scales
        blocks = _coerce_scale_blocks(st.session_state.get(KEY_SCALE_BLOCKS), scales)
        blocks[name] = {"from_col": "", "to_col": ""}
        st.session_state[KEY_SCALE_BLOCKS] = blocks
    preset_map = dict(st.session_state.get(KEY_SCALE_PRESET_MAP, {}))
    preset_map[name] = {
        "name": name,
        "n_items": preset.get("n_items"),
        "scale_range": preset.get("scale_range", (1, 5)),
        "reverse_items": list(preset.get("reverse_items") or []),
        "preset_label": label,
    }
    st.session_state[KEY_SCALE_PRESET_MAP] = preset_map


def _add_defined_scale(name: str) -> None:
    name = (name or "").strip()
    if not name:
        return
    scales = list(st.session_state.get(KEY_DEFINED_SCALES, []))
    if name not in scales:
        scales.append(name)
        st.session_state[KEY_DEFINED_SCALES] = scales
        blocks = _coerce_scale_blocks(st.session_state.get(KEY_SCALE_BLOCKS), scales)
        blocks[name] = {"from_col": "", "to_col": ""}
        st.session_state[KEY_SCALE_BLOCKS] = blocks


def _render_define_scales_panel() -> None:
    st.markdown("#### Ölçekleri Tanımla")
    preset_options = [PRESET_CUSTOM_OPTION, *SCALE_PRESETS.keys()]
    preset_col, add_preset_col = st.columns([4, 1])
    with preset_col:
        st.selectbox(
            "Ölçek hazır ayarı yükle",
            options=preset_options,
            key=KEY_LOAD_SCALE_PRESET,
        )
    with add_preset_col:
        if st.button("Hazır Ayar Ekle", key="add_scale_preset_btn"):
            selected = st.session_state.get(KEY_LOAD_SCALE_PRESET, PRESET_CUSTOM_OPTION)
            if selected and selected != PRESET_CUSTOM_OPTION:
                _add_scale_preset(selected)
                st.rerun()

    st.caption("Veya aşağıya özel ölçek adı ekleyin (hazır ayarlar toplayıcıdır).")
    input_col, button_col = st.columns([4, 1])
    with input_col:
        st.text_input(
            "Yeni ölçek adı",
            key=KEY_NEW_SCALE_INPUT,
            placeholder="ör. CBMO, Sharenting, PRFQ",
            label_visibility="collapsed",
        )
    with button_col:
        if st.button("Ölçek Ekle", key="add_defined_scale_btn"):
            name = (st.session_state.get(KEY_NEW_SCALE_INPUT) or "").strip()
            if name:
                _add_defined_scale(name)
                st.rerun()

    defined = st.session_state.get(KEY_DEFINED_SCALES, [])
    preset_map = st.session_state.get(KEY_SCALE_PRESET_MAP, {})
    if defined:
        for scale in defined:
            if scale in preset_map:
                meta = preset_map[scale]
                n = meta.get("n_items", "?")
                rev = meta.get("reverse_items") or []
                rev_note = f", ters maddeler {rev}" if rev else ""
                st.caption(f"**{scale}** — hazır ayar: {n} madde{rev_note}")
    if defined:
        chip_cols = st.columns(min(len(defined), 6) or 1)
        for idx, scale in enumerate(defined):
            with chip_cols[idx % len(chip_cols)]:
                if st.button(f"✕ {scale}", key=f"remove_defined_scale_{scale}"):
                    _remove_defined_scale(scale)
                    st.rerun()
    else:
        st.caption("Alt Aşama B'de ölçek bloklarını kullanmak için en az bir ölçek adı ekleyin.")


def _render_scale_blocks_panel(col_list: list, df: pd.DataFrame) -> None:
    st.markdown("#### Ölçek Blokları")
    defined = list(st.session_state.get(KEY_DEFINED_SCALES, []))
    scale_items = _scale_item_columns_from_roles(col_list)

    if not defined:
        st.info("Ölçek bloklarını kullanmadan önce yukarıda en az bir ölçek tanımlayın.")
        return
    if not scale_items:
        st.info("Onaylanan rollerde **Ölçek Maddesi** olarak işaretlenmiş sütun yok.")
        return

    blocks = _coerce_scale_blocks(st.session_state.get(KEY_SCALE_BLOCKS), defined)
    st.session_state[KEY_SCALE_BLOCKS] = blocks
    for scale_name, block in blocks.items():
        from_col = block.get("from_col") or ""
        to_col = block.get("to_col") or ""
        if from_col:
            st.session_state[_block_from_key(scale_name)] = from_col
        if to_col:
            st.session_state[_block_to_key(scale_name)] = to_col

    if st.button("🔍 Blokları Otomatik Tespit Et", key="auto_detect_blocks_btn"):
        if not st.session_state.get(KEY_COL_ROLES):
            st.warning(
                "Otomatik tespiti kullanmadan önce sütun rol atamasını tamamlayın ve "
                "Sütun Rollerini Onayla'ya tıklayın."
            )
        else:
            _run_auto_detect_blocks_action(col_list)
            st.rerun()

    if st.session_state.pop("auto_detect_single_group", False):
        st.info(
            "Tüm ölçek maddeleri aynı yanıt aralığına sahip. "
            "Bunun yerine manuel blok ataması kullanın."
        )

    auto_err = st.session_state.pop(KEY_AUTO_DETECT_ERROR, None)
    if auto_err:
        st.error(auto_err)

    proposed = st.session_state.get(KEY_PROPOSED_AUTO_BLOCKS, [])
    subdivision_valid = True
    if proposed:
        st.markdown("**Önerilen bloklar:**")
        for block_num, group in enumerate(proposed, start=1):
            group_id = group["id"]
            start_disp = group["start_idx"] + 1
            end_disp = group["end_idx"] + 1
            n_items = group.get(
                "n_scale_items",
                _scale_item_count_in_group(col_list, group),
            )
            max_val = group.get("max_val", "?")
            subdivision_scales = group.get("subdivision_scales") or group.get(
                "matching_scales"
            ) or _unmatched_scales_for_group(
                defined, proposed, block_num - 1, group.get("max_val")
            )
            header = (
                f"Blok {block_num}: Sütunlar {start_disp}-{end_disp} "
                f"({n_items} ölçek maddesi, maks={max_val})"
            )
            if group.get("needs_subdivision") and len(subdivision_scales) > 1:
                st.markdown(f"{header} — ölçeklere böl:")
                sub_cols = st.columns(min(len(subdivision_scales), 4) or 1)
                block_sum = 0
                n_scales = len(subdivision_scales)
                preset_counts = _subdivision_counts_from_presets(
                    subdivision_scales, n_items
                )
                exact_equal = _is_exact_equal_subdivision(n_items, n_scales)
                per_scale = n_items // n_scales if exact_equal else 0
                for idx, scale in enumerate(subdivision_scales):
                    sub_key = f"auto_subdivide_{group_id}_{_block_widget_suffix(scale)}"
                    if sub_key not in st.session_state:
                        if preset_counts is not None:
                            st.session_state[sub_key] = preset_counts[idx]
                        elif exact_equal:
                            st.session_state[sub_key] = per_scale
                        else:
                            st.session_state[sub_key] = 0
                    with sub_cols[idx % len(sub_cols)]:
                        st.number_input(
                            f"{scale} için kaç madde?",
                            min_value=0,
                            max_value=n_items,
                            step=1,
                            placeholder=f"{scale} — ör. 23",
                            key=sub_key,
                        )
                    block_sum += int(st.session_state.get(sub_key, 0))
                sum_ok = block_sum == n_items
                if sum_ok:
                    st.caption(f"Madde sayısı toplamı: **{block_sum}** / {n_items} ✓")
                else:
                    st.caption(
                        f"Madde sayısı toplamı: **{block_sum}** / {n_items} "
                        "(onaylamak için eşleşmeli)"
                    )
                    subdivision_valid = False
            else:
                default_scale = group.get("default_scale") or _auto_block_default_scale(
                    block_num - 1, len(proposed), defined
                )
                scale_index = (
                    defined.index(default_scale)
                    if default_scale in defined
                    else 0
                )
                chosen = st.selectbox(
                    f"{header} → ata:",
                    options=defined,
                    index=scale_index,
                    key=f"auto_block_scale_{group_id}",
                )
                st.caption(f"**{chosen}** ölçeğine atandı")
        if st.button(
            "Otomatik Tespiti Onayla",
            key="confirm_auto_blocks_btn",
            type="primary",
            disabled=not subdivision_valid,
        ):
            _confirm_auto_blocks_action(col_list)
            st.rerun()
        if not subdivision_valid:
            st.caption(
                "Her bloğun madde toplamının toplam sayıyla eşleşmesi için alt bölüm sayılarını düzeltin."
            )

    st.caption(
        "Tanımlanan her ölçek için bir satır. Bloklar sütunları yukarıdan aşağı tüketir "
        "(sıra ölçek listenizi izler)."
    )
    header = st.columns([2, 3, 3])
    header[0].markdown("**Ölçek**")
    header[1].markdown("**Başlangıç**")
    header[2].markdown("**Bitiş**")

    for scale_index, scale in enumerate(defined):
        entry = blocks.get(scale, {})
        suffix = _block_widget_suffix(scale)
        claimed = _claimed_indices_before_scale(col_list, blocks, defined, scale_index)
        from_options = _available_from_columns(col_list, scale_items, claimed)
        row = st.columns([2, 3, 3])

        with row[0]:
            st.markdown(f"**{scale}**")
        with row[1]:
            if from_options:
                from_val = entry.get("from_col", "")
                from_index = (
                    from_options.index(from_val) if from_val in from_options else 0
                )
                st.selectbox(
                    "Başlangıç",
                    options=from_options,
                    index=from_index,
                    format_func=lambda c: _column_mapper_label(col_list, c),
                    key=_block_from_key(scale),
                    label_visibility="collapsed",
                )
            else:
                st.caption("Kalan sütun yok")
        with row[2]:
            current_from = st.session_state.get(
                _block_from_key(scale), entry.get("from_col", "")
            )
            to_options = _available_to_columns(col_list, current_from, scale_items)
            if to_options:
                to_val = entry.get("to_col", "")
                to_index = (
                    to_options.index(to_val) if to_val in to_options else 0
                )
                st.selectbox(
                    "Bitiş",
                    options=to_options,
                    index=to_index,
                    format_func=lambda c: _column_mapper_label(col_list, c),
                    key=_block_to_key(scale),
                    label_visibility="collapsed",
                )
            else:
                st.caption("—")

    if st.button("Tüm Blokları Uygula", key="apply_all_blocks_btn", type="primary"):
        _apply_all_blocks_action(col_list)
        st.rerun()

    for msg in st.session_state.pop(KEY_SCALE_BLOCK_MESSAGES, []):
        st.success(msg)
    skip_warn = st.session_state.pop("scale_block_skip_warning", None)
    if skip_warn:
        st.warning(skip_warn)


def _on_short_label_change(col_index: int) -> None:
    """Pending flag only — never write short_label_* keys here."""
    st.session_state[f"{PENDING_SHORT_LABEL_MANUAL}_{col_index}"] = True


def _init_mapper_widget_state(column_count: int, col_list: list, df: pd.DataFrame) -> None:
    for i in range(column_count):
        col = col_list[i]
        if _role_key(i) not in st.session_state:
            role, reason = _classify_column_with_reason(col, df[col])
            st.session_state[_role_key(i)] = role
            st.session_state[_role_reason_key(i)] = reason
        if _scale_name_key(i) not in st.session_state:
            st.session_state[_scale_name_key(i)] = ""
        if _short_label_key(i) not in st.session_state:
            st.session_state[_short_label_key(i)] = ""


def _scale_bounds_for_name(scale_name: str) -> tuple[int, int]:
    normalized = (scale_name or "").strip().lower()
    for key, bounds in KNOWN_SCALE_BOUNDS.items():
        if key in normalized:
            return bounds
    return (1, 5)


def _scale_item_raw_columns() -> list[str]:
    roles = st.session_state.get(KEY_COL_ROLES, {})
    return [col for col, role in roles.items() if role == "scale_item"]


def _build_analysis_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Non-ignored columns; scale items renamed to short labels."""
    roles = st.session_state.get(KEY_COL_ROLES, {})
    short_labels = st.session_state.get(KEY_SHORT_LABELS, {})
    out: dict[str, pd.Series] = {}
    for col in raw_df.columns:
        role = roles.get(col)
        if role == "ignore":
            continue
        if role == "scale_item":
            short = short_labels.get(col)
            if short:
                out[short] = raw_df[col]
        else:
            out[col] = raw_df[col]
    return pd.DataFrame(out)


def _recode_cols_by_scale() -> dict[str, list[str]]:
    """Scale name → its scale-item raw column names (from roles + scale map)."""
    scale_map = st.session_state.get(KEY_SCALE_MAP, {})
    grouped: dict[str, list[str]] = {}
    for raw_col in _scale_item_raw_columns():
        grouped.setdefault(scale_map.get(raw_col, "—"), []).append(raw_col)
    return grouped


def _recode_value_text(value) -> str:
    """Canonical string form of a raw cell, used as the recode-map key.

    The SAME normalization is used when gathering unique values and when applying
    the map, so numeric cells (already-numeric scales in a mixed dataset) and text
    cells round-trip consistently.
    """
    return str(value).strip()


def _unique_text_values_for_scale(raw_df: pd.DataFrame, raw_cols: list[str]) -> list[str]:
    """Sorted unique non-null response strings across a scale's item columns."""
    values: set[str] = set()
    for col in raw_cols:
        if col not in raw_df.columns:
            continue
        for v in raw_df[col].dropna().unique():
            text = _recode_value_text(v)
            if text:
                values.add(text)
    return sorted(values, key=_recode_sort_key)


def _recode_sort_key(value: str):
    """Numbered values first (by their integer), word values after (alphabetical)."""
    match = _LEADING_INT_RE.match(value)
    if match:
        return (0, int(match.group(1)), "")
    return (1, 0, _normalize_response_text(value))


def _detect_recode_pattern(values: list[str]) -> str:
    """'leading_number' if every value starts with an integer, else 'words'."""
    if values and all(_LEADING_INT_RE.match(v) for v in values):
        return "leading_number"
    return "words"


def _propose_recode_for_scale(values: list[str], pattern: str) -> dict[str, int | None]:
    """Proposed number per value; None means 'unknown — user must fill'."""
    proposed: dict[str, int | None] = {}
    for v in values:
        if pattern == "leading_number":
            match = _LEADING_INT_RE.match(v)
            proposed[v] = int(match.group(1)) if match else None
        else:
            proposed[v] = _TR_FREQ_WORDS_5.get(_normalize_response_text(v))
    return proposed


def _recode_input_key(scale_name: str, value: str) -> str:
    """Stable widget key per (scale, value) — hashed so arbitrary text is key-safe."""
    digest = hashlib.md5(f"{scale_name}\x1f{value}".encode("utf-8")).hexdigest()[:12]
    return f"recode_num_{digest}"


def _all_scale_columns_numeric(raw_df: pd.DataFrame) -> bool:
    """True if every scale-item column is already a numeric dtype (no recoding needed)."""
    cols = [c for c in _scale_item_raw_columns() if c in raw_df.columns]
    if not cols:
        return True
    return all(pd.api.types.is_numeric_dtype(raw_df[c]) for c in cols)


def _build_recoded_analysis_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Like _build_analysis_dataframe, but first map text Likert responses to numbers
    via KEY_RECODE_MAP (per scale). Reuses _build_analysis_dataframe for the
    short-label/demographic structure so Steps 3–4 are unaffected. Empty map (skip /
    already-numeric data) → identity. KEY_RAW_DF is never mutated."""
    recode_map = st.session_state.get(KEY_RECODE_MAP, {})
    if not recode_map:
        return _build_analysis_dataframe(raw_df)
    scale_map = st.session_state.get(KEY_SCALE_MAP, {})
    recoded = raw_df.copy()
    for raw_col in _scale_item_raw_columns():
        if raw_col not in recoded.columns:
            continue
        mapping = recode_map.get(scale_map.get(raw_col))
        if not mapping:
            continue
        # Normalize each cell to the same string form used as map keys; values not in
        # the map become NaN (validation should have prevented that for real data).
        normalized = recoded[raw_col].map(
            lambda v: _recode_value_text(v) if pd.notna(v) else v
        )
        recoded[raw_col] = pd.to_numeric(normalized.map(mapping), errors="coerce")
    return _build_analysis_dataframe(recoded)


def _existing_column_names() -> set[str]:
    names: set[str] = set()
    working_df = st.session_state.get(KEY_WORKING_DF)
    if working_df is not None:
        names.update(working_df.columns)
    if st.session_state.get(KEY_MAPPING_DONE):
        names.update(st.session_state.get(KEY_SHORT_LABELS, {}).values())
    return names


def _export_config_dict() -> dict:
    return {
        "version": CONFIG_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        KEY_COL_ROLES: st.session_state.get(KEY_COL_ROLES, {}),
        KEY_SCALE_MAP: st.session_state.get(KEY_SCALE_MAP, {}),
        KEY_SHORT_LABELS: st.session_state.get(KEY_SHORT_LABELS, {}),
        KEY_REVERSE_CONFIG: st.session_state.get(KEY_REVERSE_CONFIG, {}),
        KEY_COMPOSITE_CONFIG: st.session_state.get(KEY_COMPOSITE_CONFIG, []),
        KEY_MAPPING_DONE: st.session_state.get(KEY_MAPPING_DONE, False),
        KEY_REVERSE_DONE: st.session_state.get(KEY_REVERSE_DONE, False),
        KEY_RECODE_MAP: st.session_state.get(KEY_RECODE_MAP, {}),
        KEY_RECODE_DONE: st.session_state.get(KEY_RECODE_DONE, False),
    }


def _find_zip_member(names: list[str], basename: str) -> str | None:
    for name in names:
        if name == basename or name.endswith(f"/{basename}"):
            return name
    return None


def _build_session_zip_bytes(final_df: pd.DataFrame) -> bytes:
    raw_df = st.session_state.get(KEY_RAW_DF)
    if raw_df is None:
        raise ValueError("No source data available to save.")
    # Save the RECODED/numeric source (recode applied, reverse not yet) so the restore
    # replay — _apply_reverse_config_to_dataframe in _finalize_full_session_after_load —
    # operates on numbers, matching the fresh path. Saving the un-recoded text source
    # would crash reverse scoring with int − str on text-Likert data.
    source_df = _build_recoded_analysis_dataframe(raw_df)
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        config_json = json.dumps(_export_config_dict(), indent=2, ensure_ascii=False)
        zf.writestr("psychstats_config.json", config_json.encode("utf-8"))
        zf.writestr(
            "psychstats_source.csv",
            source_df.to_csv(index=False).encode("utf-8-sig"),
        )
        zf.writestr(
            "psychstats_final.csv",
            final_df.to_csv(index=False).encode("utf-8-sig"),
        )
    return buf.getvalue()


def _apply_reverse_config_to_dataframe(
    working_df: pd.DataFrame,
    reverse_config: dict[str, dict],
    short_labels: dict[str, str],
) -> pd.DataFrame:
    """Apply saved reverse rules to a short-label working copy (same math as Step 3)."""
    out = working_df.copy()
    for raw_col, bounds in reverse_config.items():
        short = short_labels.get(raw_col)
        if not short or short not in out.columns:
            continue
        vmin = int(bounds.get("min", 1))
        vmax = int(bounds.get("max", 5))
        out[short] = (vmax + vmin) - out[short]
    return out


def _apply_full_session_from_zip(zip_bytes: bytes) -> list[str]:
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        config_name = _find_zip_member(names, "psychstats_config.json")
        source_name = _find_zip_member(names, "psychstats_source.csv")
        final_name = _find_zip_member(names, "psychstats_final.csv")
        if not config_name or not source_name or not final_name:
            raise ValueError(
                "Zip must contain psychstats_config.json, psychstats_source.csv, "
                "and psychstats_final.csv."
            )
        config = json.loads(zf.read(config_name).decode("utf-8"))
        source_df = pd.read_csv(
            BytesIO(zf.read(source_name)), encoding="utf-8-sig"
        )
        final_df = pd.read_csv(BytesIO(zf.read(final_name)), encoding="utf-8-sig")

    _apply_config_to_session(
        {
            KEY_COL_ROLES: config.get(KEY_COL_ROLES, {}),
            KEY_SCALE_MAP: config.get(KEY_SCALE_MAP, {}),
            KEY_SHORT_LABELS: config.get(KEY_SHORT_LABELS, {}),
            KEY_REVERSE_CONFIG: config.get(KEY_REVERSE_CONFIG, {}),
            KEY_COMPOSITE_CONFIG: config.get(KEY_COMPOSITE_CONFIG, []),
            KEY_MAPPING_DONE: config.get(KEY_MAPPING_DONE, True),
        }
    )
    _restore_full_session_config_from_json(config)
    warnings, _ = _reconcile_config(config, list(source_df.columns))

    st.session_state[KEY_PARSE_SIG] = ("psychstats_session", len(source_df.columns))
    st.session_state[KEY_UPLOAD_BYTES] = None
    st.session_state[KEY_UPLOAD_FILE_SIG] = None
    st.session_state.pop(KEY_PENDING_CONFIG, None)
    st.session_state.pop(KEY_XLSX_SHEETS, None)
    _finalize_full_session_after_load(source_df, final_df)
    return warnings


def _restore_full_session_config_from_json(config: dict) -> None:
    """Restore preprocessing metadata from the saved zip (not column-filtered reconcile)."""
    if config.get(KEY_REVERSE_CONFIG) is not None:
        st.session_state[KEY_REVERSE_CONFIG] = dict(config[KEY_REVERSE_CONFIG])
    for key in (KEY_COL_ROLES, KEY_SCALE_MAP, KEY_SHORT_LABELS):
        if config.get(key):
            st.session_state[key] = dict(config[key])
    if config.get(KEY_RECODE_MAP) is not None:
        st.session_state[KEY_RECODE_MAP] = dict(config[KEY_RECODE_MAP])
    composites = config.get(KEY_COMPOSITE_CONFIG)
    if composites is not None:
        st.session_state[KEY_COMPOSITE_CONFIG] = _normalize_composite_list(composites)


def _finalize_full_session_after_load(
    source_df: pd.DataFrame,
    final_df: pd.DataFrame,
) -> None:
    """Restore to end-of-Step-4 state; Steps 3–4 pre-filled if she uses ← back buttons."""
    ss = st.session_state
    source_copy = source_df.copy()
    final_copy = final_df.copy()
    short_labels = ss.get(KEY_SHORT_LABELS, {})
    reverse_config = ss.get(KEY_REVERSE_CONFIG, {})
    ss[KEY_RAW_DF] = source_copy
    ss[KEY_FINAL_DF] = final_copy
    ss[KEY_WORKING_DF] = _apply_reverse_config_to_dataframe(
        source_copy, reverse_config, short_labels
    )
    ss[KEY_UPLOAD_DONE] = True
    ss[KEY_ROLES_CONFIRMED] = True
    ss[KEY_MAPPING_DONE] = True
    # The saved source CSV is recoded/numeric (written via _build_recoded_analysis_dataframe
    # in _build_session_zip_bytes), so recoding is effectively done.
    ss[KEY_RECODE_DONE] = True
    ss[KEY_RECODE_PRIMED] = False
    ss[KEY_REVERSE_DONE] = True


def _render_save_full_session_button(final_df: pd.DataFrame) -> None:
    st.markdown("---")
    st.download_button(
        "💾 Tam Oturumu Kaydet",
        data=_build_session_zip_bytes(final_df),
        file_name="psychstats_session.zip",
        mime="application/zip",
        key="download_psychstats_session",
        help=(
            "Analize hazır veriyi ve ön işleme yapılandırmasını indirin; "
            "Adım 1'de tek adımda yeniden yükleyebilirsiniz."
        ),
    )


def _reconcile_config(config: dict, raw_columns: list[str]) -> tuple[dict, list[str]]:
    """Return cleaned config subset and human-readable warnings."""
    warnings: list[str] = []
    roles = config.get(KEY_COL_ROLES, {})
    scale_map = config.get(KEY_SCALE_MAP, {})
    short_labels = config.get(KEY_SHORT_LABELS, {})
    reverse_config = config.get(KEY_REVERSE_CONFIG, {})
    composites = config.get(KEY_COMPOSITE_CONFIG, [])

    config_cols = set(roles.keys())
    raw_set = set(raw_columns)

    missing_in_data = sorted(config_cols - raw_set)
    missing_in_config = sorted(raw_set - config_cols)

    if missing_in_data:
        warnings.append(
            f"Config references {len(missing_in_data)} column(s) not in the current file: "
            + ", ".join(missing_in_data[:5])
            + ("…" if len(missing_in_data) > 5 else "")
        )
    if missing_in_config:
        warnings.append(
            f"Current file has {len(missing_in_config)} column(s) without config: "
            + ", ".join(missing_in_config[:5])
            + ("…" if len(missing_in_config) > 5 else "")
        )

    cleaned_roles = {c: roles[c] for c in raw_columns if c in roles}
    cleaned_scale = {c: scale_map[c] for c in raw_columns if c in scale_map}
    cleaned_short = {c: short_labels[c] for c in raw_columns if c in short_labels}
    cleaned_reverse = {c: reverse_config[c] for c in raw_columns if c in reverse_config}

    expected_short = set(cleaned_short.values())
    for comp in composites:
        for col in comp.get("cols", comp.get("columns", [])):
            if col not in expected_short and col not in raw_set:
                warnings.append(
                    f"Composite `{comp.get('name', '?')}` references unknown column `{col}`."
                )

    cleaned = {
        KEY_COL_ROLES: cleaned_roles,
        KEY_SCALE_MAP: cleaned_scale,
        KEY_SHORT_LABELS: cleaned_short,
        KEY_REVERSE_CONFIG: cleaned_reverse,
        KEY_COMPOSITE_CONFIG: composites,
        KEY_MAPPING_DONE: bool(cleaned_roles) and not missing_in_config,
        KEY_REVERSE_DONE: False,
        # Recode map is keyed by scale name (not column) — keep only scales still present.
        KEY_RECODE_MAP: {
            scale: vals
            for scale, vals in (config.get(KEY_RECODE_MAP, {}) or {}).items()
            if scale in set(cleaned_scale.values())
        },
        KEY_RECODE_DONE: False,
    }
    return cleaned, warnings


def _apply_config_to_widgets(config: dict, raw_columns: list[str]) -> None:
    roles = config.get(KEY_COL_ROLES, {})
    scale_map = config.get(KEY_SCALE_MAP, {})
    short_labels = config.get(KEY_SHORT_LABELS, {})

    defined_scales = list(st.session_state.get(KEY_DEFINED_SCALES, []))
    for i, col in enumerate(raw_columns):
        role_key = roles.get(col, "ignore")
        st.session_state[_role_key(i)] = KEY_TO_ROLE.get(role_key, ROLE_IGNORE)
        scale_name = scale_map.get(col, "")
        st.session_state[_scale_name_key(i)] = scale_name
        if scale_name and scale_name not in defined_scales:
            defined_scales.append(scale_name)
        st.session_state[_short_label_key(i)] = _sanitize_short_label(short_labels.get(col, ""))
        if short_labels.get(col):
            st.session_state[_short_label_manual_key(i)] = True
    st.session_state[KEY_DEFINED_SCALES] = defined_scales


def _apply_config_to_session(cleaned: dict) -> None:
    st.session_state[KEY_COL_ROLES] = cleaned.get(KEY_COL_ROLES, {})
    st.session_state[KEY_SCALE_MAP] = cleaned.get(KEY_SCALE_MAP, {})
    st.session_state[KEY_SHORT_LABELS] = cleaned.get(KEY_SHORT_LABELS, {})
    st.session_state[KEY_REVERSE_CONFIG] = cleaned.get(KEY_REVERSE_CONFIG, {})
    st.session_state[KEY_COMPOSITE_CONFIG] = cleaned.get(KEY_COMPOSITE_CONFIG, [])
    st.session_state[KEY_ROLES_CONFIRMED] = bool(cleaned.get(KEY_COL_ROLES))
    st.session_state[KEY_MAPPING_DONE] = cleaned.get(KEY_MAPPING_DONE, False)
    st.session_state[KEY_REVERSE_DONE] = False
    st.session_state[KEY_REVERSE_PRIMED] = False
    st.session_state[KEY_RECODE_MAP] = cleaned.get(KEY_RECODE_MAP, {})
    st.session_state[KEY_RECODE_DONE] = cleaned.get(KEY_RECODE_DONE, False)
    st.session_state[KEY_RECODE_PRIMED] = False
    st.session_state.pop(KEY_RECODE_PREVIEW, None)
    st.session_state[KEY_WORKING_DF] = None
    st.session_state[KEY_FINAL_DF] = None


def _clear_column_mapper_widgets():
    prefixes = (
        "role_select_",
        "scale_name_",
        "short_label_",
        "_short_label_",
        "_role_default_reason_",
    )
    for key in list(st.session_state.keys()):
        if any(key.startswith(p) for p in prefixes):
            del st.session_state[key]
    st.session_state[PENDING_RESYNC_LABELS] = False


def _clear_recode_widget_keys() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith("recode_num_"):
            del st.session_state[key]


def _reset_recode_state() -> None:
    """Clear recoding so it is re-done from scratch (scales/values may have changed)."""
    st.session_state[KEY_RECODE_DONE] = False
    st.session_state[KEY_RECODE_PRIMED] = False
    st.session_state[KEY_RECODE_MAP] = {}
    st.session_state.pop(KEY_RECODE_PREVIEW, None)
    _clear_recode_widget_keys()


def _redo_recoding() -> None:
    """Recode back button: reset recoding + downstream (reverse/composite/final).

    Keeps KEY_RECODE_MAP so re-priming restores the user's last numbers; resets the
    prime flag so the panel re-renders the inputs. Upstream scale assignment is left
    intact (use the reverse step's own back button to redo column/scale assignment)."""
    st.session_state[KEY_RECODE_DONE] = False
    st.session_state[KEY_RECODE_PRIMED] = False
    st.session_state.pop(KEY_RECODE_PREVIEW, None)
    st.session_state[KEY_WORKING_DF] = None
    st.session_state[KEY_REVERSE_DONE] = False
    st.session_state[KEY_REVERSE_PRIMED] = False
    st.session_state[KEY_REVERSE_CONFIG] = {}
    st.session_state[KEY_COMPOSITE_CONFIG] = []
    st.session_state[KEY_FINAL_DF] = None
    _clear_reverse_locked_keys()


def _reset_preprocessing_state():
    st.session_state[KEY_MAPPING_DONE] = False
    st.session_state[KEY_ROLES_CONFIRMED] = False
    st.session_state[KEY_REVERSE_DONE] = False
    _reset_recode_state()
    st.session_state[KEY_WORKING_DF] = None
    st.session_state[KEY_FINAL_DF] = None
    st.session_state[KEY_COL_ROLES] = {}
    st.session_state[KEY_SCALE_MAP] = {}
    st.session_state[KEY_SHORT_LABELS] = {}
    st.session_state[KEY_SCALE_PRESET_MAP] = {}
    st.session_state[KEY_REVERSE_CONFIG] = {}
    st.session_state[KEY_COMPOSITE_CONFIG] = []
    _clear_column_mapper_widgets()


def _start_fresh_from_saved_session() -> None:
    _reset_preprocessing_state()
    st.session_state[KEY_RAW_DF] = None
    st.session_state[KEY_UPLOAD_DONE] = False
    st.session_state[KEY_UPLOAD_BYTES] = None
    st.session_state[KEY_UPLOAD_FILE_SIG] = None
    st.session_state[KEY_PARSE_SIG] = None
    st.session_state.pop(KEY_SESSION_ZIP_SIG, None)
    _clear_reverse_locked_keys()


def _raw_df_looks_like_saved_source(df: pd.DataFrame) -> bool:
    short_vals = {
        v for v in st.session_state.get(KEY_SHORT_LABELS, {}).values() if v
    }
    if not short_vals:
        return False
    return bool(set(df.columns) & short_vals)


def _redo_column_mapping():
    st.session_state[KEY_REVERSE_CONFIG] = {}
    st.session_state[KEY_COMPOSITE_CONFIG] = []
    st.session_state[KEY_FINAL_DF] = None
    st.session_state[KEY_MAPPING_DONE] = False
    st.session_state[KEY_ROLES_CONFIRMED] = False
    st.session_state[KEY_SCALE_MAP] = {}
    st.session_state[KEY_SHORT_LABELS] = {}
    st.session_state[KEY_SCALE_PRESET_MAP] = {}
    st.session_state[KEY_REVERSE_PRIMED] = False
    _reset_recode_state()
    st.session_state[KEY_WORKING_DF] = None
    _clear_reverse_locked_keys()


def _redo_reverse_scoring():
    st.session_state[KEY_REVERSE_DONE] = False
    st.session_state[KEY_REVERSE_PRIMED] = False
    st.session_state[KEY_WORKING_DF] = None
    st.session_state[KEY_COMPOSITE_CONFIG] = []
    st.session_state[KEY_FINAL_DF] = None
    _clear_reverse_locked_keys()


def _reversed_short_label_set() -> set[str]:
    reverse_config = st.session_state.get(KEY_REVERSE_CONFIG, {})
    short_labels = st.session_state.get(KEY_SHORT_LABELS, {})
    return {short_labels[raw] for raw in reverse_config if raw in short_labels}


def _item_short_label_sort_key(short_label: str) -> int:
    match = re.search(r"(\d+)$", str(short_label))
    return int(match.group(1)) if match else 0


def _composite_cols(comp: dict) -> list[str]:
    return list(comp.get("cols", comp.get("columns", [])) or [])


def _composite_multiselect_prefix() -> str:
    if st.session_state.get(KEY_EDITING_COMPOSITE_ID):
        return "edit_composite_ms"
    return "composite_ms"


def _get_editing_composite() -> dict | None:
    editing_id = st.session_state.get(KEY_EDITING_COMPOSITE_ID)
    if not editing_id:
        return None
    for comp in _normalize_composite_list(st.session_state.get(KEY_COMPOSITE_CONFIG, [])):
        if comp.get("id") == editing_id:
            return comp
    return None


def _selected_composite_columns() -> list[str]:
    grouped = _composite_options_by_scale()
    prefix = _composite_multiselect_prefix()
    selected: list[str] = []
    for scale_name, cols in grouped.items():
        ms_key = f"{prefix}_{_block_widget_suffix(scale_name)}"
        selected.extend(st.session_state.get(ms_key, []))
    return [col for col in selected if isinstance(col, str)]


def _consume_composite_form_pending() -> None:
    if st.session_state.pop(PENDING_CLEAR_COMPOSITE_FORM, False):
        st.session_state[KEY_COMPOSITE_ITEMS_CHECKED] = {}
        st.session_state[PENDING_MULTISELECT_RESET] = True
        st.session_state[KEY_COMPOSITE_NAME_INPUT] = ""
        st.session_state[KEY_COMPOSITE_SUBMIT_ATTEMPTED] = False
        st.session_state.pop(KEY_EDITING_COMPOSITE_ID, None)


def _composite_name_available(name: str, editing_id: str | None = None) -> bool:
    composites = _normalize_composite_list(st.session_state.get(KEY_COMPOSITE_CONFIG, []))
    other_names = {
        c.get("name")
        for c in composites
        if c.get("id") != editing_id and c.get("name")
    }
    if name in other_names:
        return False
    taken = _existing_column_names()
    if editing_id:
        old_name = next(
            (c.get("name") for c in composites if c.get("id") == editing_id),
            None,
        )
        if old_name:
            taken = taken - {old_name}
    return name not in taken


def _consume_pending_start_editing() -> None:
    pending = st.session_state.pop(PENDING_START_EDITING, None)
    if not pending or not isinstance(pending, dict):
        return
    comp = _ensure_composite_id(dict(pending))
    st.session_state[KEY_EDITING_COMPOSITE_ID] = comp["id"]
    st.session_state[KEY_COMPOSITE_NAME_INPUT] = comp.get("name", "")
    method = comp.get("method", "sum")
    st.session_state[KEY_COMPOSITE_METHOD] = (
        METHOD_SUM_LABEL if method == "sum" else METHOD_MEAN_LABEL
    )
    st.session_state[PENDING_MULTISELECT_RESET] = True
    st.session_state[KEY_COMPOSITE_SUBMIT_ATTEMPTED] = False


def _update_composite_by_id(
    comp_id: str,
    name: str,
    columns: list[str],
    method: str,
) -> None:
    composites = _normalize_composite_list(st.session_state.get(KEY_COMPOSITE_CONFIG, []))
    updated: list[dict] = []
    for comp in composites:
        if comp.get("id") == comp_id:
            updated.append(
                {
                    "id": comp_id,
                    "name": name,
                    "columns": columns,
                    "method": method,
                }
            )
        else:
            updated.append(comp)
    st.session_state[KEY_COMPOSITE_CONFIG] = updated


def _select_all_scale_checkboxes(scale_name: str, cols: list[str]) -> None:
    if not scale_name or not cols:
        return
    prefix = _composite_multiselect_prefix()
    st.session_state[f"{prefix}_{_block_widget_suffix(scale_name)}"] = list(cols)


def _append_suggestions_by_method(method: str) -> None:
    """Append suggested composites matching method; remove only those added from suggestions."""
    suggestions = st.session_state.get(KEY_COMPOSITE_SUGGESTIONS, [])
    existing = _existing_column_names()
    composites = _normalize_composite_list(
        st.session_state.get(KEY_COMPOSITE_CONFIG, [])
    )
    taken_names = {c.get("name") for c in composites if c.get("name")}
    added_ids: set[str] = set()
    for comp in suggestions:
        suggested = _ensure_composite_id(dict(comp))
        if suggested.get("method", "sum") != method:
            continue
        suggested_name = suggested.get("name", "")
        if (
            not suggested_name
            or suggested_name in existing
            or suggested_name in taken_names
        ):
            continue
        composites.append(suggested)
        taken_names.add(suggested_name)
        existing.add(suggested_name)
        added_ids.add(suggested["id"])
    st.session_state[KEY_COMPOSITE_CONFIG] = composites
    st.session_state[KEY_COMPOSITE_SUGGESTIONS] = [
        s
        for s in suggestions
        if _ensure_composite_id(s).get("id") not in added_ids
    ]
    st.session_state.pop("_composite_suggested_error", None)


def _add_suggested_composite(comp: dict) -> str | None:
    """Append a suggested composite. Returns error message or None."""
    comp = _ensure_composite_id(dict(comp))
    comp_name = comp.get("name", "")
    if comp_name in _existing_column_names():
        return f"Column `{comp_name}` already exists."
    composites = _normalize_composite_list(st.session_state.get(KEY_COMPOSITE_CONFIG, []))
    composites.append(comp)
    st.session_state[KEY_COMPOSITE_CONFIG] = composites
    comp_id = comp["id"]
    remaining = [
        s
        for s in st.session_state.get(KEY_COMPOSITE_SUGGESTIONS, [])
        if s.get("id") != comp_id
    ]
    st.session_state[KEY_COMPOSITE_SUGGESTIONS] = remaining
    return None


def _delete_composite_by_id(comp_id: str) -> None:
    composites = _normalize_composite_list(st.session_state.get(KEY_COMPOSITE_CONFIG, []))
    removed_name: str | None = None
    remaining: list[dict] = []
    for comp in composites:
        if comp.get("id") == comp_id:
            removed_name = comp.get("name")
        else:
            remaining.append(comp)
    st.session_state[KEY_COMPOSITE_CONFIG] = remaining
    if removed_name:
        final_df = st.session_state.get(KEY_FINAL_DF)
        if final_df is not None:
            st.session_state[KEY_FINAL_DF] = final_df.drop(
                columns=[removed_name], errors="ignore"
            )


def _composite_name_for_scale(scale_name: str, method_label: str) -> str:
    safe = _sanitize_short_label(scale_name) or "Scale"
    suffix = "Total" if method_label == METHOD_SUM_LABEL else "Mean"
    return f"{safe}_{suffix}"


def _render_select_all_scale_buttons(grouped: dict[str, list[str]]) -> None:
    if not grouped:
        return
    st.caption("Aşağıdan bir ölçeğin tüm maddelerini seçin.")
    method_label = st.session_state.get(KEY_COMPOSITE_METHOD, METHOD_SUM_LABEL)
    scale_names = list(grouped.keys())
    btn_cols = st.columns(min(len(scale_names), 4) or 1)
    for idx, scale_name in enumerate(scale_names):
        with btn_cols[idx % len(btn_cols)]:
            if st.button(
                f"Tümünü seç: {scale_name}",
                key=f"select_all_composite_{scale_name}",
            ):
                _select_all_scale_checkboxes(scale_name, grouped.get(scale_name, []))
                st.session_state[KEY_COMPOSITE_NAME_INPUT] = _composite_name_for_scale(
                    scale_name, method_label
                )
                st.rerun()


def _render_composite_item_multiselect(
    grouped: dict[str, list[str]], *, editing: bool = False
) -> None:
    if not grouped:
        return
    reversed_set = _reversed_short_label_set()
    prefix = "edit_composite_ms" if editing else "composite_ms"

    def _format_item(col: str) -> str:
        return f"{col} [R]" if col in reversed_set else col

    for scale_name, cols in grouped.items():
        st.multiselect(
            scale_name,
            options=cols,
            format_func=_format_item,
            key=f"{prefix}_{_block_widget_suffix(scale_name)}",
        )


def _render_batch_subscale_panel(grouped: dict[str, list[str]]) -> None:
    if st.session_state.pop(PENDING_CLEAR_BATCH_FORM, False):
        st.session_state["batch_subscale_name"] = ""
        st.session_state["batch_subscale_items"] = []

    # Load a staged row back into the "Tanım ekle" form for in-place editing.
    # Pending-flag pattern: written here, BEFORE the form widgets instantiate
    # (the Düzenle buttons live below the form, so we can't write their keys directly).
    pending_edit = st.session_state.pop(PENDING_BATCH_EDIT_LOAD, None)
    if pending_edit:
        st.session_state[KEY_BATCH_EDIT_ID] = pending_edit.get("id")
        edit_scale = pending_edit.get("scale", "")
        if edit_scale in grouped:
            st.session_state["batch_scale_select"] = edit_scale
        st.session_state["batch_subscale_name"] = pending_edit.get("name", "")
        st.session_state["batch_subscale_items"] = [
            c for c in pending_edit.get("cols", []) if c in grouped.get(edit_scale, [])
        ]

    with st.expander("📦 Toplu Alt Ölçek Oluşturucu", expanded=False):
        st.caption(
            "Birden fazla alt ölçeği aynı anda tanımlayın, ardından tek tıkla tüm bileşikleri oluşturun."
        )
        scale_keys = list(grouped.keys())
        default_scale = scale_keys[0] if scale_keys else ""
        if default_scale and not st.session_state.get("batch_scale_select"):
            st.session_state["batch_scale_select"] = default_scale

        # Drop a stale edit target (its row was deleted, or the batch was applied).
        defs = list(st.session_state.get(KEY_BATCH_DEFS, []))
        edit_id = st.session_state.get(KEY_BATCH_EDIT_ID)
        if edit_id and not any(d.get("id") == edit_id for d in defs):
            st.session_state[KEY_BATCH_EDIT_ID] = None
            edit_id = None

        col_scale, col_name, col_items = st.columns([2, 2, 3])
        with col_scale:
            st.selectbox("Ölçek", scale_keys, key="batch_scale_select")
        with col_name:
            st.text_input(
                "Alt ölçek adı",
                placeholder="ör. CBMO_AltOlcek1",
                key="batch_subscale_name",
            )
        selected_scale = st.session_state.get("batch_scale_select", default_scale)
        with col_items:
            st.multiselect(
                "Maddeler",
                grouped.get(selected_scale, []),
                key="batch_subscale_items",
            )

        submit_label = "Tanımı güncelle" if edit_id else "Tanım ekle"
        add_col, cancel_col = st.columns([3, 1])
        with add_col:
            submit_clicked = st.button(submit_label, key="batch_add_def_btn")
        with cancel_col:
            cancel_clicked = (
                st.button("Vazgeç", key="batch_edit_cancel_btn") if edit_id else False
            )

        if cancel_clicked:
            st.session_state[KEY_BATCH_EDIT_ID] = None
            st.session_state[PENDING_CLEAR_BATCH_FORM] = True
            st.rerun()

        if submit_clicked:
            scale = st.session_state.get("batch_scale_select", default_scale)
            name_raw = (st.session_state.get("batch_subscale_name") or "").strip()
            items = list(st.session_state.get("batch_subscale_items") or [])
            if not name_raw:
                st.error("Alt ölçek adı girin.")
            elif not items:
                st.error("En az bir madde seçin.")
            else:
                name_clean = _sanitize_short_label(name_raw) or name_raw
                if name_clean in _existing_column_names():
                    st.error(f"`{name_clean}` sütunu zaten mevcut.")
                # Dup-name check ignores the row being edited (it may keep its name).
                elif any(
                    d.get("name") == name_clean and d.get("id") != edit_id for d in defs
                ):
                    st.error(f"`{name_clean}` toplu listede zaten var.")
                elif edit_id:
                    # Rewrite the staged row in place (update-by-id — the append path
                    # would add a duplicate). Nothing is built from a staged row until
                    # apply, so no downstream clear here.
                    st.session_state[KEY_BATCH_DEFS] = [
                        {"id": edit_id, "scale": scale, "name": name_clean, "cols": items}
                        if d.get("id") == edit_id
                        else d
                        for d in defs
                    ]
                    st.session_state[KEY_BATCH_EDIT_ID] = None
                    st.session_state[PENDING_CLEAR_BATCH_FORM] = True
                    st.rerun()
                else:
                    defs.append(
                        {
                            "id": _new_composite_id(),
                            "scale": scale,
                            "name": name_clean,
                            "cols": items,
                        }
                    )
                    st.session_state[KEY_BATCH_DEFS] = defs
                    st.session_state[PENDING_CLEAR_BATCH_FORM] = True
                    st.rerun()

        defs = list(st.session_state.get(KEY_BATCH_DEFS, []))
        if defs:
            for d in defs:
                items_str = ", ".join(d.get("cols", []))
                if len(items_str) > 40:
                    items_str = items_str[:37] + "..."
                c_scale, c_name, c_items, c_edit, c_del = st.columns([2, 2, 3, 1, 1])
                with c_scale:
                    st.write(d.get("scale", ""))
                with c_name:
                    st.write(d.get("name", ""))
                with c_items:
                    st.write(items_str)
                with c_edit:
                    if st.button("Düzenle", key=f"batch_edit_{d['id']}"):
                        st.session_state[PENDING_BATCH_EDIT_LOAD] = dict(d)
                        st.rerun()
                with c_del:
                    if st.button("Sil", key=f"batch_del_{d['id']}"):
                        if st.session_state.get(KEY_BATCH_EDIT_ID) == d["id"]:
                            st.session_state[KEY_BATCH_EDIT_ID] = None
                            st.session_state[PENDING_CLEAR_BATCH_FORM] = True
                        st.session_state[KEY_BATCH_DEFS] = [
                            x for x in defs if x.get("id") != d["id"]
                        ]
                        st.rerun()

        gen_mean, gen_sum = st.columns(2)
        with gen_mean:
            gen_mean_clicked = st.button(
                "Tümünü Ortalama olarak oluştur", key="batch_gen_mean_btn"
            )
        with gen_sum:
            gen_sum_clicked = st.button(
                "Tümünü Toplam olarak oluştur", key="batch_gen_sum_btn"
            )

        if gen_mean_clicked or gen_sum_clicked:
            method = "mean" if gen_mean_clicked else "sum"
            existing = _existing_column_names()
            composites = _normalize_composite_list(
                st.session_state.get(KEY_COMPOSITE_CONFIG, [])
            )
            taken = {c.get("name") for c in composites if c.get("name")}
            n = 0
            for d in defs:
                name = d.get("name", "")
                if not name or name in existing or name in taken:
                    continue
                composites.append(
                    {
                        "id": d.get("id") or _new_composite_id(),
                        "name": name,
                        "columns": list(d.get("cols", [])),
                        "method": method,
                    }
                )
                taken.add(name)
                existing.add(name)
                n += 1
            st.session_state[KEY_COMPOSITE_CONFIG] = composites
            st.session_state[KEY_BATCH_DEFS] = []
            st.success(f"{n} bileşik oluşturuldu.")
            st.rerun()


def _validate_reversed_column_ranges(
    working_df: pd.DataFrame,
    reverse_config: dict[str, dict],
    short_labels: dict[str, str],
) -> list[str]:
    messages: list[str] = []
    for raw_col, bounds in reverse_config.items():
        short = short_labels.get(raw_col)
        if not short or short not in working_df.columns:
            continue
        vmin, vmax = int(bounds["min"]), int(bounds["max"])
        numeric = pd.to_numeric(working_df[short], errors="coerce")
        out_of_range = numeric.dropna()[(numeric < vmin) | (numeric > vmax)]
        if not out_of_range.empty:
            offenders = ", ".join(f"{v:g}" for v in out_of_range.unique()[:8])
            extra = "…" if out_of_range.nunique() > 8 else ""
            messages.append(
                f"**{short}**: value(s) outside [{vmin}, {vmax}] — {offenders}{extra}"
            )
    return messages


def _cronbach_alpha_summary(item_columns: list[str], df: pd.DataFrame) -> tuple[str, int | None]:
    import pingouin as pg

    if len(item_columns) < 2:
        return "Uygulanamaz (tek madde)", None
    item_data = df[item_columns].dropna()
    if len(item_data) < 2:
        return "Uygulanamaz", len(item_data)
    alpha, _ = pg.cronbach_alpha(data=item_data)
    return f"{alpha:.3f}", len(item_data)


def _render_data_quality_card(df: pd.DataFrame) -> None:
    """4-up metric strip + warnings, shown after upload.

    Designed so a psychology student can glance once and know:
      - How many participants and items they uploaded
      - Whether there's a worrying amount of missing data
      - Whether there's an obvious 'Yok say' candidate (timestamp)
      - How many columns look numeric (Likert items)
    """
    n_rows = len(df)
    n_cols = len(df.columns)
    total_cells = n_rows * n_cols if n_rows and n_cols else 0
    missing_cells = int(df.isna().sum().sum())
    missing_pct = (missing_cells / total_cells * 100) if total_cells else 0.0
    numeric_cols = sum(1 for c in df.columns if pd.api.types.is_numeric_dtype(df[c]))
    timestamp_like = [
        c for c in df.columns
        if any(k in c.lower() for k in ("zaman", "tarih", "timestamp", "date", "time"))
    ]

    # Build cards as pure HTML so they render inside the dashboard surface
    # without dragging Streamlit widget chrome along.
    cards_html = (
        '<div class="ps-quality-grid">'
        + _quality_card("Katılımcı", f"{n_rows:,}", "satır (N)")
        + _quality_card("Sütun", f"{n_cols:,}", "ölçek + demografik")
        + _quality_card(
            "Eksik Veri",
            f"%{missing_pct:.1f}",
            f"{missing_cells:,} hücre",
            tone="warn" if missing_pct > 10 else ("ok" if missing_pct < 1 else None),
        )
        + _quality_card("Sayısal Sütun", f"{numeric_cols:,}", "Likert adayı")
        + "</div>"
    )
    st.markdown(cards_html, unsafe_allow_html=True)

    # Inline warnings — only fire on real issues so the success state stays clean.
    if missing_pct > 10:
        st.warning(
            f"⚠️ Eksik veri oranı **%{missing_pct:.1f}** — yüksek. Analizler "
            "liste bazlı silme uygulayacağından örneklem önemli ölçüde küçülebilir."
        )
    if timestamp_like:
        st.info(
            f"⏱ Bir tarih/zaman sütunu var: **{timestamp_like[0]}**. "
            "Adım 2'de rolünü **Yok say** olarak işaretlemenizi öneririz."
        )
    if n_rows < 30:
        st.warning(
            f"📉 Sadece **{n_rows} katılımcı** var. Çoğu istatistiksel test için "
            "minimum 30 önerilir; sonuçları temkinli yorumlayın."
        )


def _quality_card(label: str, value: str, sub: str, *, tone: str | None = None) -> str:
    """One card in the data-quality strip. Returns inline HTML."""
    tone_class = f" ps-quality-card--{tone}" if tone else ""
    return (
        f'<div class="ps-quality-card{tone_class}">'
        f'  <div class="ps-quality-label">{label}</div>'
        f'  <div class="ps-quality-value">{value}</div>'
        f'  <div class="ps-quality-sub">{sub}</div>'
        f'</div>'
    )


def _render_upload_dataset_preview(df: pd.DataFrame, *, from_session: bool = False) -> None:
    """Show data-quality glance + demo badge + head() preview."""
    demo_active = bool(st.session_state.get("_psychstats_demo_active"))

    if demo_active:
        st.markdown(
            '<div class="ps-demo-badge">DEMO VERİSİ — sentetik 180 katılımcı, '
            'analize hazır. Sonuçlar gerçek verinizi yansıtmaz.</div>',
            unsafe_allow_html=True,
        )
    elif from_session:
        st.caption("Kaydedilmiş PsychStats oturumundan yüklendi (analize hazır veri).")
    else:
        st.caption(
            "İpucu: Google Forms dışa aktarımlarında genelde Zaman Damgası sütunu vardır — "
            "rolü **Yok say** olarak ayarlayın."
        )

    # ---- Data Quality glance card (4-up metrics + smart warnings) ----
    _render_data_quality_card(df)

    # ---- Compact head() preview, restyled by the card-body CSS ----
    with st.expander("İlk 5 satırı önizle", expanded=False):
        st.dataframe(df.head(5), use_container_width=True)


def _render_demo_dataset_button() -> None:
    """Compact 'try with demo data' card shown when no file is loaded yet."""
    from .demo_data import DEMO_DESCRIPTION

    st.markdown(
        '<div style="margin:8px 0 4px;font-family:Inter;font-size:11px;'
        'font-weight:600;letter-spacing:.08em;text-transform:uppercase;'
        'color:#6e7681;">Veya hızlı bir demo</div>',
        unsafe_allow_html=True,
    )
    col_btn, col_desc = st.columns([1, 3])
    with col_btn:
        clicked = st.button(
            "🚀 Demo veriyle başla",
            key="load_demo_dataset",
            use_container_width=True,
            type="secondary",
            help="Sentetik bir veri setiyle tüm akışı denemenizi sağlar.",
        )
    with col_desc:
        st.caption(DEMO_DESCRIPTION)
    if clicked:
        _load_demo_dataset()
        st.session_state["_force_scroll_top"] = True
        st.rerun()


def _load_demo_dataset() -> None:
    """Load the synthetic demo dataset into session state (Step 1)."""
    from .demo_data import DEMO_DATASET_NAME, generate_demo_dataframe

    df = generate_demo_dataframe()

    # Treat demo like an already-parsed upload: raw_df is the source of truth.
    st.session_state[KEY_RAW_DF] = df.copy()
    st.session_state[KEY_UPLOAD_DONE] = True

    # Clear any real-upload plumbing so UI is consistent.
    st.session_state[KEY_UPLOAD_BYTES] = None
    st.session_state[KEY_UPLOAD_FILE_SIG] = (DEMO_DATASET_NAME, len(df.columns))
    st.session_state[KEY_PARSE_SIG] = ("psychstats_demo", len(df.columns))
    st.session_state.pop(KEY_XLSX_SHEETS, None)
    st.session_state.pop(KEY_SESSION_ZIP_SIG, None)

    # Reset downstream preprocessing steps (roles/mapping/reverse/composites/final).
    _reset_preprocessing_state()

    st.session_state["_psychstats_demo_active"] = True


def _handle_session_zip_upload() -> None:
    """
    Render the "load saved session" uploader and apply its contents.

    The saved zip restores source + final data plus preprocessing metadata so the
    user can continue from end-of-Step-4 immediately.
    """
    uploaded_zip = st.file_uploader(
        "Tam Oturumu Yükle (.zip)",
        type=["zip"],
        key="psychstats_session_uploader",
        help="Daha önce indirdiğiniz `psychstats_session.zip` dosyasını yükleyin.",
        label_visibility="visible",
    )

    if uploaded_zip is None:
        st.caption("İpucu: Bu seçenek, kaldığınız yerden devam etmek için tüm oturumu geri yükler.")
        return

    zip_bytes = uploaded_zip.getvalue()
    zip_sig = (uploaded_zip.name, len(zip_bytes))
    if st.session_state.get(KEY_SESSION_ZIP_SIG) == zip_sig:
        return

    try:
        warnings = _apply_full_session_from_zip(zip_bytes)
    except Exception as exc:
        st.error(f"Oturum zip'i okunamadı: {exc}")
        return

    st.session_state[KEY_SESSION_ZIP_SIG] = zip_sig
    st.session_state["_psychstats_demo_active"] = False

    st.success("✅ Oturum yüklendi. Kaynak veri ve ayarlar geri yüklendi.")
    if warnings:
        with st.expander("Yükleme uyarıları", expanded=False):
            for w in warnings:
                st.warning(w)


def _render_upload_step():
    raw_df = st.session_state.get(KEY_RAW_DF)
    session_source_loaded = (
        raw_df is not None
        and st.session_state.get(KEY_SESSION_ZIP_SIG) is not None
        and _raw_df_looks_like_saved_source(raw_df)
    )

    if session_source_loaded:
        st.info("Kaynak veri kaydedilmiş oturumdan yüklendi.")
        if st.button("🔄 Yeniden başla (yeni dosya yükle)", key="start_fresh_upload"):
            _start_fresh_from_saved_session()
            st.rerun()
    else:
        uploaded = st.file_uploader(
            "Veri setinizi yükleyin (.csv veya .xlsx)",
            type=["csv", "xlsx"],
            key="psychstats_file_uploader",
        )

        if uploaded is not None:
            file_bytes = uploaded.getvalue()
            file_sig = (uploaded.name, len(file_bytes))
            st.session_state[KEY_UPLOAD_BYTES] = file_bytes
            if st.session_state.get(KEY_UPLOAD_FILE_SIG) != file_sig:
                st.session_state[KEY_UPLOAD_FILE_SIG] = file_sig
                st.session_state[KEY_PARSE_SIG] = None
                st.session_state.pop(KEY_SESSION_ZIP_SIG, None)
                _reset_preprocessing_state()
                if uploaded.name.lower().endswith(".xlsx"):
                    try:
                        st.session_state[KEY_XLSX_SHEETS] = _xlsx_sheet_names(file_bytes)
                    except Exception as exc:
                        st.error(f"Excel dosyası okunamadı: {exc}")
                        return
                else:
                    st.session_state[KEY_XLSX_SHEETS] = None

        file_bytes = st.session_state.get(KEY_UPLOAD_BYTES)
        if file_bytes is None:
            if not (
                st.session_state.get(KEY_UPLOAD_DONE)
                and st.session_state.get(KEY_RAW_DF) is not None
            ):
                st.info("Ön işlemeye başlamak için .csv veya .xlsx dosyası yükleyin.")
        else:
            file_name = (st.session_state.get(KEY_UPLOAD_FILE_SIG) or ("", 0))[0].lower()
            selected_sheet = None

            if file_name.endswith(".xlsx"):
                sheets = st.session_state.get(KEY_XLSX_SHEETS) or []
                if len(sheets) > 1:
                    selected_sheet = st.selectbox(
                        "Sayfa seçin",
                        sheets,
                        key="xlsx_sheet_select",
                    )
                elif len(sheets) == 1:
                    selected_sheet = sheets[0]
                else:
                    st.error("Excel dosyasında sayfa bulunamadı.")
                    return
                parse_sig = (st.session_state.get(KEY_UPLOAD_FILE_SIG), selected_sheet)
            else:
                parse_sig = (st.session_state.get(KEY_UPLOAD_FILE_SIG), "csv")

            if st.session_state.get(KEY_PARSE_SIG) != parse_sig:
                try:
                    if file_name.endswith(".xlsx"):
                        df = _read_xlsx_bytes(file_bytes, selected_sheet)
                    else:
                        df = _read_csv_bytes(file_bytes)
                    # Rule 8: always overwrite raw data on parse — never "if not set"
                    st.session_state[KEY_RAW_DF] = df.copy()
                    st.session_state[KEY_UPLOAD_DONE] = True
                    st.session_state[KEY_PARSE_SIG] = parse_sig
                    _reset_preprocessing_state()
                except Exception as exc:
                    st.error(f"Dosya okunamadı: {exc}")
                    return

    st.divider()
    _render_demo_dataset_button()

    st.divider()
    st.markdown("**Veya önceden kaydedilmiş bir oturumu yükleyin:**")
    _handle_session_zip_upload()

    if st.session_state.get(KEY_UPLOAD_DONE) and st.session_state.get(KEY_RAW_DF) is not None:
        from_session = (
            st.session_state.get(KEY_SESSION_ZIP_SIG) is not None
            and st.session_state.get(KEY_UPLOAD_BYTES) is None
        )
        _render_upload_dataset_preview(
            st.session_state[KEY_RAW_DF],
            from_session=from_session,
        )


def _render_config_save_load(df: pd.DataFrame):
    st.markdown("---")
    col_save, col_load = st.columns(2)

    with col_save:
        config_json = json.dumps(_export_config_dict(), indent=2, ensure_ascii=False)
        st.download_button(
            "💾 Yapılandırmayı Kaydet",
            data=config_json.encode("utf-8"),
            file_name="psychstats_config.json",
            mime="application/json",
            help="Sütun rolleri, ölçek eşlemesi, kısa etiketler, ters puanlama kuralları ve bileşikleri indirin.",
        )

    with col_load:
        uploaded_config = st.file_uploader(
            "📂 Yapılandırma Yükle",
            type=["json"],
            key="psychstats_config_uploader",
            label_visibility="visible",
        )

    if uploaded_config is not None:
        config_bytes = uploaded_config.getvalue()
        config_sig = (uploaded_config.name, len(config_bytes))
        if st.session_state.get("_config_file_sig") != config_sig:
            try:
                parsed = json.loads(config_bytes.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                st.error(f"Geçersiz yapılandırma dosyası: {exc}")
                st.session_state.pop(KEY_PENDING_CONFIG, None)
                return
            cleaned, warnings = _reconcile_config(parsed, list(df.columns))
            st.session_state[KEY_PENDING_CONFIG] = {"cleaned": cleaned, "warnings": warnings}
            st.session_state["_config_file_sig"] = config_sig
            st.session_state["confirm_load_config"] = False

    pending = st.session_state.get(KEY_PENDING_CONFIG)
    if pending:
        cleaned = pending.get("cleaned", {})
        for msg in pending.get("warnings", []):
            st.warning(msg)
        if not pending.get("warnings"):
            st.info("Yapılandırma mevcut veri seti sütunlarıyla eşleşiyor.")

        st.warning(
            "Bu, mevcut sütun atamanızın üzerine yazacaktır. Onaylamak için işaretleyin."
        )
        st.checkbox(
            "Bu, mevcut sütun atamanızın üzerine yazacaktır. Onaylamak için işaretleyin.",
            key="confirm_load_config",
        )
        if st.button("Yüklenen yapılandırmayı uygula", key="apply_loaded_config"):
            if not st.session_state.get("confirm_load_config"):
                st.error("Uygulamadan önce onay kutusunu işaretleyin.")
                return
            st.session_state[PENDING_APPLY_CONFIG] = cleaned
            st.session_state.pop(KEY_PENDING_CONFIG, None)
            st.success(
                "Yapılandırma Adım 2'ye yüklendi. Sütun rollerini, ardından ölçek atamasını onaylayın."
            )
            st.rerun()


def _confirm_column_roles(col_list: list) -> bool:
    """Sub-phase A: persist roles from mapper widgets into KEY_COL_ROLES."""
    roles: dict[str, str] = {}
    for i, col in enumerate(col_list):
        role_label = st.session_state.get(_role_key(i), ROLE_IGNORE)
        roles[col] = ROLE_TO_KEY.get(role_label, "ignore")

    st.session_state[KEY_COL_ROLES] = roles
    st.session_state[KEY_ROLES_CONFIRMED] = True
    st.session_state[KEY_MAPPING_DONE] = False
    st.session_state[KEY_SCALE_MAP] = {}
    st.session_state[KEY_SHORT_LABELS] = {}
    st.session_state[KEY_REVERSE_DONE] = False
    _reset_recode_state()
    st.session_state[KEY_WORKING_DF] = None
    st.session_state[KEY_FINAL_DF] = None
    return True


def _confirm_scale_assignment(col_list: list) -> bool:
    """Sub-phase B: validate scale map and complete Step 2."""
    roles = st.session_state.get(KEY_COL_ROLES, {})
    scale_map = st.session_state.get(KEY_SCALE_MAP, {})
    short_labels = st.session_state.get(KEY_SHORT_LABELS, {})

    missing_scale: list[str] = []
    missing_short: list[str] = []
    seen_short: dict[str, str] = {}

    for col in col_list:
        if roles.get(col) != "scale_item":
            continue
        if col not in scale_map or not (scale_map.get(col) or "").strip():
            missing_scale.append(col)
            continue
        short = short_labels.get(col, "")
        if not short:
            missing_short.append(col)
            continue
        if short in seen_short and seen_short[short] != col:
            st.error(
                f"`{short}` kısa etiketi `{seen_short[short]}` ve `{col}` sütunları için yineleniyor."
            )
            return False
        seen_short[short] = col

    if missing_scale:
        st.error(
            "Onaylamadan önce Tüm Blokları Uygula (veya ölçek atayın). "
            "Eksik ölçek: " + ", ".join(missing_scale[:8])
            + ("…" if len(missing_scale) > 8 else "")
        )
        return False
    if missing_short:
        st.error(
            "Eksik kısa etiket: " + ", ".join(missing_short[:8])
            + ("…" if len(missing_short) > 8 else "")
        )
        return False

    st.session_state[KEY_MAPPING_DONE] = True
    st.session_state[KEY_REVERSE_DONE] = False
    _reset_recode_state()
    st.session_state[KEY_WORKING_DF] = None
    st.session_state[KEY_FINAL_DF] = None
    return True


def _render_confirmed_roles_summary(col_list: list) -> None:
    roles = st.session_state.get(KEY_COL_ROLES, {})
    n_scale = sum(1 for c in col_list if roles.get(c) == "scale_item")
    n_demo = sum(1 for c in col_list if roles.get(c) == "demographic")
    n_ignore = sum(1 for c in col_list if roles.get(c) == "ignore")
    st.success("Sütun rolleri onaylandı.")
    st.write(f"- **Ölçek maddeleri:** {n_scale}")
    st.write(f"- **Demografik sütunlar:** {n_demo}")
    st.write(f"- **Yok sayılan sütunlar:** {n_ignore}")


def _render_scale_assignment_summary(col_list: list) -> None:
    roles = st.session_state.get(KEY_COL_ROLES, {})
    scale_map = st.session_state.get(KEY_SCALE_MAP, {})
    short_labels = st.session_state.get(KEY_SHORT_LABELS, {})
    scale_names = sorted({scale_map[c] for c in col_list if roles.get(c) == "scale_item" and c in scale_map})
    st.success("Ölçek ataması onaylandı. Adım 2 tamamlandı.")
    for scale_name in scale_names:
        labels = sorted(
            (
                short_labels[c]
                for c in col_list
                if roles.get(c) == "scale_item"
                and scale_map.get(c) == scale_name
                and c in short_labels
            ),
            key=_item_short_label_sort_key,
        )
        st.write(f"- **{scale_name}:** {len(labels)} madde → `{', '.join(labels)}`")


def _render_subphase_b_scale_assignment(col_list: list, df: pd.DataFrame) -> None:
    st.markdown("### Alt Aşama B — Ölçek Ataması")
    _render_define_scales_panel()
    _render_scale_blocks_panel(col_list, df)

    if st.button("Ölçek Atamasını Onayla", type="primary", key="confirm_scale_assignment"):
        if _confirm_scale_assignment(col_list):
            st.rerun()

    if st.session_state.get(KEY_MAPPING_DONE):
        _render_scale_assignment_summary(col_list)
        st.caption(
            "✅ Tamamlandı — devam etmek için aşağıdaki **Adım 3: Ters Puanlama**'yı genişletin."
        )


def _consume_pending_bulk_role(col_list: list, column_count: int) -> None:
    """Apply a queued bulk role change BEFORE the row table / bulk widgets render.

    Pending-flag pattern: the Apply button only sets PENDING_BULK_ROLE + reruns; the
    actual widget-key writes happen here, before instantiation. Updates the per-row
    role keys (role_select_i — these drive the table), mirrors into KEY_COL_ROLES, and
    resets the data_editor so its stale per-cell edits can't override the change.
    Role assignment is upstream of recode/reverse/composite, so nothing downstream is
    touched (the existing 'confirm' flow propagates changes when she's ready)."""
    pending = st.session_state.pop(PENDING_BULK_ROLE, None)
    if not pending:
        return
    role_label = pending.get("role")
    indices = pending.get("indices", [])
    if role_label in ROLE_OPTIONS:
        role_key = ROLE_TO_KEY.get(role_label, "ignore")
        roles = dict(st.session_state.get(KEY_COL_ROLES, {}))
        for i in indices:
            if 0 <= i < column_count:
                st.session_state[_role_key(i)] = role_label
                roles[col_list[i]] = role_key
        st.session_state[KEY_COL_ROLES] = roles
    # Drop the editor's edited_rows overlay so the table reflects the new role keys.
    st.session_state.pop("role_assignment_editor", None)
    # Clear the multiselect for the next batch (pre-instantiation — pending pattern).
    st.session_state[KEY_BULK_ROLE_COLS] = []


def _render_bulk_role_control(col_list: list, column_count: int) -> None:
    """Compact 'set several columns to one role at once' control, above the table.

    Native widgets only. Selecting by row-number-prefixed display name keeps long
    survey questions distinguishable. Apply only queues PENDING_BULK_ROLE + reruns."""
    with st.expander("Toplu rol atama", expanded=False):
        st.caption(
            "Birden çok sütunu tek seferde aynı role ayarlayın — yanlış "
            "sınıflandırmaları satır satır düzeltmek yerine hızlıca düzeltin."
        )
        # Keep the stored selection valid if the dataset changed (avoids a stale-index
        # error from the keyed multiselect). Pre-instantiation write — allowed.
        valid = [i for i in st.session_state.get(KEY_BULK_ROLE_COLS, []) if 0 <= i < column_count]
        if valid != list(st.session_state.get(KEY_BULK_ROLE_COLS, [])):
            st.session_state[KEY_BULK_ROLE_COLS] = valid

        c_cols, c_role, c_apply = st.columns([3, 1, 1])
        with c_cols:
            st.multiselect(
                "Sütunlar",
                options=list(range(column_count)),
                format_func=lambda i: f"{i + 1} — {col_list[i]}",
                key=KEY_BULK_ROLE_COLS,
                label_visibility="collapsed",
                placeholder="Sütun(lar) seçin…",
            )
        with c_role:
            st.selectbox(
                "Rol",
                options=ROLE_OPTIONS,
                key=KEY_BULK_ROLE_VALUE,
                label_visibility="collapsed",
            )
        with c_apply:
            apply_clicked = st.button(
                "Uygula", key="bulk_role_apply", use_container_width=True,
            )

        if apply_clicked:
            selected = list(st.session_state.get(KEY_BULK_ROLE_COLS, []))
            if not selected:
                st.warning("Önce en az bir sütun seçin.")
            else:
                st.session_state[PENDING_BULK_ROLE] = {
                    "indices": selected,
                    "role": st.session_state.get(KEY_BULK_ROLE_VALUE, ROLE_OPTIONS[0]),
                }
                st.rerun()


def _render_role_step():
    """Step 2 — Sütun Rolleri (Sub-phase A).

    Renders an editable, numbered, full-height table where each row is one
    column from the dataset. The user can change a column's role inline
    via a per-row dropdown. Top + bottom "Onayla" buttons let the user
    confirm without scrolling 47 rows.
    """
    if not st.session_state.get(KEY_UPLOAD_DONE):
        st.info("Önce Adım 1'i (dosya yükleme) tamamlayın.")
        return

    df = st.session_state[KEY_RAW_DF]
    col_list = list(df.columns)
    column_count = len(col_list)

    pending_config = st.session_state.get(PENDING_APPLY_CONFIG)
    if pending_config:
        _apply_config_to_session(pending_config)
        _apply_config_to_widgets(pending_config, col_list)
        st.session_state[PENDING_APPLY_CONFIG] = None

    _init_mapper_widget_state(column_count, col_list, df)

    # Apply any queued bulk role change before the row table / bulk widgets render.
    _consume_pending_bulk_role(col_list, column_count)

    # ------------------------------------------------------------------
    # 1) Build the editable table.
    # ------------------------------------------------------------------
    editor_key = "role_assignment_editor"

    def _current_role(i: int, col: str) -> str:
        # Prefer the live widget-key value (also persisted across reruns).
        return (
            st.session_state.get(_role_key(i))
            or _classify_column_with_reason(col, df[col])[0]
        )

    table_rows = []
    for i, col in enumerate(col_list):
        series = df[col]
        _default_role, default_reason = _classify_column_with_reason(col, series)
        table_rows.append({
            "#": i + 1,
            "Sütun": col,
            "Örnek": _sample_values(series),
            "Rol": _current_role(i, col),
            "Gerekçe": default_reason,
        })
    table_df = pd.DataFrame(table_rows)

    # Summary line (top) — computed from current widget state.
    role_counts = {opt: 0 for opt in ROLE_OPTIONS}
    for i, col in enumerate(col_list):
        role_counts[_current_role(i, col)] = role_counts.get(_current_role(i, col), 0) + 1
    summary = (
        f"**{column_count} sütun** · "
        f"{role_counts.get(ROLE_SCALE_ITEM, 0)} ölçek maddesi · "
        f"{role_counts.get(ROLE_DEMOGRAPHIC, 0)} demografik · "
        f"{role_counts.get(ROLE_IGNORE, 0)} yok say"
    )

    # ------------------------------------------------------------------
    # 2) Top action bar — summary + primary Onayla button.
    # ------------------------------------------------------------------
    bar_left, bar_right = st.columns([3, 1])
    with bar_left:
        st.markdown(summary)
        st.caption(
            "İpucu: Google Forms dışa aktarımlarında genelde Zaman Damgası "
            "sütunu vardır — rolü **Yok say** olarak ayarlayın. "
            "Bir hücreye tıklayarak rolü değiştirebilirsiniz."
        )
    with bar_right:
        confirm_top = st.button(
            "Sütun Rollerini Onayla",
            type="primary",
            key="confirm_column_roles_top",
            use_container_width=True,
        )

    # Bulk role assignment — compact safety net directly above the table.
    _render_bulk_role_control(col_list, column_count)

    # ------------------------------------------------------------------
    # 3) Tall editable table.
    # ------------------------------------------------------------------
    # This one table breaks out of the global 1180px content column to ~full
    # viewport width, so the long question / justification columns are readable
    # without per-column resizing. Scoped to THIS table via a unique marker; the
    # rest of the app keeps its narrow reading column. No transform (would offset
    # the grid's inline cell editor) — classic position/left/margin full-bleed.
    st.markdown(
        """
        <style>
        /* Make the main content area a query container so 100cqw = main width,
           EXCLUDING the sidebar (no viewport vw — that slid the table under the
           expanded sidebar). The table then fills the main area, centered. */
        section[data-testid="stMain"]{ container-type: inline-size; }
        [data-testid="stElementContainer"]:has(.ps-roletable-fullbleed){display:none;}
        [data-testid="stElementContainer"]:has(.ps-roletable-fullbleed)
          + [data-testid="stElementContainer"]{
            position:relative;
            width:calc(100cqw - 24px) !important;
            max-width:calc(100cqw - 24px) !important;
            /* 50% resolves against the (centered) card width and cancels out, so the
               left edge lands on the main area's left edge regardless of card width. */
            margin-left:calc(-50cqw + 50% + 12px) !important;
        }
        </style>
        <div class="ps-roletable-fullbleed"></div>
        """,
        unsafe_allow_html=True,
    )
    edited = st.data_editor(
        table_df,
        key=editor_key,
        hide_index=True,
        use_container_width=True,
        # Taller fixed height (~18–19 rows visible at once) with internal scroll,
        # so the ~72-column review isn't a constant scroll.
        height=700,
        column_config={
            "#": st.column_config.NumberColumn(
                "#", width="small", help="Sütun sırası", disabled=True,
            ),
            # Long survey-question text → widest column. (Streamlit 1.57's TextColumn
            # has no text-wrap option, so proportionate width carries the readability.)
            "Sütun": st.column_config.TextColumn(
                "Sütun adı", width="large", disabled=True,
            ),
            "Örnek": st.column_config.TextColumn(
                "Örnek değer", width="medium", disabled=True,
            ),
            "Rol": st.column_config.SelectboxColumn(
                "Rol",
                options=ROLE_OPTIONS,
                required=True,
                width="small",
                help=(
                    "**Ölçek Maddesi:** Likert puanı (1-5 / 1-7) — analize girer.\n\n"
                    "**Demografik:** kategorik (cinsiyet, bölüm) veya sayısal (yaş) "
                    "bilgi — grup karşılaştırmalarında bağımsız değişken olarak kullanılır.\n\n"
                    "**Yok say:** zaman damgası, ID, e-posta gibi analize girmeyen sütunlar."
                ),
            ),
            "Gerekçe": st.column_config.TextColumn(
                "Otomatik gerekçe", width="large", disabled=True,
            ),
        },
    )

    # Sync edited Rol values back into widget-key state for _confirm_column_roles().
    for i, col in enumerate(col_list):
        new_role = str(edited.iloc[i]["Rol"]) if i < len(edited) else _current_role(i, col)
        if new_role not in ROLE_OPTIONS:
            new_role = ROLE_OPTIONS[0]
        st.session_state[_role_key(i)] = new_role

    # ------------------------------------------------------------------
    # 4) Bottom Onayla button (mirror of top for users who scroll).
    # ------------------------------------------------------------------
    confirm_bottom = st.button(
        "Sütun Rollerini Onayla",
        type="primary",
        key="confirm_column_roles_bottom",
    )

    if confirm_top or confirm_bottom:
        _confirm_column_roles(col_list)
        # Signal the layout to scroll to top on the next render (app.py reads this).
        st.session_state["_force_scroll_top"] = True
        st.rerun()

    if st.session_state.get(KEY_ROLES_CONFIRMED, False):
        st.divider()
        _render_confirmed_roles_summary(col_list)
        st.success("Roller onaylandı — bir sonraki adım: Ölçek Tanımlama ve Atama.")


def _render_scale_step():
    """Step 3 — Ölçek Tanımlama ve Atama (Sub-phase B).

    Define scales (custom or via preset), assign column ranges to each
    scale (manual or auto-detect), then confirm to flip KEY_MAPPING_DONE.
    """
    if not st.session_state.get(KEY_ROLES_CONFIRMED, False):
        st.info("Önce Adım 2'yi (sütun rolleri) tamamlayın.")
        return

    df = st.session_state[KEY_RAW_DF]
    col_list = list(df.columns)

    _render_confirmed_roles_summary(col_list)
    st.divider()
    _render_subphase_b_scale_assignment(col_list, df)
    _render_config_save_load(df)


# Backward-compat shim so any external callers (and the dispatcher below)
# still work if they reference the old name.
def _render_mapping_step():
    _render_role_step()
    if st.session_state.get(KEY_ROLES_CONFIRMED, False):
        st.divider()
        _render_scale_step()


def _recode_preview_frame(raw_df: pd.DataFrame, working_df: pd.DataFrame) -> dict:
    """Before/after for the first ≤2 recoded scale columns (first 3 rows)."""
    scale_map = st.session_state.get(KEY_SCALE_MAP, {})
    short_labels = st.session_state.get(KEY_SHORT_LABELS, {})
    recode_map = st.session_state.get(KEY_RECODE_MAP, {})
    frame: dict[str, list] = {}
    shown = 0
    for raw_col in _scale_item_raw_columns():
        if shown >= 2:
            break
        if not recode_map.get(scale_map.get(raw_col)):
            continue
        short = short_labels.get(raw_col)
        if not short or raw_col not in raw_df.columns or short not in working_df.columns:
            continue
        frame[f"{short} (ham)"] = [str(x) for x in raw_df[raw_col].head(3).tolist()]
        frame[f"{short} (kod)"] = working_df[short].head(3).tolist()
        shown += 1
    return frame


def _apply_recoding(raw_df: pd.DataFrame, scale_values: dict[str, list[str]]) -> None:
    """Validate the per-value number inputs, build KEY_RECODE_MAP + KEY_WORKING_DF."""
    ss = st.session_state
    recode_map: dict[str, dict] = {}
    blanks: list[str] = []
    for scale, values in scale_values.items():
        mapping: dict[str, int] = {}
        for v in values:
            num = ss.get(_recode_input_key(scale, v))
            if num is None or (isinstance(num, str) and not str(num).strip()):
                blanks.append(f"{scale} · `{v}`")
                continue
            mapping[v] = int(num)
        recode_map[scale] = mapping

    if blanks:
        st.error(
            "Her metin yanıtına bir sayı atanmalı (boş bırakılamaz). Eksik: "
            + ", ".join(blanks[:8]) + ("…" if len(blanks) > 8 else "")
        )
        return

    # Soft validations — warn, don't block. Persisted so they survive the rerun.
    warnings_list: list[str] = []
    for scale, mapping in recode_map.items():
        nums = sorted(set(mapping.values()))
        if not nums:
            continue
        if nums != list(range(1, max(nums) + 1)):
            warnings_list.append(
                f"{scale}: eşlenen değerler {', '.join(map(str, nums))} — "
                f"1–{max(nums)} aralığında ardışık bekleniyordu; doğrulayın."
            )
        _, preset_max = _scale_bounds_for_name(scale)
        if max(nums) != preset_max:
            warnings_list.append(
                f"{scale}: algılanan maksimum {max(nums)}, beklenen ölçek maksimumu "
                f"{preset_max} ile eşleşmiyor; doğrulayın."
            )

    ss[KEY_RECODE_MAP] = recode_map
    working_df = _build_recoded_analysis_dataframe(raw_df)
    ss[KEY_WORKING_DF] = working_df
    ss[KEY_RECODE_PREVIEW] = {
        "frame": _recode_preview_frame(raw_df, working_df),
        "warnings": warnings_list,
    }
    ss[KEY_RECODE_DONE] = True
    st.rerun()


def _render_recode_step() -> None:
    """Step 2.5 — Value Recoding (text Likert → numeric). Gates Step 3 (reverse).

    Reads KEY_RAW_DF (never mutated); writes KEY_WORKING_DF with the same short-label
    structure as _build_analysis_dataframe so Steps 3–4 are unchanged."""
    ss = st.session_state
    raw_df = ss.get(KEY_RAW_DF)
    if raw_df is None:
        return

    with st.expander(
        "Değer Kodlama — Metin yanıtlarını sayıya çevir",
        expanded=not ss.get(KEY_RECODE_DONE),
    ):
        st.caption("Ters puanlamadan önce yapılır.")
        # Completed → compact summary + before/after + reset.
        if ss.get(KEY_RECODE_DONE):
            recode_map = ss.get(KEY_RECODE_MAP, {})
            n_scales = len([s for s, m in recode_map.items() if m])
            if n_scales:
                st.success(f"✅ Değer kodlama uygulandı ({n_scales} ölçek).")
            else:
                st.info("✅ Veri zaten sayısaldı — kodlamaya gerek olmadı.")
            preview = ss.get(KEY_RECODE_PREVIEW) or {}
            for msg in preview.get("warnings", []):
                st.warning(msg)
            frame = preview.get("frame")
            if frame:
                st.caption("Önce / sonra (ilk 3 satır):")
                st.dataframe(
                    pd.DataFrame(frame), use_container_width=True, hide_index=True
                )
            if st.button("← Değer kodlamayı yeniden yap", key="recode_redo"):
                _redo_recoding()
                st.rerun()
            return

        # Skip path — data is already numeric (e.g. the demo dataset).
        if _all_scale_columns_numeric(raw_df):
            st.info("Veri zaten sayısal görünüyor — metin→sayı kodlamasına gerek yok.")
            if st.button("Kodlamayı atla", type="primary", key="recode_skip"):
                ss[KEY_RECODE_MAP] = {}
                ss[KEY_WORKING_DF] = _build_analysis_dataframe(raw_df)
                ss.pop(KEY_RECODE_PREVIEW, None)
                ss[KEY_RECODE_DONE] = True
                st.rerun()
            return

        # Auto-detect per scale.
        scale_values: dict[str, list[str]] = {}
        scale_pattern: dict[str, str] = {}
        for scale, raw_cols in _recode_cols_by_scale().items():
            values = _unique_text_values_for_scale(raw_df, raw_cols)
            scale_values[scale] = values
            scale_pattern[scale] = _detect_recode_pattern(values)

        # Prime number inputs once (guarded). Prefer the user's saved map (redo), else
        # the auto-detected/dictionary proposal; unknown values are left blank.
        if not ss.get(KEY_RECODE_PRIMED):
            stored_map = ss.get(KEY_RECODE_MAP, {})
            for scale, values in scale_values.items():
                proposed = _propose_recode_for_scale(values, scale_pattern[scale])
                saved = stored_map.get(scale, {})
                for v, num in proposed.items():
                    chosen = saved.get(v, num)
                    if chosen is not None:
                        ss[_recode_input_key(scale, v)] = int(chosen)
            ss[KEY_RECODE_PRIMED] = True

        st.caption(
            "Metin Likert yanıtları sayıya dönüştürülür. Otomatik önerileri kontrol "
            "edip gerekirse düzeltin; bilinmeyenler boş gelir, doldurun. Ham veri değişmez."
        )

        for scale, values in scale_values.items():
            st.markdown(f"**{scale}** · {len(values)} farklı yanıt")
            if scale_pattern[scale] == "leading_number":
                st.caption('Otomatik algılandı: baştaki sayı etiketleri (ör. "3. …" → 3).')
            else:
                st.caption("Kelime etiketleri — her yanıt için sayıyı doğrulayın/girin.")
            for v in values:
                k = _recode_input_key(scale, v)
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(f"`{v}`")
                with c2:
                    kwargs = {
                        "key": k,
                        "step": 1,
                        "format": "%d",
                        "label_visibility": "collapsed",
                    }
                    if k not in ss:  # unknown → blank input (avoids default/session clash)
                        kwargs["value"] = None
                    st.number_input(f"{scale}:{v}", **kwargs)
            st.divider()

        col_apply, col_back = st.columns([1, 1])
        with col_apply:
            apply_clicked = st.button(
                "Kodlamayı Uygula", type="primary", key="recode_apply"
            )
        with col_back:
            if st.button("← Değer kodlamayı yeniden yap", key="recode_reset_pre"):
                _redo_recoding()
                st.rerun()

        if apply_clicked:
            _apply_recoding(raw_df, scale_values)


def _render_reverse_step():
    if not st.session_state.get(KEY_MAPPING_DONE):
        st.info("Önce Adım 2'yi (sütun rol ataması) tamamlayın.")
        return

    # Step 2.5 — Value Recoding sits between scale assignment and reverse scoring,
    # and gates it: reverse cannot run until recoding is applied (or skipped).
    _render_recode_step()
    if not st.session_state.get(KEY_RECODE_DONE):
        return

    if st.button("← Sütun atamasını yeniden yap", key="back_to_column_mapping"):
        _redo_column_mapping()
        st.rerun()

    raw_cols = _scale_item_raw_columns()
    short_labels = st.session_state.get(KEY_SHORT_LABELS, {})

    if not raw_cols:
        st.warning("Hiçbir ölçek maddesi atanmadı. Ters puanlama atlanıyor.")
        if st.button("Ters puanlama olmadan devam et", key="skip_reverse"):
            st.session_state[KEY_WORKING_DF] = _build_recoded_analysis_dataframe(st.session_state[KEY_RAW_DF])
            st.session_state[KEY_REVERSE_CONFIG] = {}
            st.session_state[KEY_REVERSE_DONE] = True
            st.rerun()
        return

    ss = st.session_state
    scale_map = st.session_state.get(KEY_SCALE_MAP, {})
    if not ss.get(KEY_REVERSE_PRIMED):
        _prime_reverse_checks_from_presets(raw_cols)
        _prime_reverse_checks_from_config(raw_cols)
        ss[KEY_REVERSE_PRIMED] = True

    pending_preset_scale = ss.pop("pending_apply_preset_scale", None)
    if pending_preset_scale:
        preset_map = st.session_state.get(KEY_SCALE_PRESET_MAP, {})
        meta = preset_map.get(pending_preset_scale, {})
        reverse_nums = set(meta.get("reverse_items") or [])
        default_min, default_max = _scale_bounds_for_name(pending_preset_scale)
        for raw_col in raw_cols:
            if scale_map.get(raw_col) != pending_preset_scale:
                continue
            short = short_labels.get(raw_col, "")
            match = re.search(r"(\d+)$", short)
            if match and int(match.group(1)) in reverse_nums:
                ss[f"reverse_chk_{raw_col}"] = True
                ss[f"reverse_min_{raw_col}"] = int(
                    ss.get(f"reverse_min_{raw_col}", default_min)
                )
                ss[f"reverse_max_{raw_col}"] = int(
                    ss.get(f"reverse_max_{raw_col}", default_max)
                )

    if not st.session_state.get(KEY_REVERSE_DONE):
        cols_by_scale: dict[str, list[str]] = defaultdict(list)
        for raw_col in raw_cols:
            scale_name = scale_map.get(raw_col, "—")
            cols_by_scale[scale_name].append(raw_col)

        for scale_name, scale_raw_cols in cols_by_scale.items():
            preset_map = st.session_state.get(KEY_SCALE_PRESET_MAP, {})
            meta = preset_map.get(scale_name, {})
            reverse_nums = set(meta.get("reverse_items") or [])

            any_checked = any(
                ss.get(f"reverse_chk_{rc}", False) for rc in scale_raw_cols
            )
            auto_expand = bool(reverse_nums) or any_checked

            with st.expander(
                f"{scale_name} ({len(scale_raw_cols)} madde)",
                expanded=auto_expand,
            ):
                if reverse_nums:
                    items_str = ", ".join(str(n) for n in sorted(reverse_nums))
                    st.caption(
                        f"Hazır ayar ters puanlama maddelerini öneriyor: **{items_str}** — "
                        "uygulamadan önce doğrulayın."
                    )
                    if st.button(
                        f"Hazır ayarı uygula: {scale_name}",
                        key=f"apply_preset_{_block_widget_suffix(scale_name)}",
                    ):
                        ss["pending_apply_preset_scale"] = scale_name
                        st.rerun()

                default_min, default_max = _scale_bounds_for_name(scale_name)
                for raw_col in scale_raw_cols:
                    short = short_labels.get(raw_col, raw_col)
                    st.checkbox(
                        f"Ters puan: **{short}**",
                        key=f"reverse_chk_{raw_col}",
                        help=(
                            "Bu madde negatif yönde puanlanmışsa işaretleyin. "
                            "Örnek: 'Hayatımdan memnunum' (düz) ve 'Hayatım berbat' (ters) "
                            "aynı ölçekte yer alırsa, ikincinin puanı ölçek aralığına göre "
                            "çevrilir (örn. 1–5 ölçeğinde 5 → 1). Böylece tüm maddeler aynı "
                            "yönü ölçer."
                        ),
                    )
                    if ss.get(f"reverse_chk_{raw_col}", False):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.number_input(
                                "Ölçek minimumu",
                                min_value=0,
                                value=int(ss.get(f"reverse_min_{raw_col}", default_min)),
                                key=f"reverse_min_{raw_col}",
                            )
                        with c2:
                            st.number_input(
                                "Ölçek maksimumu",
                                min_value=1,
                                value=int(ss.get(f"reverse_max_{raw_col}", default_max)),
                                key=f"reverse_max_{raw_col}",
                            )

        items_to_reverse = []
        for raw_col in raw_cols:
            if ss.get(f"reverse_chk_{raw_col}", False):
                short = short_labels.get(raw_col, raw_col)
                vmin = int(ss.get(f"reverse_min_{raw_col}", 1))
                vmax = int(ss.get(f"reverse_max_{raw_col}", 5))
                items_to_reverse.append(
                    {
                        "Madde": short,
                        "Ölçek min": vmin,
                        "Ölçek maks": vmax,
                        "Formül": f"{vmax} + {vmin} − x",
                    }
                )

        if items_to_reverse:
            st.markdown("**Ters puanlama için seçilen maddeler:**")
            st.dataframe(
                pd.DataFrame(items_to_reverse),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption(
                "Ters puanlama için madde seçilmedi — ters puanlama olmadan devam etmek için "
                "Uygula'ya tıklayın."
            )

        if st.button("Ters Puanlamayı Uygula", type="primary", key="apply_reverse"):
            raw_df = st.session_state[KEY_RAW_DF]
            if _raw_df_looks_like_saved_source(raw_df):
                working_df = raw_df.copy()
            else:
                # Recoded base (text→numeric already applied via KEY_RECODE_MAP); rebuilt
                # deterministically so redo-reverse never double-reverses. Empty map →
                # identity, so already-numeric data is unchanged.
                working_df = _build_recoded_analysis_dataframe(raw_df)
            reverse_config: dict[str, dict] = {}
            reversed_short: list[str] = []
            before_after: dict[str, dict] = {}

            for raw_col in raw_cols:
                short = short_labels.get(raw_col)
                if not short:
                    continue
                if not st.session_state.get(f"reverse_chk_{raw_col}", False):
                    continue
                vmin = int(st.session_state.get(f"reverse_min_{raw_col}", 1))
                vmax = int(st.session_state.get(f"reverse_max_{raw_col}", 5))
                if vmin > vmax:
                    st.error(f"{short}: minimum maksimumdan büyük olamaz.")
                    return
                before_after[short] = {
                    "before": working_df[short].head(3).tolist(),
                }
                reverse_config[raw_col] = {"min": vmin, "max": vmax}
                reversed_short.append(short)

            working_df = _apply_reverse_config_to_dataframe(
                working_df, reverse_config, short_labels
            )
            for short in reversed_short:
                if short in before_after:
                    before_after[short]["after"] = working_df[short].head(3).tolist()

            range_errors = _validate_reversed_column_ranges(
                working_df, reverse_config, short_labels
            )
            if range_errors:
                for msg in range_errors:
                    st.error(msg)
                st.error(
                    "Ters puanlama yapılandırılan ölçek aralığının dışında değerler üretti. "
                    "Min/maks değerlerini ayarlayıp tekrar deneyin."
                )
                return

            ss = st.session_state
            ss[KEY_WORKING_DF] = working_df
            ss[KEY_REVERSE_CONFIG] = reverse_config
            ss[KEY_REVERSE_DONE] = True
            _lock_reverse_checkbox_choices(raw_cols)

            if reversed_short:
                st.success(
                    f"Ters puanlama {len(reversed_short)} sütun(a) uygulandı."
                )
                preview = pd.DataFrame(before_after).T
                st.write("Önce / sonra (ilk 3 satır, kısa etiketler):")
                st.dataframe(preview, use_container_width=True)
            else:
                st.info(
                    "Hiçbir madde seçilmedi — çalışma kopyası ters puanlama olmadan kısa etiketler kullanır."
                )
            st.rerun()

    if st.session_state.get(KEY_REVERSE_DONE):
        reverse_config = st.session_state.get(KEY_REVERSE_CONFIG, {})
        short_labels = st.session_state.get(KEY_SHORT_LABELS, {})
        n_rev = len(reverse_config)

        if n_rev:
            st.success(f"✅ Ters puanlama uygulandı — {n_rev} madde terslendi.")
            rows = []
            for raw_col, bounds in reverse_config.items():
                short = short_labels.get(raw_col, raw_col)
                rows.append(
                    {
                        "Madde": short,
                        "Ölçek min": bounds.get("min", "—"),
                        "Ölçek maks": bounds.get("max", "—"),
                        "Formül": f"{bounds.get('max', '?')} + {bounds.get('min', '?')} − x",
                    }
                )
            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Ters puanlama adımı tamamlandı (terslenen madde yok).")
        st.caption(
            "✅ Tamamlandı — devam etmek için aşağıdaki **Adım 4: Bileşik Puan Oluşturucu**'yu genişletin."
        )


def _composite_options_by_scale() -> dict[str, list[str]]:
    scale_map = st.session_state.get(KEY_SCALE_MAP, {})
    short_labels = st.session_state.get(KEY_SHORT_LABELS, {})
    grouped: dict[str, list[str]] = {}
    for raw_col, scale in scale_map.items():
        short = short_labels.get(raw_col, raw_col)
        grouped.setdefault(scale, []).append(short)
    for scale in grouped:
        grouped[scale].sort(key=_item_short_label_sort_key)
    return dict(sorted(grouped.items()))


def _render_composite_summary_and_download(final_df: pd.DataFrame, composites: list[dict]):
    if not composites:
        return

    raw_df = st.session_state.get(KEY_RAW_DF)
    total_rows = len(raw_df) if raw_df is not None else 0
    st.markdown("**Bileşik özetleri**")
    rows = []
    alpha_n_values: list[int] = []
    for comp in composites:
        comp_name = comp.get("name")
        comp_cols = comp.get("cols", comp.get("columns", []))
        if not comp_name:
            continue
        if comp_name not in final_df.columns:
            continue
        series = final_df[comp_name].dropna()
        alpha_str, n_alpha = _cronbach_alpha_summary(comp_cols, final_df)
        if n_alpha is not None:
            alpha_n_values.append(n_alpha)
        rows.append(
            {
                "Bileşik": comp_name,
                "N": len(series),
                "Ort": round(series.mean(), 3) if len(series) else None,
                "SS": round(series.std(ddof=1), 3) if len(series) > 1 else None,
                "Min": series.min() if len(series) else None,
                "Max": series.max() if len(series) else None,
                "α": alpha_str,
                "N (α)": n_alpha if n_alpha is not None else "—",
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if total_rows > 0 and alpha_n_values:
        for n_alpha in alpha_n_values:
            if n_alpha < total_rows and (total_rows - n_alpha) / total_rows > 0.10:
                st.warning(
                    f"Cronbach's α, yüklenen {total_rows:,} satırdan {n_alpha:,} tam vakayı kullandı "
                    f"(eksik madde verisi nedeniyle {(total_rows - n_alpha) / total_rows:.0%} dışlandı)."
                )
                break

    for comp in composites:
        comp_name = comp.get("name", "composite")
        comp_cols = comp.get("cols", comp.get("columns", []))
        if len(comp_cols) < 2:
            continue
        with st.expander(f"Madde-toplam istatistikleri: {comp_name}", expanded=False):
            stats_df = item_total_statistics_table(comp_name, comp_cols, final_df)
            st.dataframe(stats_df, use_container_width=True, hide_index=True)

    csv_bytes = final_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇ Ön işlenmiş veriyi indir (CSV)",
        data=csv_bytes,
        file_name="psychstats_preprocessed.csv",
        mime="text/csv",
        key="download_preprocessed_csv",
    )


def _render_composite_step():
    if not st.session_state.get(KEY_REVERSE_DONE):
        st.info("Önce Adım 3'ü (ters puanlama) tamamlayın.")
        return

    _consume_composite_form_pending()
    _consume_pending_start_editing()

    if st.session_state.pop(PENDING_MULTISELECT_RESET, False):
        grouped_reset = _composite_options_by_scale()
        editing_comp = _get_editing_composite()
        if editing_comp is not None:
            edit_cols = set(_composite_cols(editing_comp))
            for scale_name, cols in grouped_reset.items():
                ms_key = f"edit_composite_ms_{_block_widget_suffix(scale_name)}"
                st.session_state[ms_key] = [c for c in cols if c in edit_cols]
        else:
            checked = st.session_state.get(KEY_COMPOSITE_ITEMS_CHECKED, {})
            for scale_name, cols in grouped_reset.items():
                ms_key = f"composite_ms_{_block_widget_suffix(scale_name)}"
                st.session_state[ms_key] = [c for c in cols if checked.get(c, False)]

    if st.button("← Ters puanlamayı yeniden yap", key="back_to_reverse_scoring"):
        _redo_reverse_scoring()
        st.rerun()

    working_df = st.session_state.get(KEY_WORKING_DF)
    if working_df is None:
        working_df = _build_analysis_dataframe(st.session_state[KEY_RAW_DF])
        st.session_state[KEY_WORKING_DF] = working_df

    grouped = _composite_options_by_scale()

    defined_scales = list(st.session_state.get(KEY_DEFINED_SCALES, []))
    scale_map = st.session_state.get(KEY_SCALE_MAP, {})
    if not defined_scales and scale_map:
        defined_scales = sorted({v for v in scale_map.values() if v})

    suggest_err = st.session_state.pop("_composite_suggested_error", None)
    if suggest_err:
        st.error(suggest_err)

    if st.button("Bileşikleri Otomatik Öner", key="auto_suggest_composites"):
        suggestions = []
        for scale_name, cols in grouped.items():
            safe = _sanitize_short_label(scale_name) or "Scale"
            suggestions.append(
                {
                    "id": _new_composite_id(),
                    "name": f"{safe}_Total",
                    "columns": cols.copy(),
                    "method": "sum",
                }
            )
            suggestions.append(
                {
                    "id": _new_composite_id(),
                    "name": f"{safe}_Mean",
                    "columns": cols.copy(),
                    "method": "mean",
                }
            )
        st.session_state[KEY_COMPOSITE_SUGGESTIONS] = suggestions
        st.session_state["_force_scroll_top"] = True
        st.info(
            f"Aşağıda {len(suggestions)} bileşik önerildi — inceleyin ve her biri için "
            "**Öneriyi ekle**'ye tıklayın."
        )

    suggestions = st.session_state.get(KEY_COMPOSITE_SUGGESTIONS, [])
    if suggestions:
        st.markdown("**Önerilen bileşikler**")
        has_mean = any(
            _ensure_composite_id(s).get("method") == "mean" for s in suggestions
        )
        has_sum = any(
            _ensure_composite_id(s).get("method") == "sum" for s in suggestions
        )
        if has_mean or has_sum:
            col_mean, col_sum = st.columns(2)
            if has_mean:
                with col_mean:
                    if st.button(
                        "Tümünü ekle (Ortalama)",
                        key="add_all_suggested_mean_btn",
                    ):
                        _append_suggestions_by_method("mean")
                        st.rerun()
            if has_sum:
                with col_sum:
                    if st.button(
                        "Tümünü ekle (Toplam)",
                        key="add_all_suggested_sum_btn",
                    ):
                        _append_suggestions_by_method("sum")
                        st.rerun()
        for comp in suggestions:
            comp = _ensure_composite_id(comp)
            comp_name = comp.get("name", "composite")
            comp_cols = comp.get("cols", comp.get("columns", []))
            comp_id = comp["id"]
            st.write(
                f"- `{comp_name}` — {_method_display(comp.get('method', 'sum'))} "
                f"({len(comp_cols)} madde: {', '.join(comp_cols[:3])}"
                f"{'…' if len(comp_cols) > 3 else ''})"
            )
            if st.button(f"Öneriyi ekle: {comp_name}", key=f"add_suggested_{comp_id}"):
                suggested = _ensure_composite_id(dict(comp))
                suggested_name = suggested.get("name", "")
                if suggested_name in _existing_column_names():
                    st.session_state["_composite_suggested_error"] = (
                        f"`{suggested_name}` sütunu zaten mevcut."
                    )
                else:
                    composites = _normalize_composite_list(
                        st.session_state.get(KEY_COMPOSITE_CONFIG, [])
                    )
                    composites.append(suggested)
                    st.session_state[KEY_COMPOSITE_CONFIG] = composites
                    st.session_state[KEY_COMPOSITE_SUGGESTIONS] = [
                        s
                        for s in st.session_state.get(KEY_COMPOSITE_SUGGESTIONS, [])
                        if s.get("id") != suggested["id"]
                    ]
                    st.session_state.pop("_composite_suggested_error", None)
                st.rerun()

    if grouped:
        st.radio(
            "Yöntem",
            [METHOD_SUM_LABEL, METHOD_MEAN_LABEL],
            horizontal=True,
            key=KEY_COMPOSITE_METHOD,
            help=(
                "**Toplam:** maddelerin toplam puanı (her madde aynı ölçekte ise tercih edilir).  \n"
                "**Ortalama:** maddelerin ortalama puanı — farklı sayıda maddeye sahip ölçekleri "
                "karşılaştırmak veya orijinal Likert aralığını korumak için idealdir.  \n"
                "Tezlerde yayınlanmış ölçeğin yazarının kullandığı yöntemi seçin."
            ),
        )
        _render_select_all_scale_buttons(grouped)

    st.text_input(
        "Bileşik değişken adı",
        placeholder="Mukemmeliyetcilik_Toplam",
        key=KEY_COMPOSITE_NAME_INPUT,
        help=(
            "Oluşan sütunun analizlerde görünecek adı. Öneri: "
            "`ÖlçekAdı_Toplam` veya `ÖlçekAdı_Ortalama` (ASCII + alt çizgi)."
        ),
    )
    editing_id = st.session_state.get(KEY_EDITING_COMPOSITE_ID)
    if grouped:
        if editing_id:
            st.caption("Bileşik maddelerini düzenleyin (ölçek başına bir çoklu seçim).")
            _render_composite_item_multiselect(grouped, editing=True)
        else:
            st.caption("Dahil edilecek maddeleri seçin (ölçeğe göre gruplandırılmış).")
            _render_composite_item_multiselect(grouped, editing=False)
    else:
        st.info("Bileşik oluşturmak için kullanılabilir ölçek maddesi yok.")
    submit_label = "Bileşiği Güncelle" if editing_id else "Bileşik Ekle"
    add_composite_clicked = st.button(submit_label, key="add_composite_btn")
    selected_cols = sorted(_selected_composite_columns(), key=_item_short_label_sort_key)
    add_composite_succeeded = False

    if add_composite_clicked:
        st.session_state[KEY_COMPOSITE_SUBMIT_ATTEMPTED] = True
        comp_name_raw = (st.session_state.get(KEY_COMPOSITE_NAME_INPUT) or "").strip()
        comp_name_clean = _sanitize_short_label(comp_name_raw) if comp_name_raw else ""
        method_label = st.session_state.get(KEY_COMPOSITE_METHOD, METHOD_SUM_LABEL)
        if not comp_name_clean:
            st.error("Bileşik değişken adı girin.")
        elif not _composite_name_available(comp_name_clean, editing_id):
            st.error(f"`{comp_name_clean}` sütunu veri setinde zaten mevcut.")
        elif not selected_cols:
            pass
        else:
            short_labels = st.session_state.get(KEY_SHORT_LABELS, {})
            short_to_scale = {
                short_labels[r]: scale_map[r] for r in scale_map if r in short_labels
            }
            scales_used = {short_to_scale.get(c) for c in selected_cols if c in short_to_scale}
            scales_used.discard(None)
            if len(scales_used) > 1:
                st.warning(
                    "Seçilen maddeler birden fazla ölçeği kapsıyor "
                    f"({', '.join(sorted(scales_used))}). Ölçekler arası bileşiklere izin verilir "
                    "ancak dikkatli yorumlayın."
                )
            method = "sum" if method_label == METHOD_SUM_LABEL else "mean"
            if editing_id:
                _update_composite_by_id(editing_id, comp_name_clean, selected_cols, method)
                st.session_state.pop(KEY_EDITING_COMPOSITE_ID, None)
            else:
                composites = _normalize_composite_list(
                    st.session_state.get(KEY_COMPOSITE_CONFIG, [])
                )
                composites.append(
                    {
                        "id": _new_composite_id(),
                        "name": comp_name_clean,
                        "columns": selected_cols,
                        "method": method,
                    }
                )
                st.session_state[KEY_COMPOSITE_CONFIG] = composites
            st.session_state[PENDING_CLEAR_COMPOSITE_FORM] = True
            add_composite_succeeded = True
            st.rerun()

    if (
        not add_composite_succeeded
        and st.session_state.get(KEY_COMPOSITE_SUBMIT_ATTEMPTED)
        and not selected_cols
    ):
        st.error("En az bir madde seçin.")

    composites = _normalize_composite_list(st.session_state.get(KEY_COMPOSITE_CONFIG, []))
    st.session_state[KEY_COMPOSITE_CONFIG] = composites
    if composites:
        st.markdown("**Tanımlanan bileşikler**")
        # Mark reverse-scored items with [R] using Step 3's recorded reverse list
        # (KEY_REVERSE_CONFIG, via _reversed_short_label_set). Display only.
        reversed_set = _reversed_short_label_set()
        for comp in composites:
            comp_id = comp["id"]
            comp_name = comp.get("name", "composite")
            comp_cols = comp.get("cols", comp.get("columns", []))
            comp_method = comp.get("method", "sum")
            cols_display = ", ".join(
                f"{c}[R]" if c in reversed_set else c for c in comp_cols
            )
            c1, c2, c3 = st.columns([4, 1, 1])
            with c1:
                st.write(
                    f"**{comp_name}** — {_method_display(comp_method)} "
                    f"({len(comp_cols)} madde): {cols_display}"
                )
            with c2:
                if st.button("Düzenle", key=f"edit_composite_{comp_id}"):
                    st.session_state[PENDING_START_EDITING] = dict(comp)
                    st.rerun()
            with c3:
                if st.button("Sil", key=f"delete_composite_{comp_id}"):
                    if st.session_state.get(KEY_EDITING_COMPOSITE_ID) == comp_id:
                        st.session_state.pop(KEY_EDITING_COMPOSITE_ID, None)
                    _delete_composite_by_id(comp_id)
                    st.rerun()

    if grouped:
        _render_batch_subscale_panel(grouped)

    if st.button("Tüm Bileşikleri Oluştur", type="primary", key="build_composites"):
        working_base = st.session_state.get(KEY_WORKING_DF)
        if working_base is None:
            st.error("Önce Adım 3'ü (ters puanlama) tamamlayın.")
            return
        final_df = working_base.copy()
        composites = st.session_state.get(KEY_COMPOSITE_CONFIG, [])

        for comp in composites:
            name = comp.get("name")
            cols = comp.get("cols", comp.get("columns", []))
            method = comp.get("method", "sum")
            if not name or not cols:
                continue
            subset = final_df[cols]
            if method == "sum":
                final_df[name] = subset.sum(axis=1, skipna=True)
            else:
                final_df[name] = subset.mean(axis=1, skipna=True)

        st.session_state[KEY_FINAL_DF] = final_df
        st.success("✅ Ön işleme tamamlandı. Bileşikler oluşturuldu ve analize hazır.")
        st.caption("✅ Tamamlandı — devam etmek için kenar çubuğundan **Betimsel İstatistikler**'e gidin.")
        st.rerun()

    final_df = st.session_state.get(KEY_FINAL_DF)
    if final_df is not None:
        composites = st.session_state.get(KEY_COMPOSITE_CONFIG, [])
        _render_composite_summary_and_download(final_df, composites)
        if not composites:
            csv_bytes = final_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "⬇ Ön işlenmiş veriyi indir (CSV)",
                data=csv_bytes,
                file_name="psychstats_preprocessed.csv",
                mime="text/csv",
                key="download_preprocessed_no_composites",
            )

        _render_save_full_session_button(final_df)


def render(active_step: int = 1):
    """
    Render the data-preparation phase for a given sub-step (1-5).

    Replaces the old vertical-expander stack. The horizontal stepper in
    app.py owns navigation; this renders ONE sub-step at a time, inside
    the card body provided by open_step_shell.

    Sub-steps:
      1 - Dosya Yukleme              (_render_upload_step)
      2 - Sutun Rolleri              (_render_role_step,      gated by upload)
      3 - Olcek Tanimlama ve Atama   (_render_scale_step,     gated by roles)
      4 - Ters Puanlama               (_render_reverse_step,   gated by mapping)
      5 - Bilesik Puan Olusturucu    (_render_composite_step, gated by reverse)
    """
    ss = st.session_state

    if active_step == 1:
        _render_upload_step()
        return

    if active_step == 2:
        if not ss.get(KEY_UPLOAD_DONE, False):
            st.info("Önce Adım 1'i (dosya yükleme) tamamlayın.")
            return
        _render_role_step()
        return

    if active_step == 3:
        if not ss.get(KEY_ROLES_CONFIRMED, False):
            st.info("Önce Adım 2'yi (sütun rolleri) tamamlayın.")
            return
        _render_scale_step()
        return

    if active_step == 4:
        if not ss.get(KEY_MAPPING_DONE, False):
            st.info("Önce Adım 3'ü (ölçek atama) tamamlayın.")
            return
        _render_reverse_step()
        return

    if active_step == 5:
        if not ss.get(KEY_REVERSE_DONE, False):
            st.info("Önce Adım 4'ü (ters puanlama) tamamlayın.")
            return
        _render_composite_step()
        return

    st.error(f"Bilinmeyen adım: {active_step}")
