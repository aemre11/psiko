"""
PsychStats — modernized layout entrypoint.

Replaces the old vertical-expander stack with a horizontal 6-step Process
Stepper and a single "Main Content Card" that wraps each step's widgets.

  Step 1 — Dosya Yükleme
  Step 2 — Sütun Rolleri
  Step 3 — Ölçek Tanımlama ve Atama
  Step 4 — Ters Puanlama
  Step 5 — Bileşik Puan Oluşturucu
  Step 6 — Analiz ve Raporlama (sub-tabs: Betimsel / Grup / Korelasyon / Word)

Active step is derived from the existing session_state completion flags,
with an optional manual override (`_active_step_index`) so the user can
jump back to a completed step from the sidebar or the footer.
"""

import streamlit as st
import streamlit.components.v1 as components

from modules import correlation, data_manager, descriptives, export, inferential
from modules.correlation import KEY_CORRELATION_RESULTS
from modules.data_manager import (
    KEY_FINAL_DF,
    KEY_MAPPING_DONE,
    KEY_RAW_DF,
    KEY_REVERSE_DONE,
    KEY_ROLES_CONFIRMED,
    KEY_UPLOAD_DONE,
    init_session_state,
)
from modules.descriptives import KEY_NORMALITY_RESULTS
from modules.inferential import KEY_INFERENTIAL_RUN

from psychstats_theme import inject_css
from psychstats_layout import (
    Step,
    close_step_shell,
    inject_layout_css,
    open_step_shell,
    render_sidebar_progress,
    segmented_control,
)


# ---------------------------------------------------------------------------
# Session-state key for the active step (manual override of the auto value).
# ---------------------------------------------------------------------------
ACTIVE_STEP_KEY = "_active_step_index"
ANALYSIS_TAB_KEY = "_analysis_tab_selection"
LAST_RENDERED_STEP_KEY = "_last_rendered_step"
FORCE_SCROLL_KEY = "_force_scroll_top"


def _scroll_to_top() -> None:
    """
    Fire a one-shot script that scrolls the main Streamlit pane back to the
    top. Implemented via a 0-height components.html iframe — `unsafe_allow_html`
    strips <script> tags, so this is the only reliable channel.

    Used in two places:
      (a) auto-fire whenever the active step changes (handled in this file).
      (b) explicit signal: any data_manager helper that wants to scroll
          (e.g. "Bileşikleri Otomatik Öner") sets st.session_state
          ["_force_scroll_top"] = True before calling st.rerun(). This file
          consumes it on the next run.
    """
    components.html(
        """
        <script>
          // Climb out of the iframe and scroll the parent page.
          const p = window.parent;
          // Streamlit's main scroll container varies by version.
          const main = p.document.querySelector('section.main')
                    || p.document.querySelector('.main')
                    || p.document.querySelector('[data-testid="stAppViewContainer"]')
                    || p.document.scrollingElement
                    || p.document.documentElement;
          if (main && main.scrollTo) main.scrollTo({top: 0, behavior: 'instant'});
          p.scrollTo({top: 0, behavior: 'instant'});
        </script>
        """,
        height=0,
    )


# ---------------------------------------------------------------------------
# Step definitions — title/subtitle/state derived per-render
# ---------------------------------------------------------------------------
STEP_LABELS = [
    "Dosya Yükleme",
    "Sütun Rolleri",
    "Ölçek Tanımlama ve Atama",
    "Ters Puanlama",
    "Bileşik Puan Oluşturucu",
    "Analiz ve Raporlama",
]

STEP_META = {
    1: {
        "title": "Dosya Yükleme",
        "subtitle": "Veri dosyanızı (.csv veya .xlsx) yükleyin ve ön kontrol yapın.",
    },
    2: {
        "title": "Sütun Rolleri",
        "subtitle": "Her sütunu Ölçek Maddesi · Demografik · Yok say olarak işaretleyin.",
    },
    3: {
        "title": "Ölçek Tanımlama ve Atama",
        "subtitle": "Ölçekleri tanımlayın ve madde sütun aralıklarını eşleştirin.",
    },
    4: {
        "title": "Ters Puanlama",
        "subtitle": "Negatif yönde puanlanmış maddeleri ölçek aralığına göre çevirin.",
    },
    5: {
        "title": "Bileşik Puan Oluşturucu",
        "subtitle": "Alt ölçeklerin toplam veya ortalama puanlarını oluşturun.",
    },
    6: {
        "title": "Analiz ve Raporlama",
        "subtitle": "Betimsel istatistikler, grup karşılaştırmaları, korelasyon, dışa aktarma.",
    },
}

ANALYSIS_TABS = [
    ("Betimsel İstatistikler", descriptives.render),
    ("Grup Karşılaştırmaları", inferential.render),
    ("Korelasyon ve Moderasyon", correlation.render),
    ("Word'e Aktar", export.render),
]


