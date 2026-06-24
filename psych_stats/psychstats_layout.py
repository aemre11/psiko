"""
psychstats_layout.py
====================

Drop-in Streamlit module that renders a horizontal Process Stepper and a
"Main Content Card" shell around your existing widgets.

Design tokens follow the PsychStats Design System spec exactly:
- Surface: #1c2128 on #0d1117 page
- Active step: gold #d4a843
- Complete step: green #2ea043
- Accent: indigo #6e76f7
- Inter (sans) + JetBrains Mono (mono) via Google Fonts

USAGE
-----
    import streamlit as st
    from psychstats_layout import open_step_shell, close_step_shell, Step

    STEPS = [
        Step("Dosya Yükleme",          "complete"),
        Step("Sütun ve Ölçek Atama",   "complete"),
        Step("Ters Puanlama",          "active"),
        Step("Bileşik Puan Oluşturucu","locked"),
        Step("Analiz ve Raporlama",    "locked"),
    ]

    body = open_step_shell(
        STEPS,
        active_step=3,
        title="Ters Puanlama",
        subtitle="Negatif yönde puanlanmış maddeleri ölçek aralığına göre çevir.",
        meta="N = 203 · 47 sütun yüklendi",
    )

    with body:
        # Native Streamlit widgets — event listeners untouched
        c1, c2 = st.columns(2)
        with c1: st.number_input("Ölçek minimum", value=1)
        with c2: st.number_input("Ölçek maksimum", value=5)
        st.multiselect("Ters puanlanacak maddeler", options=items)

    close_step_shell(primary_label="Ters puanlamayı uygula →")


WHY THIS APPROACH IS SAFE FOR STREAMLIT
---------------------------------------
We never wrap a widget inside a hand-written <div> (which would either be
broken by Streamlit's DOM reconciliation, or — worse — cut the widget off
from its iframe message channel). Instead we:

  1. Render the stepper + card-head as static `st.markdown(unsafe_allow_html=True)`.
  2. Create a normal `st.container()` for the body. Streamlit owns this
     container's DOM and lifecycle, including all widget event listeners.
  3. Drop a tiny invisible "anchor" element inside that container.
  4. Style the container's outer `[data-testid="stVerticalBlock"]` using
     `:has(.ps-card-body-anchor)` — purely cosmetic, no DOM mutation.

The result: widgets sit visually inside a beautiful dark card, but the
Streamlit ↔ Python bridge for every widget is exactly as Streamlit
shipped it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Optional

import streamlit as st


StepState = Literal["complete", "active", "locked"]


@dataclass(frozen=True)
class Step:
    """A single entry in the process stepper."""
    label: str
    state: StepState = "locked"


# ---------------------------------------------------------------------------
# CSS — injected exactly once per session via _inject_css()
# ---------------------------------------------------------------------------

_CSS = r"""
/* ============================================================
   PsychStats — Modern Dashboard Layout
   All rules are scoped under .psychstats-shell or via :has()
   on our anchor element, so Streamlit's own CSS is untouched.
   ============================================================ */

/* --- Fonts (loaded once; safe to repeat — browser dedupes) --- */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* --- Page chrome --- */
.stApp {
    background: #0d1117;
}
/* Apply Inter only to text-bearing elements — NEVER to bare span/div,
   because Streamlit's Material Symbols icons live inside <span> elements
   with their own `font-family: 'Material Symbols Outlined'`. Forcing
   Inter on those spans makes the icon render as raw text ("arrow_right",
   "upload", etc.) — that was the cause of "uploadpload" on the file
   uploader and "_arrow_right(madde)" on the multiselect dropdowns. */
