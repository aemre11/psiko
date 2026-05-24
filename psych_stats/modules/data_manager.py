import json
import logging
import re
import unicodedata
import uuid
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st

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
KEY_REVERSE_DONE = "reverse_done"

CONFIG_VERSION = 1
CONFIG_STATE_KEYS = (
    KEY_COL_ROLES,
    KEY_SCALE_MAP,
    KEY_SHORT_LABELS,
    KEY_REVERSE_CONFIG,
    KEY_COMPOSITE_CONFIG,
    KEY_MAPPING_DONE,
    KEY_REVERSE_DONE,
)

ROLE_OPTIONS = ["Scale Item", "Demographic", "Ignore"]
ROLE_TO_KEY = {
    "Scale Item": "scale_item",
    "Demographic": "demographic",
    "Ignore": "ignore",
}
KEY_TO_ROLE = {v: k for k, v in ROLE_TO_KEY.items()}

KNOWN_SCALE_BOUNDS = {
    "perfectionism": (1, 5),
    "çbmö": (1, 5),
    "cbmo": (1, 5),
    "sharenting": (1, 5),
    "prfq": (1, 7),
}

PENDING_RESYNC_LABELS = "pending_resync_labels"
PENDING_CONFIRM_MAPPING = "pending_confirm_column_roles"
PENDING_SHORT_LABEL_MANUAL = "pending_short_label_manual"


def _role_key(col_index: int) -> str:
    return f"role_select_{col_index}"


def _scale_name_key(col_index: int) -> str:
    return f"scale_name_{col_index}"


def _short_label_key(col_index: int) -> str:
    return f"short_label_{col_index}"


def _short_label_manual_key(col_index: int) -> str:
    return f"_short_label_manual_{col_index}"


def _short_label_auto_key(col_index: int) -> str:
    return f"_short_label_auto_{col_index}"


def _role_reason_key(col_index: int) -> str:
    return f"_role_default_reason_{col_index}"


def _new_composite_id() -> str:
    return uuid.uuid4().hex[:12]


def _composite_item_id(comp: dict) -> str:
    existing = comp.get("id")
    if existing:
        return str(existing)
    name = _sanitize_short_label(comp.get("name", "composite")) or "composite"
    col_sig = "_".join(comp.get("columns", []))
    return f"{name}_{_sanitize_short_label(col_sig)}"[:48]


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
        KEY_REVERSE_DONE: False,
        PENDING_RESYNC_LABELS: False,
        PENDING_CONFIRM_MAPPING: False,
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
            return f"Column name matches timestamp pattern: {pattern.pattern!r}"
    sample = series.dropna().astype(str).head(5)
    if not sample.empty:
        date_ratio = sample.str.contains(_VALUE_DATE_PATTERN, regex=True).mean()
        if date_ratio >= 0.6:
            return f"Sample values look like dates ({date_ratio:.0%} of first rows)"
    return None


def _email_ignore_reason(col_name: str, series: pd.Series) -> str | None:
    lowered = col_name.lower()
    for token in ("email", "e-mail", "eposta", "e-posta"):
        if token in lowered:
            return f"Column name contains {token!r}"
    sample = series.dropna().astype(str).head(10)
    if not sample.empty:
        at_ratio = sample.str.contains("@", regex=False).mean()
        if at_ratio >= 0.5:
            return f"Sample values contain @ ({at_ratio:.0%} of first rows)"
    return None


def _likert_check_details(series: pd.Series) -> tuple[bool, str]:
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    if valid.empty:
        return False, "No numeric values after coercion"
    n_unique = int(valid.nunique())
    vmin, vmax = float(valid.min()), float(valid.max())
    if n_unique > 7:
        return False, f"Too many unique values ({n_unique} > 7)"
    if vmin < 1 or vmax > 7:
        return False, f"Values outside 1–7 range (min={vmin:g}, max={vmax:g})"
    return True, f"Numeric Likert-like values (unique={n_unique}, min={vmin:g}, max={vmax:g})"


def _is_likert_scale_column(series: pd.Series) -> bool:
    ok, _ = _likert_check_details(series)
    return ok