# ---------------------------------------------------------------------------
# Active-step computation
# ---------------------------------------------------------------------------

def _step_completion_flags() -> list[bool]:
    """Per-step completion (1-indexed): index 0 = step 1, etc. (6 entries)."""
    ss = st.session_state
    return [
        bool(ss.get(KEY_UPLOAD_DONE, False)),         # step 1 - upload
        bool(ss.get(KEY_ROLES_CONFIRMED, False)),     # step 2 - column roles (sub-phase A)
        bool(ss.get(KEY_MAPPING_DONE, False)),         # step 3 - scale assignment (sub-phase B)
        bool(ss.get(KEY_REVERSE_DONE, False)),         # step 4 - reverse scoring
        ss.get(KEY_FINAL_DF) is not None,              # step 5 - composites built
        bool(ss.get(KEY_NORMALITY_RESULTS)),           # step 6 - analysis touched
    ]


def _default_active_step() -> int:
    """First non-complete prep step, or step 6 (analysis) once all prep is done."""
    flags = _step_completion_flags()
    for i, done in enumerate(flags[:5], start=1):
        if not done:
            return i
    return 6


def _active_step() -> int:
    override = st.session_state.get(ACTIVE_STEP_KEY)
    if override is not None:
        # If prerequisites are no longer satisfied (e.g. user redid mapping
        # while pinned to step 4), drop the override and recompute.
        if _can_visit(int(override)):
            return int(override)
        st.session_state.pop(ACTIVE_STEP_KEY, None)
    return _default_active_step()


def _can_visit(step: int) -> bool:
    """Step is visitable if it's the current default OR it's already complete
    OR every step before it is complete."""
    flags = _step_completion_flags()
    if step == 1:
        return True
    # All steps strictly before must be complete to visit this one.
    return all(flags[: step - 1])


def _navigate_to(step: int) -> None:
    if not (1 <= step <= 6):
        return
    st.session_state[ACTIVE_STEP_KEY] = step
    st.rerun()


def _clear_override() -> None:
    st.session_state.pop(ACTIVE_STEP_KEY, None)


def _build_steps(active: int) -> list[Step]:
    """
    Build the list of Step entries for the stepper. State semantics:
      - completed flag from session state  → "complete"
      - the active step (passed in)        → "active"  (forced by open_step_shell)
      - everything else                    → "locked"
    """
    flags = _step_completion_flags()
    steps: list[Step] = []
    for i, label in enumerate(STEP_LABELS, start=1):
        if i == active:
            state = "active"
        elif flags[i - 1]:
            state = "complete"
        else:
            state = "locked"
        steps.append(Step(label=label, state=state))
    return steps


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _render_sidebar(active: int) -> None:
    ss = st.session_state

    with st.sidebar:
        st.markdown(
            '<h3 style="margin:0 0 4px;font-family:Inter;font-size:11px;'
            'letter-spacing:.12em;text-transform:uppercase;color:#6e7681;">'
            'PsychStats</h3>'
            '<p style="margin:0 0 18px;font-size:18px;font-weight:600;color:#e6edf3;'
            'letter-spacing:-.01em;">Tez Analiz Aracı</p>',
            unsafe_allow_html=True,
        )

        # Jump-to-step nav. Disabled steps are shown but won't navigate.
        st.markdown("**Akış**")
        for i, label in enumerate(STEP_LABELS, start=1):
            visitable = _can_visit(i)
            is_active = (i == active)
            disabled = not visitable and not is_active
            btn_label = f"{i:02d}  {label}"
            if st.button(
                btn_label,
                key=f"nav_step_{i}",
                use_container_width=True,
                disabled=disabled,
                type="primary" if is_active else "secondary",
            ):
                _navigate_to(i)

        st.divider()

        st.markdown("**Analiz İlerlemesi**")
        render_sidebar_progress([
            ("Veri yüklendi",                       ss.get(KEY_RAW_DF) is not None),
            ("Ölçekler atandı",                     ss.get(KEY_MAPPING_DONE, False)),
            ("Ters puanlama tamamlandı",            ss.get(KEY_REVERSE_DONE, False)),
            ("Bileşikler oluşturuldu",              ss.get(KEY_FINAL_DF) is not None),
            ("Betimsel istatistikler tamamlandı",   bool(ss.get(KEY_NORMALITY_RESULTS))),
            ("Grup karşılaştırmaları",              ss.get(KEY_INFERENTIAL_RUN, False)),
            ("Korelasyon ve moderasyon",            bool(ss.get(KEY_CORRELATION_RESULTS))),
            ("Dışa aktarmaya hazır",
             ss.get(KEY_FINAL_DF) is not None and bool(ss.get(KEY_NORMALITY_RESULTS))),
        ])