.stApp,
.stApp p,
.stApp label,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stMarkdownContainer"] *:not([class*="material"]):not([class*="icon"]),
.stApp button {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
/* Defensive: explicitly preserve the icon font on Streamlit's icon spans */
.stApp [class*="material-symbols"],
.stApp [data-testid*="Icon"],
.stApp [data-testid*="icon"],
.stApp .material-icons,
.stApp .material-symbols-outlined,
.stApp .material-symbols-rounded,
.stApp .material-symbols-sharp {
    font-family: 'Material Symbols Outlined', 'Material Symbols Rounded', 'Material Icons' !important;
}

/* Hide Streamlit's default top padding so the stepper hugs the top */
.stApp > header { background: transparent; }
.block-container { padding-top: 2.5rem !important; padding-bottom: 4rem !important; max-width: 1180px !important; }

/* ============================================================
   Shell tokens
   ============================================================ */
.psychstats-shell {
    --color-bg: #0d1117;
    --color-surface: #1c2128;
    --color-surface-elevated: #22272e;
    --color-border: #30363d;
    --color-border-subtle: #21262d;

    --color-text-primary: #e6edf3;
    --color-text-secondary: #8b949e;
    --color-text-muted: #6e7681;

    --color-accent: #6e76f7;
    --color-accent-hover: #8b92f8;
    --color-accent-subtle: rgba(110, 118, 247, 0.12);

    --color-step-active: #d4a843;
    --color-step-active-tint: rgba(212, 168, 67, 0.14);
    --color-step-active-glow: rgba(212, 168, 67, 0.35);
    --color-step-complete: #2ea043;
    --color-step-complete-tint: rgba(46, 160, 67, 0.14);
    --color-step-locked: #6e7681;

    --radius-md: 8px;
    --radius-lg: 12px;
    --radius-pill: 999px;

    font-family: 'Inter', sans-serif;
    color: var(--color-text-primary);
    line-height: 1.5;
    margin-bottom: 8px;
}

/* --- Page header --- */
.psychstats-shell .ps-header {
    display: flex; align-items: flex-end; justify-content: space-between;
    gap: 24px; padding-bottom: 20px;
    border-bottom: 1px solid var(--color-border-subtle);
    margin-bottom: 28px;
}
.psychstats-shell .ps-title {
    font-size: 22px; font-weight: 600; letter-spacing: -0.015em; margin: 0;
    color: var(--color-text-primary);
}
.psychstats-shell .ps-subtitle {
    font-size: 13px; color: var(--color-text-secondary);
    margin: 4px 0 0; font-weight: 400;
}
.psychstats-shell .ps-meta {
    display: flex; align-items: center; gap: 10px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; color: var(--color-text-muted);
    letter-spacing: 0.04em; text-transform: uppercase;
}
.psychstats-shell .ps-meta-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--color-step-complete);
    box-shadow: 0 0 8px rgba(46, 160, 67, 0.5);
}

/* --- Horizontal stepper --- */
.psychstats-shell .ps-stepper {
    display: grid; grid-template-columns: repeat(var(--ps-step-count, 5), 1fr);
    gap: 0; position: relative; margin-bottom: 24px; padding: 4px 0 8px;
}
.psychstats-shell .ps-step {
    position: relative; display: flex; flex-direction: column;
    align-items: flex-start; padding: 0 14px; min-width: 0;
}
.psychstats-shell .ps-step::after {
    content: ""; position: absolute; top: 14px;
    left: calc(50% + 18px); right: calc(-50% + 18px);
    height: 2px; background: var(--color-border-subtle); z-index: 0;
}
.psychstats-shell .ps-step:last-child::after { display: none; }
.psychstats-shell .ps-step.complete::after { background: var(--color-step-complete); }

.psychstats-shell .ps-step-marker {
    position: relative; z-index: 1;
    width: 28px; height: 28px; border-radius: 50%;
    display: inline-flex; align-items: center; justify-content: center;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px; font-weight: 600;
    background: var(--color-surface);
    border: 1.5px solid var(--color-border);
    color: var(--color-text-muted);
    transition: all 160ms ease;
}
.psychstats-shell .ps-step.complete .ps-step-marker {
    background: var(--color-step-complete);
    border-color: var(--color-step-complete);
    color: #0d1117;
}
.psychstats-shell .ps-step.complete .ps-step-marker::before {
    content: "✓"; font-family: 'Inter', sans-serif;
    font-size: 14px; font-weight: 700; line-height: 1;
}
.psychstats-shell .ps-step.complete .ps-num { display: none; }
.psychstats-shell .ps-step.active .ps-step-marker {
    background: var(--color-step-active);
    border-color: var(--color-step-active);
    color: #0d1117;
    box-shadow: 0 0 0 4px var(--color-step-active-tint),
                0 0 16px var(--color-step-active-glow);
}
.psychstats-shell .ps-step.locked .ps-step-marker {
    background: var(--color-surface);
    border-style: dashed; border-color: var(--color-border);
    color: var(--color-text-muted);
}

.psychstats-shell .ps-step-body { margin-top: 12px; min-width: 0; }
.psychstats-shell .ps-step-eyebrow {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; font-weight: 600;
    letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--color-text-muted); margin: 0 0 4px;
}
.psychstats-shell .ps-step.complete .ps-step-eyebrow { color: var(--color-step-complete); }
.psychstats-shell .ps-step.active   .ps-step-eyebrow { color: var(--color-step-active); }
.psychstats-shell .ps-step-label {
    font-size: 12.5px; font-weight: 500; color: var(--color-text-secondary);
    margin: 0; line-height: 1.3;
    /* Wrap to a max of 2 lines; reserve the space so all step bodies align
       even when some labels are 1-line and others are 2-line. */
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    overflow-wrap: break-word;
    min-height: 2.6em;
}
.psychstats-shell .ps-step.active .ps-step-label {
    color: var(--color-text-primary); font-weight: 600;
}
.psychstats-shell .ps-step.locked .ps-step-label { color: var(--color-text-muted); }