def _classify_column_with_reason(col_name: str, series: pd.Series) -> tuple[str, str]:
    ts_reason = _timestamp_ignore_reason(col_name, series)
    if ts_reason:
        logger.debug("Column %r → Ignore: %s", col_name, ts_reason)
        return "Ignore", ts_reason
    email_reason = _email_ignore_reason(col_name, series)
    if email_reason:
        logger.debug("Column %r → Ignore: %s", col_name, email_reason)
        return "Ignore", email_reason
    is_likert, likert_detail = _likert_check_details(series)
    if is_likert:
        logger.debug("Column %r → Scale Item: %s", col_name, likert_detail)
        return "Scale Item", likert_detail
    if pd.to_numeric(series, errors="coerce").notna().any():
        reason = f"Numeric but not Likert ({likert_detail})"
    else:
        reason = f"Non-numeric / text field ({series.nunique(dropna=True)} unique values)"
    logger.debug("Column %r → Demographic: %s", col_name, reason)
    return "Demographic", reason


def _default_role(col_name: str, series: pd.Series) -> str:
    role, _ = _classify_column_with_reason(col_name, series)
    return role


def _auto_short_label(scale_name: str, col_index: int, column_count: int) -> str:
    """{FirstWordOfScale}_{n} where n counts items with the same scale name in column order."""
    parts = scale_name.strip().split()
    first_word = parts[0] if parts else "Item"
    base = _sanitize_short_label(first_word) or "Item"
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
        if st.session_state.get(_role_key(i)) != "Scale Item":
            continue
        if st.session_state.get(_short_label_manual_key(i), False):
            continue
        scale_name = (st.session_state.get(_scale_name_key(i)) or "").strip()
        if not scale_name:
            continue
        suggested = _sanitize_short_label(_auto_short_label(scale_name, i, column_count))
        st.session_state[_short_label_key(i)] = suggested
        st.session_state[_short_label_auto_key(i)] = suggested


def _on_scale_name_change() -> None:
    """Pending flag only — never write scale_name_* or short_label_* keys here."""
    st.session_state[PENDING_RESYNC_LABELS] = True


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


def _existing_column_names() -> set[str]:
    names: set[str] = set()
    for key in (KEY_WORKING_DF, KEY_FINAL_DF):
        df = st.session_state.get(key)
        if df is not None:
            names.update(df.columns)
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
    }


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
        for col in comp.get("columns", []):
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
    }
    return cleaned, warnings


def _apply_config_to_widgets(config: dict, raw_columns: list[str]) -> None:
    roles = config.get(KEY_COL_ROLES, {})
    scale_map = config.get(KEY_SCALE_MAP, {})
    short_labels = config.get(KEY_SHORT_LABELS, {})

    for i, col in enumerate(raw_columns):
        role_key = roles.get(col, "ignore")
        st.session_state[_role_key(i)] = KEY_TO_ROLE.get(role_key, "Ignore")
        st.session_state[_scale_name_key(i)] = scale_map.get(col, "")
        st.session_state[_short_label_key(i)] = _sanitize_short_label(short_labels.get(col, ""))
        if short_labels.get(col):
            st.session_state[_short_label_manual_key(i)] = True


def _apply_config_to_session(cleaned: dict) -> None:
    st.session_state[KEY_COL_ROLES] = cleaned.get(KEY_COL_ROLES, {})
    st.session_state[KEY_SCALE_MAP] = cleaned.get(KEY_SCALE_MAP, {})
    st.session_state[KEY_SHORT_LABELS] = cleaned.get(KEY_SHORT_LABELS, {})
    st.session_state[KEY_REVERSE_CONFIG] = cleaned.get(KEY_REVERSE_CONFIG, {})
    st.session_state[KEY_COMPOSITE_CONFIG] = cleaned.get(KEY_COMPOSITE_CONFIG, [])
    st.session_state[KEY_MAPPING_DONE] = False
    st.session_state[KEY_REVERSE_DONE] = False
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
    st.session_state[PENDING_CONFIRM_MAPPING] = False


def _reset_preprocessing_state():
    st.session_state[KEY_MAPPING_DONE] = False
    st.session_state[KEY_REVERSE_DONE] = False
    st.session_state[KEY_WORKING_DF] = None
    st.session_state[KEY_FINAL_DF] = None
    st.session_state[KEY_COL_ROLES] = {}
    st.session_state[KEY_SCALE_MAP] = {}
    st.session_state[KEY_SHORT_LABELS] = {}
    st.session_state[KEY_REVERSE_CONFIG] = {}
    st.session_state[KEY_COMPOSITE_CONFIG] = []
    _clear_column_mapper_widgets()