# ---------------------------------------------------------------------------
# Footer: Previous / Next navigation
# ---------------------------------------------------------------------------

def _footer_nav(active: int) -> None:
    """
    Per-step internal 'Apply' buttons already flip the completion flags.
    The footer here only gives the user a way to step BACK (re-edit a
    completed step) or jump FORWARD (when prerequisites are met).
    """
    flags = _step_completion_flags()
    can_advance = (active < 6) and (flags[active - 1] if active <= 5 else False)

    secondary_label = "← Önceki adım" if active > 1 else None
    primary_label = "Sonraki adım →" if can_advance else None

    actions = close_step_shell(
        helper_text=(
            "İpucu: tüm değişiklikler otomatik olarak kaydedilir."
            if flags[active - 1] or active == 6
            else "Devam etmek için bu adımdaki onay/uygula düğmesine basın."
        ),
        primary_label=primary_label,
        secondary_label=secondary_label,
        primary_key=f"footer_next_{active}",
        secondary_key=f"footer_prev_{active}",
    )

    if actions.get("secondary"):
        _navigate_to(active - 1)
    if actions.get("primary"):
        _navigate_to(active + 1)


# ---------------------------------------------------------------------------
# Step 6: Analysis sub-tabs
# ---------------------------------------------------------------------------

def _render_analysis_phase() -> None:
    """Pill segmented-control sub-nav for the 4 analysis modules."""
    tab_labels = [name for name, _ in ANALYSIS_TABS]
    selected = segmented_control(
        "Analiz modülü",
        options=tab_labels,
        key=ANALYSIS_TAB_KEY,
        default=tab_labels[0],
    )
    # Spacer
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    for name, render_fn in ANALYSIS_TABS:
        if selected == name:
            render_fn()
            return


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="PsychStats",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject base theme + modern layout CSS.
inject_css()
inject_layout_css()

# ---------------------------------------------------------------------------
# Authentication gate (Streamlit Community Cloud)
# Single trusted user. The password lives ONLY in the Cloud secrets manager as
# st.secrets["app_password"] — never hardcoded, never committed. Runs after
# set_page_config (which must stay the first Streamlit call) and before any app
# logic; nothing below executes until the correct password is entered.
# ---------------------------------------------------------------------------
if not st.session_state.get("_authenticated", False):
    st.title("🧬 PsychStats")
    # Fail closed: if the app_password secret isn't configured, never grant access —
    # show a clear message and stop, instead of crashing with a raw
    # StreamlitSecretNotFoundError at whoever opens the app.
    try:
        _expected_pw = st.secrets["app_password"]
    except Exception:
        st.error(
            "Uygulama yapılandırılmamış: erişim parolası tanımlı değil. "
            "Lütfen sistem yöneticisiyle iletişime geçin."
        )
        st.stop()
    _pw = st.text_input("Parola", type="password", key="_auth_password")
    if _pw:
        if _pw == _expected_pw:
            st.session_state["_authenticated"] = True
            st.rerun()
        else:
            st.error("Hatalı parola. Lütfen tekrar deneyin.")
    st.stop()

# Initialize session-state defaults BEFORE any widget reads them.
init_session_state()

# Determine which step we're on.
active = _active_step()

# Scroll-to-top handling:
#   - on a step transition (last != current), OR
#   - on an explicit one-shot signal raised by a helper that wants to scroll.
_last = st.session_state.get(LAST_RENDERED_STEP_KEY)
_force = st.session_state.pop(FORCE_SCROLL_KEY, False)
if _last is not None and (_last != active or _force):
    _scroll_to_top()
st.session_state[LAST_RENDERED_STEP_KEY] = active

# Render sidebar (nav + progress). Buttons in here may trigger a rerun
# via _navigate_to(); that's fine — they run before the shell opens.
_render_sidebar(active)

# Build dynamic stepper data and shell metadata.
steps = _build_steps(active)
meta = STEP_META[active]

ss = st.session_state
total_n = "—"
if ss.get(KEY_RAW_DF) is not None:
    try:
        total_n = f"N = {len(ss[KEY_RAW_DF])}"
    except Exception:
        total_n = "—"

# Open the shell. Returns the st.container() that IS the card body.
body = open_step_shell(
    steps,
    active_step=active,
    title=meta["title"],
    subtitle=meta["subtitle"],
    page_title="PsychStats — Tez Analiz Aracı",
    meta=total_n if total_n != "—" else None,
)

# Render the active step's widgets INSIDE the card body container.
with body:
    if active in (1, 2, 3, 4, 5):
        data_manager.render(active_step=active)
    elif active == 6:
        if ss.get(KEY_FINAL_DF) is not None:
            _render_analysis_phase()
        else:
            st.info("Analiz aşamasına geçmek için önce Adım 1–5'i tamamlayın.")

# Footer: Previous / Next navigation buttons.
_footer_nav(active)