/* --- Card head (above the widgets) --- */
.psychstats-shell .ps-card-head {
    background: var(--color-surface);
    border: 1px solid var(--color-border-subtle);
    border-bottom: none;
    border-radius: var(--radius-lg) var(--radius-lg) 0 0;
    padding: 24px 32px 16px;
    position: relative;
    margin-bottom: 0;
}
.psychstats-shell .ps-card-head::before {
    content: ""; position: absolute; top: 0; left: 0;
    width: 3px; height: 100%;
    background: var(--color-step-active); opacity: 0.9;
    border-top-left-radius: var(--radius-lg);
}
.psychstats-shell .ps-card-head-row {
    display: flex; align-items: center; justify-content: space-between;
    gap: 16px; padding-bottom: 16px;
    border-bottom: 1px solid var(--color-border-subtle);
}
.psychstats-shell .ps-card-head-left { display: flex; align-items: center; gap: 14px; }
.psychstats-shell .ps-card-step-pill {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 10px; border-radius: var(--radius-pill);
    background: var(--color-step-active-tint);
    color: var(--color-step-active);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; font-weight: 600;
    letter-spacing: 0.06em; text-transform: uppercase;
}
.psychstats-shell .ps-card-step-pill::before {
    content: ""; width: 6px; height: 6px; border-radius: 50%;
    background: var(--color-step-active);
    box-shadow: 0 0 8px var(--color-step-active-glow);
}
.psychstats-shell .ps-card-title {
    font-size: 18px; font-weight: 600; letter-spacing: -0.01em;
    margin: 0; color: var(--color-text-primary);
}
.psychstats-shell .ps-card-subtitle {
    font-size: 13px; color: var(--color-text-secondary); margin: 4px 0 0;
}

/* --- Card body wrapper — applied via :has() on the Streamlit container --- */
/* The anchor div tells us "this stVerticalBlock IS our card body". */
.ps-card-body-anchor { display: none; }

/* Streamlit's container has data-testid="stVerticalBlock".
   We find the one containing our anchor and dress it as the card body. */
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor),
[data-testid="stVerticalBlock"]:has(> div > div > .ps-card-body-anchor) {
    background: #1c2128;
    border: 1px solid #21262d;
    border-top: none;
    border-radius: 0 0 12px 12px;
    padding: 20px 32px 28px !important;
    position: relative;
    box-shadow: 0 1px 0 rgba(255, 255, 255, 0.02) inset;
}
/* Gold accent strip continues from the head into the body */
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor)::before,
[data-testid="stVerticalBlock"]:has(> div > div > .ps-card-body-anchor)::before {
    content: ""; position: absolute; left: -1px; top: 0; bottom: 0;
    width: 3px; background: #d4a843; opacity: 0.9;
    border-bottom-left-radius: 12px;
}

/* ============================================================
   Streamlit widget restyling INSIDE the card body
   We scope each rule with the :has() selector so Streamlit's
   widgets outside the card are unaffected.
   We only override VISUAL properties — never display, position,
   pointer-events, or anything that could break event handling.
   ============================================================ */
.ps-card-scope {
    /* a class we add to widgets-wrapper to keep selectors short */
}

/* Inputs (text, number) */
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stTextInput"] input,
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stNumberInput"] input,
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-baseweb="input"] input {
    background: #0d1117 !important;
    border: 1px solid #30363d !important;
    border-radius: 8px !important;
    color: #e6edf3 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13px !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stTextInput"] input:focus,
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stNumberInput"] input:focus {
    border-color: #6e76f7 !important;
    box-shadow: 0 0 0 3px rgba(110, 118, 247, 0.15) !important;
    outline: none !important;
}

/* Labels above widgets */
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) label,
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) label p {
    color: #8b949e !important;
    font-size: 12px !important;
    font-weight: 500 !important;
}

/* Selectbox + multiselect base */
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-baseweb="select"] > div {
    background: #0d1117 !important;
    border: 1px solid #30363d !important;
    border-radius: 8px !important;
    color: #e6edf3 !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-baseweb="tag"] {
    background: rgba(110, 118, 247, 0.12) !important;
    border: 1px solid rgba(110, 118, 247, 0.4) !important;
    color: #8b92f8 !important;
}

/* Buttons inside the card — pill, accent.
   Scope STRICTLY to st.button's outer container so we never touch the
   internal <button> elements inside stFileUploader, stCameraInput,
   stDownloadButton chrome, or BaseWeb's own modal/popover buttons.
   Targeting [data-testid="baseButton-secondary"] broadly was the cause
   of the "uploadpload" overlap on the file uploader's Browse button. */
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stButton"] > button {
    background: #6e76f7 !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 999px !important;
    padding: 8px 18px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    transition: transform 140ms ease, box-shadow 140ms ease, background 140ms ease !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stButton"] > button:hover {
    transform: translateY(-1px);
    background: #8b92f8 !important;
    box-shadow: 0 6px 18px rgba(110, 118, 247, 0.42) !important;
}
/* Secondary (type="secondary") st.buttons — outlined, not filled */
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stButton"] > button[kind="secondary"] {
    background: transparent !important;
    border: 1.5px solid #6e76f7 !important;
    color: #8b92f8 !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stButton"] > button[kind="secondary"]:hover {
    background: rgba(110, 118, 247, 0.12) !important;
}