def _redo_column_mapping():
    st.session_state[KEY_REVERSE_CONFIG] = {}
    st.session_state[KEY_COMPOSITE_CONFIG] = []
    st.session_state[KEY_FINAL_DF] = None
    st.session_state[KEY_MAPPING_DONE] = False


def _redo_reverse_scoring():
    st.session_state[KEY_COMPOSITE_CONFIG] = []
    st.session_state[KEY_FINAL_DF] = None


def _reversed_short_label_set() -> set[str]:
    reverse_config = st.session_state.get(KEY_REVERSE_CONFIG, {})
    short_labels = st.session_state.get(KEY_SHORT_LABELS, {})
    return {short_labels[raw] for raw in reverse_config if raw in short_labels}


def _composite_multiselect_label(scale_name: str, col: str) -> str:
    suffix = " [R]" if col in _reversed_short_label_set() else ""
    return f"[{scale_name}] {col}{suffix}"


def _parse_composite_multiselect_label(label: str) -> str:
    text = label.split("] ", 1)[1]
    return text.removesuffix(" [R]").strip()


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
        return "N/A (single item)", None
    item_data = df[item_columns].dropna()
    if len(item_data) < 2:
        return "N/A", len(item_data)
    alpha, _ = pg.cronbach_alpha(data=item_data)
    return f"{alpha:.3f}", len(item_data)


def _item_total_statistics_table(
    composite_name: str, item_columns: list[str], df: pd.DataFrame
) -> pd.DataFrame:
    import pingouin as pg

    item_data = df[item_columns].dropna()
    rows = []
    for item in item_columns:
        others = [c for c in item_columns if c != item]
        others_sum = item_data[others].sum(axis=1)
        corrected_r = item_data[item].corr(others_sum)
        if len(others) >= 2:
            alpha_deleted, _ = pg.cronbach_alpha(data=item_data[others])
            alpha_str = f"{alpha_deleted:.3f}"
        else:
            alpha_str = "N/A"
        rows.append(
            {
                "Item": item,
                "Corrected Item-Total Correlation": f"{corrected_r:.3f}"
                if pd.notna(corrected_r)
                else "N/A",
                "α if Item Deleted": alpha_str,
            }
        )
    return pd.DataFrame(rows)