/* Radio (Toplam / Ortalama) */
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stRadio"] > div {
    gap: 16px;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stRadio"] label {
    color: #e6edf3 !important;
    font-size: 13px !important;
}

/* Caption helper text */
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stCaptionContainer"] {
    color: #6e7681 !important;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px !important;
}

/* --- Card footer (Önceki / Sonraki nav) ---
   Sits below the card with breathing room, not butt-joined. */
.psychstats-shell-footer {
    margin-top: 28px;
    padding: 20px 0 0;
    border-top: 1px solid var(--color-border-subtle);
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px;
}
.psychstats-shell-footer .ps-helper {
    font-size: 12px; color: var(--color-text-muted);
    font-family: 'JetBrains Mono', monospace;
}

/* ============================================================
   DATA QUALITY GLANCE CARD — 4-up metric strip on Step 1
   ============================================================ */
.psychstats-shell .ps-quality-grid,
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) .ps-quality-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin: 8px 0 16px;
}
.psychstats-shell .ps-quality-card,
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) .ps-quality-card {
    background: #0d1117;
    border: 1px solid #21262d;
    border-radius: 10px;
    padding: 14px 16px;
    transition: border-color 140ms ease;
}
.ps-quality-card:hover { border-color: #30363d; }
.ps-quality-card--ok    { border-color: rgba(46, 160, 67, 0.35); }
.ps-quality-card--ok .ps-quality-value { color: #3fb950; }
.ps-quality-card--warn  { border-color: rgba(212, 168, 67, 0.45); }
.ps-quality-card--warn .ps-quality-value { color: #e3b341; }

.ps-quality-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #6e7681;
    margin-bottom: 6px;
}
.ps-quality-value {
    font-family: 'Inter', sans-serif;
    font-size: 22px;
    font-weight: 600;
    color: #e6edf3;
    line-height: 1.1;
    margin-bottom: 4px;
    letter-spacing: -0.015em;
    font-variant-numeric: tabular-nums;
}
.ps-quality-sub {
    font-size: 11.5px;
    color: #6e7681;
    line-height: 1.3;
}

@media (max-width: 720px) {
    .psychstats-shell .ps-quality-grid,
    [data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) .ps-quality-grid {
        grid-template-columns: repeat(2, 1fr);
    }
}

/* ============================================================
   DEMO DATASET BADGE
   ============================================================ */
.ps-demo-badge {
    display: inline-block;
    margin: 0 0 12px;
    padding: 6px 12px;
    border-radius: 999px;
    background: rgba(212, 168, 67, 0.14);
    border: 1px solid rgba(212, 168, 67, 0.45);
    color: #e3b341;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.04em;
}

/* ============================================================
   SIDEBAR — dark surface, refined nav
   Streamlit selector: [data-testid="stSidebar"]
   ============================================================ */
[data-testid="stSidebar"] {
    background: #161b22 !important;
    border-right: 1px solid #21262d !important;
}
[data-testid="stSidebar"] > div:first-child {
    padding-top: 24px !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #e6edf3 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    letter-spacing: 0.04em !important;
    text-transform: uppercase !important;
    margin: 0 0 12px !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] li,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label {
    color: #8b949e !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13px !important;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] strong {
    color: #e6edf3 !important;
}
/* Sidebar radio = page nav — render as stacked nav rows */
[data-testid="stSidebar"] [data-testid="stRadio"] > div {
    gap: 2px !important;
    flex-direction: column !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 8px 10px !important;
    margin: 0 !important;
    width: 100%;
    cursor: pointer;
    transition: background 120ms ease, border-color 120ms ease, color 120ms ease;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background: #22272e;
    border-color: #21262d;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-checked="true"],
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
    background: rgba(110, 118, 247, 0.12) !important;
    border-color: rgba(110, 118, 247, 0.35) !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p {
    color: #8b92f8 !important;
    font-weight: 500 !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] [role="radio"] {
    margin-right: 8px !important;
}
[data-testid="stSidebar"] hr,
[data-testid="stSidebar"] [data-testid="stDivider"] {
    border-color: #21262d !important;
    margin: 16px 0 !important;
}
/* Sidebar progress list (markdown ✅ / ⬜ rows) */
[data-testid="stSidebar"] .ps-progress-row {
    display: flex; align-items: center; gap: 10px;
    padding: 6px 8px; border-radius: 6px;
    font-size: 12.5px;
}
[data-testid="stSidebar"] .ps-progress-row.done { color: #3fb950; }
[data-testid="stSidebar"] .ps-progress-row.pending { color: #6e7681; }
[data-testid="stSidebar"] .ps-progress-row .ps-progress-dot {
    width: 8px; height: 8px; border-radius: 50%;
    flex: 0 0 8px;
}
[data-testid="stSidebar"] .ps-progress-row.done .ps-progress-dot {
    background: #2ea043; box-shadow: 0 0 8px rgba(46,160,67,0.5);
}
[data-testid="stSidebar"] .ps-progress-row.pending .ps-progress-dot {
    background: #30363d;
}

/* ============================================================
   ST.EXPANDER — used for any sub-collapsibles still in the app
   Selector: [data-testid="stExpander"]
   ============================================================ */
/* Scope to inside the card body so we don't accidentally restyle
   the user's other expanders. */
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stExpander"] {
    background: #161b22 !important;
    border: 1px solid #21262d !important;
    border-radius: 10px !important;
    margin-bottom: 12px !important;
    overflow: hidden;
    transition: border-color 140ms ease, box-shadow 140ms ease;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stExpander"]:hover {
    border-color: #30363d !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stExpander"] summary,
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stExpander"] details > summary {
    padding: 12px 16px !important;
    background: transparent !important;
    border-radius: 10px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    color: #e6edf3 !important;
    list-style: none !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stExpander"] summary:hover {
    background: #1c2128 !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stExpander"] summary svg {
    fill: #6e7681 !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
    background: #1c2128 !important;
    padding: 16px !important;
    border-top: 1px solid #21262d !important;
}

/* ============================================================
   ST.DATAFRAME — SaaS-style clean data table
   Selector: [data-testid="stDataFrame"], .ps-table (HTML tables)
   ============================================================ */
/* Top-level dataframe container */
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stDataFrame"],
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stTable"] {
    border: 1px solid #21262d !important;
    border-radius: 10px !important;
    background: #0d1117 !important;
    overflow: hidden !important;
}

/* The Glide grid (Streamlit's native dataframe) */
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stDataFrame"] [data-testid="stDataFrameGlideDataEditor"] {
    background: #0d1117 !important;
    --gdg-bg-cell: #0d1117 !important;
    --gdg-bg-cell-medium: #161b22 !important;
    --gdg-bg-header: #161b22 !important;
    --gdg-bg-header-has-focus: #1c2128 !important;
    --gdg-bg-header-hovered: #1c2128 !important;
    --gdg-text-dark: #e6edf3 !important;
    --gdg-text-medium: #8b949e !important;
    --gdg-text-light: #6e7681 !important;
    --gdg-text-header: #8b949e !important;
    --gdg-border-color: #21262d !important;
    --gdg-horizontal-border-color: #21262d !important;
    --gdg-accent-color: #6e76f7 !important;
    --gdg-accent-light: rgba(110, 118, 247, 0.18) !important;
    --gdg-font-family: 'Inter', -apple-system, sans-serif !important;
    --gdg-base-font-style: 13px 'Inter' !important;
    --gdg-header-font-style: 600 11px 'Inter' !important;
}

/* HTML-rendered tables (df.to_html with .ps-table) */
.psychstats-shell .ps-table,
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) table {
    width: 100% !important;
    border-collapse: collapse !important;
    background: #0d1117 !important;
    border: 1px solid #21262d !important;
    border-radius: 10px !important;
    overflow: hidden !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13px !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) table thead th {
    background: #161b22 !important;
    color: #8b949e !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 10.5px !important;
    font-weight: 600 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    text-align: left !important;
    padding: 10px 14px !important;
    border-bottom: 1px solid #21262d !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) table tbody td {
    color: #e6edf3 !important;
    padding: 10px 14px !important;
    border-bottom: 1px solid #21262d !important;
    font-variant-numeric: tabular-nums !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) table tbody tr:last-child td {
    border-bottom: none !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) table tbody tr:hover td {
    background: #161b22 !important;
}

/* ============================================================
   SEGMENTED CONTROL — for sub-nav inside the card body
   Built on top of st.radio(horizontal=True) with a marker class.
   ============================================================ */
[data-testid="stVerticalBlock"]:has(> div > .ps-segmented-anchor) > div:first-child {
    margin-bottom: 16px !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-segmented-anchor) [data-testid="stRadio"] > div {
    background: #0d1117 !important;
    border: 1px solid #21262d !important;
    border-radius: 999px !important;
    padding: 4px !important;
    gap: 0 !important;
    display: inline-flex !important;
    flex-direction: row !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-segmented-anchor) [data-testid="stRadio"] label {
    padding: 6px 16px !important;
    border-radius: 999px !important;
    margin: 0 !important;
    transition: background 120ms ease, color 120ms ease;
    cursor: pointer;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-segmented-anchor) [data-testid="stRadio"] label:has(input:checked) {
    background: #6e76f7 !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-segmented-anchor) [data-testid="stRadio"] label:has(input:checked) p {
    color: #ffffff !important;
    font-weight: 600 !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-segmented-anchor) [data-testid="stRadio"] label p {
    color: #8b949e !important;
    font-size: 12.5px !important;
    margin: 0 !important;
}
/* Hide the actual radio input dot */
[data-testid="stVerticalBlock"]:has(> div > .ps-segmented-anchor) [data-testid="stRadio"] [role="radio"] {
    display: none !important;
}

/* ============================================================
   ALERTS — st.info / st.success / st.warning / st.error
   ============================================================ */
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stAlert"] {
    border-radius: 8px !important;
    border: none !important;
    border-left: 3px solid !important;
    padding: 12px 16px !important;
    font-size: 13px !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stAlert"][kind="info"]    { background:#0c1929 !important; border-left-color:#388bfd !important; color:#58a6ff !important; }
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stAlert"][kind="success"] { background:#0d2818 !important; border-left-color:#2ea043 !important; color:#3fb950 !important; }
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stAlert"][kind="warning"] { background:#2b1f06 !important; border-left-color:#d4a843 !important; color:#e3b341 !important; }
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stAlert"][kind="error"]   { background:#2d1117 !important; border-left-color:#f85149 !important; color:#ff7b72 !important; }

/* ============================================================
   FILE UPLOADER — st.file_uploader
   ============================================================ */
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stFileUploader"] section {
    background: #0d1117 !important;
    border: 1.5px dashed #30363d !important;
    border-radius: 10px !important;
    padding: 18px !important;
    transition: border-color 140ms ease, background 140ms ease;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stFileUploader"] section:hover {
    border-color: #6e76f7 !important;
    background: rgba(110, 118, 247, 0.04) !important;
}

/* Translate uploader button label (Streamlit renders "Upload" in some builds). */
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"] {
    position: relative !important;
    font-size: 0 !important; /* hide "Upload" without killing the icon */
    line-height: 0 !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"] * {
    font-size: 0 !important;
    line-height: 0 !important;
    color: transparent !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"] svg,
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"] svg * {
    font-size: initial !important;
    line-height: initial !important;
    color: #e6edf3 !important; /* keep icon visible */
    fill: currentColor !important;
    stroke: currentColor !important;
}
[data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) [data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"]::after {
    content: "Yükle" !important;
    position: absolute !important;
    left: 50% !important;
    top: 50% !important;
    transform: translate(-35%, -50%) !important; /* bias right to clear icon */
    color: #e6edf3 !important;
    font-size: 13px !important;
    line-height: 1 !important;
    font-weight: 600 !important;
    pointer-events: none !important;
}

/* --- Responsive --- */
@media (max-width: 820px) {
    .psychstats-shell .ps-step-label { display: none; }
    .psychstats-shell .ps-step-eyebrow { font-size: 9px; }
    .psychstats-shell .ps-card-head { padding: 20px 20px 14px; }
    [data-testid="stVerticalBlock"]:has(> div > .ps-card-body-anchor) {
        padding: 16px 20px 22px !important;
    }
}
"""


# ---------------------------------------------------------------------------
# CSS injection — idempotent (only fires once per session)
# ---------------------------------------------------------------------------

_INJECTED_FLAG = "_psychstats_layout_css_injected"


def inject_layout_css() -> None:
    """
    Inject the layout CSS into the page.

    IMPORTANT — fire on EVERY rerun, not just once.
    Streamlit reconciles the DOM on each script run; a <style> tag emitted
    once and not re-emitted on the next run gets removed, which is why the
    stepper/card collapse to raw vertical text after a file upload or any
    other widget interaction. We unconditionally re-emit the block; the
    browser deduplicates identical inline <style> content, so the cost is
    effectively zero.
    """
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# HTML builders
# ---------------------------------------------------------------------------

def _stepper_html(steps: Iterable[Step], active_step: int) -> str:
    """Render the 5-up horizontal stepper as HTML."""
    steps = list(steps)
    count = len(steps)
    parts: list[str] = [f'<nav class="ps-stepper" style="--ps-step-count:{count}" aria-label="Analiz adımları">']
    for i, step in enumerate(steps, start=1):
        # active_step (1-indexed) overrides the dataclass state on that index
        state = step.state
        if i == active_step:
            state = "active"
        eyebrow_state = {
            "complete": "Tamamlandı",
            "active":   "Aktif",
            "locked":   "",
        }[state]
        eyebrow = f"Adım {i:02d}" + (f" · {eyebrow_state}" if eyebrow_state else "")
        parts.append(
            f'<div class="ps-step {state}">'
            f'  <span class="ps-step-marker"><span class="ps-num">{i}</span></span>'
            f'  <div class="ps-step-body">'
            f'    <p class="ps-step-eyebrow">{eyebrow}</p>'
            f'    <p class="ps-step-label">{_esc(step.label)}</p>'
            f'  </div>'
            f'</div>'
        )
    parts.append("</nav>")
    return "".join(parts)


def _header_html(page_title: str, page_subtitle: str, meta: Optional[str]) -> str:
    meta_html = ""
    if meta:
        meta_html = (
            f'<div class="ps-meta">'
            f'  <span class="ps-meta-dot"></span>'
            f'  <span>{_esc(meta)}</span>'
            f'</div>'
        )
    return (
        f'<header class="ps-header">'
        f'  <div>'
        f'    <h1 class="ps-title">{_esc(page_title)}</h1>'
        f'    <p class="ps-subtitle">{_esc(page_subtitle)}</p>'
        f'  </div>'
        f'  {meta_html}'
        f'</header>'
    )


def _card_head_html(title: str, subtitle: str, step_pill: str) -> str:
    return (
        f'<div class="ps-card-head">'
        f'  <div class="ps-card-head-row">'
        f'    <div class="ps-card-head-left">'
        f'      <span class="ps-card-step-pill">{_esc(step_pill)}</span>'
        f'      <div>'
        f'        <h2 class="ps-card-title">{_esc(title)}</h2>'
        f'        <p class="ps-card-subtitle">{_esc(subtitle)}</p>'
        f'      </div>'
        f'    </div>'
        f'  </div>'
        f'</div>'
    )


def _esc(s: str) -> str:
    """Minimal HTML escape — keep Turkish chars intact."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# Public API — open_step_shell / close_step_shell