def _render_upload_step():
    st.subheader("Step 1: File Upload")
    uploaded = st.file_uploader(
        "Upload your dataset (.csv or .xlsx)",
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
            _reset_preprocessing_state()
            if uploaded.name.lower().endswith(".xlsx"):
                try:
                    st.session_state[KEY_XLSX_SHEETS] = _xlsx_sheet_names(file_bytes)
                except Exception as exc:
                    st.error(f"Could not read Excel workbook: {exc}")
                    return
            else:
                st.session_state[KEY_XLSX_SHEETS] = None

    file_bytes = st.session_state.get(KEY_UPLOAD_BYTES)
    if file_bytes is None:
        st.info("Upload a .csv or .xlsx file to begin preprocessing.")
        return

    file_name = (st.session_state.get(KEY_UPLOAD_FILE_SIG) or ("", 0))[0].lower()
    selected_sheet = None

    if file_name.endswith(".xlsx"):
        sheets = st.session_state.get(KEY_XLSX_SHEETS) or []
        if len(sheets) > 1:
            selected_sheet = st.selectbox(
                "Select sheet to use",
                sheets,
                key="xlsx_sheet_select",
            )
        elif len(sheets) == 1:
            selected_sheet = sheets[0]
        else:
            st.error("No sheets found in the Excel file.")
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
            st.error(f"Could not read file: {exc}")
            return

    if not st.session_state.get(KEY_UPLOAD_DONE) or st.session_state[KEY_RAW_DF] is None:
        st.info("Upload a .csv or .xlsx file to begin preprocessing.")
        return

    df = st.session_state[KEY_RAW_DF]
    st.caption(
        "Tip: Google Forms exports often include a Timestamp column — set it to **Ignore**."
    )
    st.write(f"**Rows:** {len(df):,}  |  **Columns:** {len(df.columns):,}")
    st.dataframe(df.head(5), use_container_width=True)

    nan_rows = int(df.isna().any(axis=1).sum())
    if nan_rows > 0:
        st.warning(
            f"⚠️ {nan_rows:,} rows contain missing values. These will be excluded "
            "automatically during analysis (listwise deletion)."
        )
    else:
        st.success("No rows with missing values detected in the raw file.")


def _render_config_save_load(df: pd.DataFrame):
    st.markdown("---")
    col_save, col_load = st.columns(2)

    with col_save:
        config_json = json.dumps(_export_config_dict(), indent=2, ensure_ascii=False)
        st.download_button(
            "💾 Save Config",
            data=config_json.encode("utf-8"),
            file_name="psychstats_config.json",
            mime="application/json",
            help="Download column roles, scale map, short labels, reverse rules, and composites.",
        )

    with col_load:
        uploaded_config = st.file_uploader(
            "📂 Load Config",
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
                st.error(f"Invalid config file: {exc}")
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
            st.info("Config matches the current dataset columns.")

        st.warning("This will overwrite your current column mapping. Check to confirm.")
        st.checkbox(
            "This will overwrite your current column mapping. Check to confirm.",
            key="confirm_load_config",
        )
        if st.button("Apply loaded config", key="apply_loaded_config"):
            if not st.session_state.get("confirm_load_config"):
                st.error("Check the confirmation box before applying.")
                return
            _apply_config_to_session(cleaned)
            _apply_config_to_widgets(cleaned, list(df.columns))
            st.session_state.pop(KEY_PENDING_CONFIG, None)
            st.success("Configuration loaded into Step 2. Confirm column roles when ready.")
            st.rerun()


def _confirm_column_roles(col_list: list, column_count: int) -> bool:
    """Read mapper widgets from session state and persist roles (after pre-widget resync)."""
    roles: dict[str, str] = {}
    scale_map: dict[str, str] = {}
    short_labels: dict[str, str] = {}
    missing_scale_names: list[str] = []
    missing_short_labels: list[str] = []
    seen_short: dict[str, str] = {}

    for i, col in enumerate(col_list):
        role_label = st.session_state.get(_role_key(i), "Ignore")
        role_key = ROLE_TO_KEY.get(role_label, "ignore")
        roles[col] = role_key

        if role_key == "scale_item":
            scale_name = (st.session_state.get(_scale_name_key(i)) or "").strip()
            raw_short = (st.session_state.get(_short_label_key(i)) or "").strip()
            if not scale_name:
                missing_scale_names.append(col)
                continue
            if not raw_short:
                missing_short_labels.append(col)
                continue
            short = _sanitize_short_label(raw_short)
            if not short:
                missing_short_labels.append(col)
                continue
            if short in seen_short and seen_short.get(short) != col:
                st.error(
                    f"Duplicate short label `{short}` for columns "
                    f"`{seen_short[short]}` and `{col}`."
                )
                return False
            seen_short[short] = col
            scale_map[col] = scale_name
            short_labels[col] = short

    if missing_scale_names:
        st.error(
            "Each Scale Item needs a scale name. Missing for: "
            + ", ".join(missing_scale_names)
        )
        return False
    if missing_short_labels:
        st.error(
            "Each Scale Item needs a short label. Missing for: "
            + ", ".join(missing_short_labels)
        )
        return False

    st.session_state[KEY_COL_ROLES] = roles
    st.session_state[KEY_SCALE_MAP] = scale_map
    st.session_state[KEY_SHORT_LABELS] = short_labels
    st.session_state[KEY_MAPPING_DONE] = True
    st.session_state[KEY_REVERSE_DONE] = False
    st.session_state[KEY_WORKING_DF] = None
    st.session_state[KEY_FINAL_DF] = None
    return True


def _render_mapping_step():
    st.subheader("Step 2: Column Role Assignment")
    if not st.session_state.get(KEY_UPLOAD_DONE):
        st.info("Complete Step 1 (file upload) first.")
        return

    df = st.session_state[KEY_RAW_DF]
    col_list = list(df.columns)
    column_count = len(col_list)

    if st.session_state.get(PENDING_RESYNC_LABELS):
        _resync_all_auto_short_labels(column_count)
        st.session_state[PENDING_RESYNC_LABELS] = False

    if st.session_state.get(PENDING_CONFIRM_MAPPING):
        st.session_state[PENDING_CONFIRM_MAPPING] = False
        if _confirm_column_roles(col_list, column_count):
            st.rerun()
        # Validation failed — fall through and re-render mapper widgets.

    st.caption(
        "Tip: Google Forms exports often include a Timestamp column — set it to **Ignore**."
    )

    classification_rows = []
    for i, col in enumerate(col_list):
        role, reason = _classify_column_with_reason(col, df[col])
        classification_rows.append(
            {"Column": col if len(col) <= 55 else col[:52] + "…", "Default": role, "Reason": reason}
        )

    _init_mapper_widget_state(column_count, col_list, df)

    for i in range(column_count):
        if st.session_state.pop(f"{PENDING_SHORT_LABEL_MANUAL}_{i}", False):
            current = (st.session_state.get(_short_label_key(i)) or "").strip()
            cleaned = _sanitize_short_label(current)
            if cleaned != current:
                st.session_state[_short_label_key(i)] = cleaned
            auto = st.session_state.get(_short_label_auto_key(i))
            if auto is None or cleaned != _sanitize_short_label(str(auto)):
                st.session_state[_short_label_manual_key(i)] = True

    with st.expander("Classification decision log", expanded=False):
        st.caption("Why each column received its default role (recomputed from current data).")
        st.dataframe(pd.DataFrame(classification_rows), use_container_width=True, hide_index=True)

    for i, col in enumerate(col_list):
        series = df[col]
        default_reason = st.session_state.get(
            _role_reason_key(i),
            _classify_column_with_reason(col, series)[1],
        )

        st.markdown(f"**{col}**")
        st.caption(f"Auto-default: **{st.session_state.get(_role_key(i))}** — {default_reason}")
        meta_cols = st.columns([2, 2])
        with meta_cols[0]:
            st.caption(f"Sample: {_sample_values(series)}")
        with meta_cols[1]:
            role_label = st.selectbox(
                "Role",
                ROLE_OPTIONS,
                key=_role_key(i),
                label_visibility="collapsed",
            )

        if role_label == "Scale Item":
            label_cols = st.columns(2)
            scale_name_val = (st.session_state.get(_scale_name_key(i)) or "").strip()
            with label_cols[0]:
                st.text_input(
                    "Scale name",
                    key=_scale_name_key(i),
                    placeholder="e.g. Perfectionism / PRFQ / Sharenting",
                    on_change=_on_scale_name_change,
                    help="Typing a scale name auto-fills short labels on the next update.",
                )
            with label_cols[1]:
                st.text_input(
                    "Short label",
                    key=_short_label_key(i),
                    placeholder=(
                        _auto_short_label(scale_name_val or "Scale", i, column_count)
                        if scale_name_val
                        else "e.g. Perfectionism_1"
                    ),
                    help="Auto-filled as {ScaleName}_{n}; edit anytime to override.",
                    on_change=_on_short_label_change,
                    args=(i,),
                )

        st.divider()

    if st.button("Confirm Column Roles", type="primary", key="confirm_column_roles"):
        st.session_state[PENDING_RESYNC_LABELS] = True
        st.session_state[PENDING_CONFIRM_MAPPING] = True
        st.rerun()

    _render_config_save_load(df)

    if st.session_state.get(KEY_MAPPING_DONE):
        roles = st.session_state.get(KEY_COL_ROLES, {})
        scale_map = st.session_state.get(KEY_SCALE_MAP, {})
        short_labels = st.session_state.get(KEY_SHORT_LABELS, {})
        n_demo = sum(1 for r in roles.values() if r == "demographic")
        n_ignore = sum(1 for r in roles.values() if r == "ignore")
        scale_counts: dict[str, int] = {}
        for col, scale in scale_map.items():
            scale_counts[scale] = scale_counts.get(scale, 0) + 1

        st.success("Column roles confirmed.")
        st.write(f"- **Demographic columns:** {n_demo}")
        st.write(f"- **Ignored columns:** {n_ignore}")
        for scale_name, count in sorted(scale_counts.items()):
            st.write(f"- **{scale_name}:** {count} scale item(s) → `{', '.join(sorted(short_labels[c] for c in scale_map if scale_map[c] == scale_name))}`")


def _render_reverse_step():
    st.subheader("Step 3: Reverse Scoring")
    if not st.session_state.get(KEY_MAPPING_DONE):
        st.info("Complete Step 2 (column role assignment) first.")
        return

    if st.button("← Redo column mapping", key="back_to_column_mapping"):
        _redo_column_mapping()
        st.rerun()

    raw_cols = _scale_item_raw_columns()
    short_labels = st.session_state.get(KEY_SHORT_LABELS, {})

    if not raw_cols:
        st.warning("No scale items were mapped. Skipping reverse scoring.")
        if st.button("Continue without reverse scoring", key="skip_reverse"):
            st.session_state[KEY_WORKING_DF] = _build_analysis_dataframe(st.session_state[KEY_RAW_DF])
            st.session_state[KEY_REVERSE_CONFIG] = {}
            st.session_state[KEY_REVERSE_DONE] = True
            st.rerun()
        return

    scale_map = st.session_state.get(KEY_SCALE_MAP, {})
    for raw_col in raw_cols:
        short = short_labels.get(raw_col, raw_col)
        scale_name = scale_map.get(raw_col, "")
        default_min, default_max = _scale_bounds_for_name(scale_name)
        st.checkbox(
            f"Reverse score: **{short}** (scale: {scale_name or '—'})",
            key=f"reverse_chk_{raw_col}",
        )
        if st.session_state.get(f"reverse_chk_{raw_col}", False):
            c1, c2 = st.columns(2)
            with c1:
                st.number_input(
                    "Scale minimum",
                    min_value=0,
                    value=int(st.session_state.get(f"reverse_min_{raw_col}", default_min)),
                    key=f"reverse_min_{raw_col}",
                )
            with c2:
                st.number_input(
                    "Scale maximum",
                    min_value=1,
                    value=int(st.session_state.get(f"reverse_max_{raw_col}", default_max)),
                    key=f"reverse_max_{raw_col}",
                )

    if st.button("Apply Reverse Scoring", type="primary", key="apply_reverse"):
        raw_df = st.session_state[KEY_RAW_DF]
        working_df = _build_analysis_dataframe(raw_df)
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
                st.error(f"{short}: minimum cannot exceed maximum.")
                return
            before_after[short] = {
                "before": working_df[short].head(3).tolist(),
            }
            working_df[short] = (vmax + vmin) - working_df[short]
            before_after[short]["after"] = working_df[short].head(3).tolist()
            reverse_config[raw_col] = {"min": vmin, "max": vmax}
            reversed_short.append(short)

        range_errors = _validate_reversed_column_ranges(
            working_df, reverse_config, short_labels
        )
        if range_errors:
            for msg in range_errors:
                st.error(msg)
            st.error(
                "Reverse scoring produced values outside the configured scale range. "
                "Adjust min/max and try again."
            )
            return

        st.session_state[KEY_WORKING_DF] = working_df
        st.session_state[KEY_REVERSE_CONFIG] = reverse_config
        st.session_state[KEY_REVERSE_DONE] = True

        if reversed_short:
            st.success(f"Reverse scoring applied to {len(reversed_short)} column(s).")
            preview = pd.DataFrame(before_after).T
            st.write("Before / after (first 3 rows, short labels):")
            st.dataframe(preview, use_container_width=True)
        else:
            st.info("No items selected — working copy uses short labels without reversal.")
        st.rerun()

    if st.session_state.get(KEY_REVERSE_DONE):
        n_rev = len(st.session_state.get(KEY_REVERSE_CONFIG, {}))
        st.success(
            f"Reverse scoring step complete ({n_rev} item(s) reversed)."
            if n_rev
            else "Reverse scoring step complete (no items reversed)."
        )


def _composite_options_by_scale() -> dict[str, list[str]]:
    scale_map = st.session_state.get(KEY_SCALE_MAP, {})
    short_labels = st.session_state.get(KEY_SHORT_LABELS, {})
    grouped: dict[str, list[str]] = {}
    for raw_col, scale in scale_map.items():
        short = short_labels.get(raw_col, raw_col)
        grouped.setdefault(scale, []).append(short)
    for scale in grouped:
        grouped[scale].sort()
    return dict(sorted(grouped.items()))


def _render_composite_summary_and_download(final_df: pd.DataFrame, composites: list[dict]):
    if not composites:
        return

    raw_df = st.session_state.get(KEY_RAW_DF)
    total_rows = len(raw_df) if raw_df is not None else 0
    st.markdown("**Composite summaries**")
    rows = []
    alpha_n_values: list[int] = []
    for comp in composites:
        comp_name = comp.get("name")
        comp_cols = comp.get("columns", [])
        if not comp_name:
            continue
        series = final_df[comp_name].dropna()
        alpha_str, n_alpha = _cronbach_alpha_summary(comp_cols, final_df)
        if n_alpha is not None:
            alpha_n_values.append(n_alpha)
        rows.append(
            {
                "Composite": comp_name,
                "N": len(series),
                "Mean": round(series.mean(), 3) if len(series) else None,
                "SD": round(series.std(ddof=1), 3) if len(series) > 1 else None,
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
                    f"Cronbach's α used {n_alpha:,} complete cases of {total_rows:,} uploaded rows "
                    f"({(total_rows - n_alpha) / total_rows:.0%} excluded due to missing item data)."
                )
                break

    for comp in composites:
        comp_name = comp.get("name", "composite")
        comp_cols = comp.get("columns", [])
        if len(comp_cols) < 2:
            continue
        with st.expander(f"Item-total statistics: {comp_name}", expanded=False):
            stats_df = _item_total_statistics_table(comp_name, comp_cols, final_df)
            st.dataframe(stats_df, use_container_width=True, hide_index=True)

    csv_bytes = final_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇ Download preprocessed data (CSV)",
        data=csv_bytes,
        file_name="psychstats_preprocessed.csv",
        mime="text/csv",
    )


def _render_composite_step():
    st.subheader("Step 4: Composite Score Builder")
    if not st.session_state.get(KEY_REVERSE_DONE):
        st.info("Complete Step 3 (reverse scoring) first.")
        return

    if st.button("← Redo reverse scoring", key="back_to_reverse_scoring"):
        _redo_reverse_scoring()
        st.rerun()

    working_df = st.session_state.get(KEY_WORKING_DF)
    if working_df is None:
        working_df = _build_analysis_dataframe(st.session_state[KEY_RAW_DF])
        st.session_state[KEY_WORKING_DF] = working_df

    grouped = _composite_options_by_scale()
    flat_options: list[str] = []
    for scale_name, cols in grouped.items():
        for col in cols:
            flat_options.append(_composite_multiselect_label(scale_name, col))

    if st.button("Auto-suggest composites", key="auto_suggest_composites"):
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
        st.session_state["_composite_suggestions"] = suggestions
        st.info(
            f"Suggested {len(suggestions)} composite(s) below — review and click "
            "**Add Composite** for each, or edit before adding."
        )

    suggestions = st.session_state.pop("_composite_suggestions", None)
    if suggestions:
        st.markdown("**Suggested composites**")
        for comp in suggestions:
            comp_name = comp.get("name", "composite")
            comp_cols = comp.get("columns", [])
            comp_id = _composite_item_id(comp)
            st.write(
                f"- `{comp_name}` — {comp.get('method', 'sum').title()} of "
                f"{len(comp_cols)} item(s) ({', '.join(comp_cols[:3])}"
                f"{'…' if len(comp_cols) > 3 else ''})"
            )
            if st.button(f"Add suggested: {comp_name}", key=f"add_suggested_{comp_id}"):
                existing = _existing_column_names()
                if comp_name in existing:
                    st.error(f"Column `{comp_name}` already exists.")
                else:
                    st.session_state.setdefault(KEY_COMPOSITE_CONFIG, []).append(comp)
                    st.rerun()

    with st.form("add_composite_form", clear_on_submit=True):
        comp_name = st.text_input("Composite variable name", placeholder="Perfectionism_Total")
        selected_labels = st.multiselect(
            "Select items to include",
            options=flat_options,
            help="Items use short labels; grouped by scale.",
        )
        method_label = st.radio("Method", ["Sum", "Mean"], horizontal=True)
        submitted = st.form_submit_button("Add Composite")

    if submitted:
        comp_name_clean = _sanitize_short_label(comp_name.strip()) if comp_name.strip() else ""
        if not comp_name_clean:
            st.error("Enter a composite variable name.")
        elif comp_name_clean in _existing_column_names():
            st.error(f"Column `{comp_name_clean}` already exists in the dataset.")
        elif not selected_labels:
            st.error("Select at least one item.")
        else:
            selected_cols = [_parse_composite_multiselect_label(label) for label in selected_labels]
            scale_map = st.session_state.get(KEY_SCALE_MAP, {})
            short_labels = st.session_state.get(KEY_SHORT_LABELS, {})
            short_to_scale = {short_labels[r]: scale_map[r] for r in scale_map if r in short_labels}
            scales_used = {short_to_scale.get(c) for c in selected_cols if c in short_to_scale}
            scales_used.discard(None)
            if len(scales_used) > 1:
                st.warning(
                    "Selected items span multiple scales "
                    f"({', '.join(sorted(scales_used))}). Cross-scale composites are allowed "
                    "but interpret with caution."
                )
            method = "sum" if method_label == "Sum" else "mean"
            st.session_state.setdefault(KEY_COMPOSITE_CONFIG, []).append(
                {
                    "id": _new_composite_id(),
                    "name": comp_name_clean,
                    "columns": selected_cols,
                    "method": method,
                }
            )
            st.rerun()

    composites = st.session_state.get(KEY_COMPOSITE_CONFIG, [])
    if composites:
        st.markdown("**Defined composites**")
        for comp in composites:
            comp_id = _composite_item_id(comp)
            comp_name = comp.get("name", "composite")
            comp_cols = comp.get("columns", [])
            comp_method = comp.get("method", "sum")
            c1, c2 = st.columns([5, 1])
            with c1:
                st.write(
                    f"**{comp_name}** — {comp_method.title()} of "
                    f"{len(comp_cols)} item(s): {', '.join(comp_cols)}"
                )
            with c2:
                if st.button("Delete", key=f"delete_composite_{comp_id}"):
                    st.session_state[KEY_COMPOSITE_CONFIG] = [
                        c
                        for c in st.session_state.get(KEY_COMPOSITE_CONFIG, [])
                        if _composite_item_id(c) != comp_id
                    ]
                    st.rerun()

    if st.button("Build All Composites", type="primary", key="build_composites"):
        final_df = working_df.copy()
        composites = st.session_state.get(KEY_COMPOSITE_CONFIG, [])

        for comp in composites:
            name = comp.get("name")
            cols = comp.get("columns", [])
            method = comp.get("method", "sum")
            if not name or not cols:
                continue
            if name in final_df.columns:
                st.error(f"Column `{name}` already exists. Remove or rename the composite.")
                return
            subset = final_df[cols]
            if method == "sum":
                final_df[name] = subset.sum(axis=1, skipna=True)
            else:
                final_df[name] = subset.mean(axis=1, skipna=True)

        st.session_state[KEY_FINAL_DF] = final_df
        st.success("✅ Preprocessing complete. You can now proceed to analysis.")
        st.rerun()

    final_df = st.session_state.get(KEY_FINAL_DF)
    if final_df is not None:
        composites = st.session_state.get(KEY_COMPOSITE_CONFIG, [])
        _render_composite_summary_and_download(final_df, composites)
        if not composites:
            csv_bytes = final_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "⬇ Download preprocessed data (CSV)",
                data=csv_bytes,
                file_name="psychstats_preprocessed.csv",
                mime="text/csv",
                key="download_preprocessed_no_composites",
            )


def render():
    st.header("Data Upload & Preprocessing")

    with st.expander("Step 1: File Upload", expanded=not st.session_state.get(KEY_UPLOAD_DONE)):
        _render_upload_step()

    with st.expander(
        "Step 2: Column Role Assignment",
        expanded=st.session_state.get(KEY_UPLOAD_DONE, False)
        and not st.session_state.get(KEY_MAPPING_DONE, False),
    ):
        _render_mapping_step()

    with st.expander(
        "Step 3: Reverse Scoring",
        expanded=st.session_state.get(KEY_MAPPING_DONE, False)
        and not st.session_state.get(KEY_REVERSE_DONE, False),
    ):
        _render_reverse_step()

    with st.expander(
        "Step 4: Composite Score Builder",
        expanded=st.session_state.get(KEY_REVERSE_DONE, False)
        and st.session_state.get(KEY_FINAL_DF) is None,
    ):
        _render_composite_step()