# ---------------------------------------------------------------------------

def open_step_shell(
    steps: Iterable[Step],
    active_step: int,
    title: str,
    subtitle: str = "",
    page_title: str = "PsychStats — Tez Analiz Aracı",
    page_subtitle: Optional[str] = None,
    meta: Optional[str] = None,
):
    """
    Render the page header, horizontal stepper, and card head.
    Returns a ``st.container`` representing the card body — use it with a
    ``with`` block so your widgets render inside the card visually:

        body = open_step_shell(STEPS, active_step=3, title="Ters Puanlama")
        with body:
            st.number_input("Min", value=1)
            st.button("Uygula")
        close_step_shell()

    Parameters
    ----------
    steps        : list of Step entries; their ``state`` is used as-is unless
                   overridden by ``active_step`` (1-indexed).
    active_step  : 1-indexed index of the active step. Forces ``state="active"``
                   on that step regardless of what was passed in.
    title        : Card title shown above the widgets.
    subtitle     : Optional one-line description shown under the title.
    page_title   : Top page heading (default: "PsychStats — Tez Analiz Aracı").
    page_subtitle: Subline under the page title. Defaults to "Adım N / total".
    meta         : Optional right-aligned status text (e.g. "N = 203 yüklendi").
    """
    inject_layout_css()
    steps = list(steps)
    total = len(steps)

    if page_subtitle is None:
        page_subtitle = f"Adım {active_step} / {total}"

    step_pill = f"Adım {active_step:02d} · Aktif"

    # 1. Shell wrapper open + header + stepper + card head
    html = (
        '<div class="psychstats-shell">'
        + _header_html(page_title, page_subtitle, meta)
        + _stepper_html(steps, active_step)
        + _card_head_html(title, subtitle, step_pill)
        + '</div>'  # close .psychstats-shell — card body is rendered by Streamlit next
    )
    st.markdown(html, unsafe_allow_html=True)

    # 2. Card body — a REAL st.container so widget event listeners are intact.
    #    The anchor element triggers our :has() CSS rules.
    body = st.container()
    body.markdown('<div class="ps-card-body-anchor"></div>', unsafe_allow_html=True)
    return body


def close_step_shell(
    helper_text: str = "İpucu: değişiklikler otomatik olarak kaydedilir.",
    primary_label: Optional[str] = None,
    primary_key: str = "ps_primary_action",
    secondary_label: Optional[str] = None,
    secondary_key: str = "ps_secondary_action",
) -> dict:
    """
    Render the card footer (helper text + optional primary/secondary buttons).

    Returns a dict with the click states of the buttons:
        {"primary": bool, "secondary": bool}

    The buttons themselves are real ``st.button`` widgets, so they participate
    in Streamlit's normal callback/rerun lifecycle.
    """
    # Footer container — also a real st.container, so the buttons inside
    # are real widgets we can return state from.
    footer = st.container()
    footer.markdown(
        f'<div class="psychstats-shell-footer-anchor"></div>'
        f'<div class="psychstats-shell-footer">'
        f'  <span class="ps-helper">{_esc(helper_text)}</span>'
        f'  <div class="ps-footer-buttons" id="ps-footer-buttons-target"></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    clicked = {"primary": False, "secondary": False}
    if secondary_label or primary_label:
        cols = footer.columns([6, 2, 2])
        with cols[1]:
            if secondary_label:
                clicked["secondary"] = st.button(secondary_label, key=secondary_key, type="secondary")
        with cols[2]:
            if primary_label:
                clicked["primary"] = st.button(primary_label, key=primary_key, type="primary")

    return clicked


# ---------------------------------------------------------------------------
# Convenience: context manager form (preferred for cleanliness)
# ---------------------------------------------------------------------------

from contextlib import contextmanager


@contextmanager
def step_shell(
    steps: Iterable[Step],
    active_step: int,
    title: str,
    subtitle: str = "",
    page_title: str = "PsychStats — Tez Analiz Aracı",
    page_subtitle: Optional[str] = None,
    meta: Optional[str] = None,
    helper_text: str = "İpucu: değişiklikler otomatik olarak kaydedilir.",
    primary_label: Optional[str] = None,
    secondary_label: Optional[str] = None,
):
    """
    Context-manager form. Yields the card body container AND a `actions` dict
    that the caller can read AFTER the `with` block to learn whether the
    primary/secondary buttons were clicked.

    Example:
        with step_shell(STEPS, 3, "Ters Puanlama",
                        primary_label="Uygula →") as (body, actions):
            with body:
                st.number_input("Min", value=1)
        if actions["primary"]:
            run_reverse_scoring()
    """
    body = open_step_shell(
        steps=steps,
        active_step=active_step,
        title=title,
        subtitle=subtitle,
        page_title=page_title,
        page_subtitle=page_subtitle,
        meta=meta,
    )
    actions: dict = {"primary": False, "secondary": False}
    try:
        yield body, actions
    finally:
        result = close_step_shell(
            helper_text=helper_text,
            primary_label=primary_label,
            secondary_label=secondary_label,
        )
        actions.update(result)


# ---------------------------------------------------------------------------
# Segmented control — pill sub-nav for inside the card (Step 5 analysis tabs)
# ---------------------------------------------------------------------------

def segmented_control(
    label: str,
    options: list[str],
    key: str,
    default: Optional[str] = None,
) -> str:
    """
    Render a horizontal pill-style segmented control. Wraps st.radio with an
    anchor div so our CSS targets ONLY this instance (not other radios).
    Returns the selected option.

    Use inside a card body for sub-navigation between related views.
    """
    # Anchor goes in its own container — that's what our :has() selector keys off.
    box = st.container()
    box.markdown('<div class="ps-segmented-anchor"></div>', unsafe_allow_html=True)
    with box:
        if default is not None and key not in st.session_state:
            st.session_state[key] = default
        choice = st.radio(
            label, options=options, key=key,
            horizontal=True, label_visibility="collapsed",
        )
    return choice


# ---------------------------------------------------------------------------
# Sidebar progress widget — colored dots + labels
# ---------------------------------------------------------------------------

def render_sidebar_progress(items: list[tuple[str, bool]]) -> None:
    """
    Render a list of (label, done_bool) rows in the sidebar as colored progress
    dots. Pure HTML — no widgets, no event listeners involved.
    """
    rows = []
    for label, done in items:
        state = "done" if done else "pending"
        rows.append(
            f'<div class="ps-progress-row {state}">'
            f'  <span class="ps-progress-dot"></span>'
            f'  <span>{_esc(label)}</span>'
            f'</div>'
        )
    st.sidebar.markdown("".join(rows), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Minimal smoke-test stub (only runs if module is the Streamlit entrypoint)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    st.set_page_config(page_title="PsychStats Layout Demo", layout="wide")

    STEPS = [
        Step("Dosya Yükleme",            "complete"),
        Step("Sütun ve Ölçek Atama",     "complete"),
        Step("Ters Puanlama",            "active"),
        Step("Bileşik Puan Oluşturucu",  "locked"),
        Step("Analiz ve Raporlama",      "locked"),
    ]

    body = open_step_shell(
        STEPS,
        active_step=3,
        title="Ters Puanlama",
        subtitle="Negatif yönde puanlanmış maddeleri ölçek aralığına göre çevir.",
        meta="N = 203 · 47 sütun yüklendi",
    )

    with body:
        c1, c2 = st.columns(2)
        with c1:
            st.number_input("Ölçek minimum", value=1, key="demo_min")
        with c2:
            st.number_input("Ölçek maksimum", value=5, key="demo_max")
        st.multiselect(
            "Ters puanlanacak maddeler",
            options=[f"CBMO_{i}" for i in range(1, 24)],
            default=["CBMO_3", "CBMO_7", "CBMO_15"],
            key="demo_items",
        )
        st.radio("Yöntem", ["Toplam", "Ortalama"], horizontal=True, key="demo_method")

    actions = close_step_shell(
        primary_label="Ters puanlamayı uygula →",
        secondary_label="Atla",
    )
    if actions["primary"]:
        st.success("Ters puanlama uygulandı.")
