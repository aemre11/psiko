"""
PsychStats Design System — psychstats_theme.py
===============================================
Complete dark-mode theme for the PsychStats Streamlit app.
Visual direction: Linear / Vercel / Raycast — professional, minimalist, student-friendly.

QUICK START
-----------
    import streamlit as st
    from psychstats_theme import inject_css, apply_psychstats_theme, metric_card, result_container

    st.set_page_config(page_title="PsychStats", page_icon="🧬", layout="wide")
    inject_css()   # ← call once, at the very top

    # Metric cards
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(metric_card("Cronbach's α", ".847", delta="+.03"), unsafe_allow_html=True)

    # Result container
    table_html = df.to_html(classes="ps-table", border=0, index=False)
    st.markdown(result_container("📊", "Betimleyici İstatistikler", table_html), unsafe_allow_html=True)

    # Matplotlib
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(groups, means, color="#6e76f7")
    apply_psychstats_theme(fig, ax, title="Grup Ortalamaları", xlabel="Grup", ylabel="Puan")
    st.pyplot(fig)
"""

import matplotlib as mpl
import matplotlib.pyplot as plt


# ============================================================
# 1. DESIGN TOKENS  (Python constants for use in code)
# ============================================================

COLORS = {
    # ── Backgrounds ──────────────────────────────────────────
    "bg":               "#0d1117",   # page background
    "bg_sidebar":       "#161b22",   # sidebar
    "surface":          "#1c2128",   # cards, expanders
    "surface_elevated": "#22272e",   # hover state, table headers

    # ── Accent (indigo — matches Inter/Linear palette) ───────
    "accent":           "#6e76f7",
    "accent_hover":     "#8b92f8",
    "accent_dark":      "#5558d9",
    "accent_subtle":    "rgba(110, 118, 247, 0.12)",

    # ── Semantic — Success ───────────────────────────────────
    "success":          "#2ea043",
    "success_bg":       "#0d2818",
    "success_border":   "#1a4226",
    "success_text":     "#3fb950",

    # ── Semantic — Warning ───────────────────────────────────
    "warning":          "#d4a843",
    "warning_bg":       "#2b1f06",
    "warning_border":   "#4a3310",
    "warning_text":     "#e3b341",

    # ── Semantic — Error ─────────────────────────────────────
    "error":            "#f85149",
    "error_bg":         "#2d1117",
    "error_border":     "#4a1c1a",
    "error_text":       "#ff7b72",

    # ── Semantic — Info ──────────────────────────────────────
    "info":             "#388bfd",
    "info_bg":          "#0c1929",
    "info_border":      "#1a3a5c",
    "info_text":        "#58a6ff",

    # ── Text ─────────────────────────────────────────────────
    "text_primary":     "#e6edf3",
    "text_secondary":   "#8b949e",
    "text_muted":       "#6e7681",
    "text_inverse":     "#0d1117",

    # ── Borders ──────────────────────────────────────────────
    "border":           "#30363d",
    "border_subtle":    "#21262d",
    "border_strong":    "#8b949e",

    # ── Step states ──────────────────────────────────────────
    "step_active":      "#d4a843",
    "step_active_bg":   "#2b1f06",
    "step_complete":    "#2ea043",
    "step_complete_bg": "#0d2818",
    "step_locked":      "#6e7681",
    "step_locked_bg":   "#1c2128",
}

TYPOGRAPHY = {
    "font_sans": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    "font_mono": "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",

    # Size scale (rem / px equivalent at 16px root)
    "size_display": "2.5rem",     # 40px — page hero
    "size_h1":      "1.875rem",   # 30px
    "size_h2":      "1.375rem",   # 22px
    "size_h3":      "1.125rem",   # 18px
    "size_body":    "0.9375rem",  # 15px
    "size_small":   "0.8125rem",  # 13px
    "size_caption": "0.6875rem",  # 11px

    # Weight scale
    "weight_regular":  "400",
    "weight_medium":   "500",
    "weight_semibold": "600",
    "weight_bold":     "700",
}

SPACING = {
    # 8px grid
    "xs":  "4px",
    "sm":  "8px",
    "md":  "12px",
    "lg":  "16px",
    "xl":  "24px",
    "2xl": "32px",
    "3xl": "48px",
    "4xl": "64px",

    "card_padding":  "24px",
    "section_gap":   "32px",
    "container_max": "900px",

    # Border radius
    "radius_sm":   "4px",
    "radius_md":   "8px",
    "radius_lg":   "12px",
    "radius_pill": "999px",
}


# ============================================================
# 2. MATPLOTLIB / SEABORN THEME
# ============================================================

#: Drop-in rcParams dict — apply with mpl.rcParams.update(PSYCHSTATS_RC_PARAMS)
PSYCHSTATS_RC_PARAMS: dict = {
    # Figure
    "figure.facecolor":    "#0d1117",
    "figure.edgecolor":    "#0d1117",
    "figure.dpi":          120,
    "figure.autolayout":   False,

    # Axes
    "axes.facecolor":      "#1c2128",
    "axes.edgecolor":      "#30363d",
    "axes.labelcolor":     "#e6edf3",
    "axes.titlecolor":     "#e6edf3",
    "axes.titlesize":      13,
    "axes.titleweight":    "600",
    "axes.titlepad":       12,
    "axes.labelsize":      11,
    "axes.labelpad":       8,
    "axes.spines.top":     False,
    "axes.spines.right":   False,
    "axes.spines.left":    True,
    "axes.spines.bottom":  True,
    "axes.grid":           True,
    "axes.axisbelow":      True,

    # Grid
    "grid.color":          "#21262d",
    "grid.linewidth":      0.8,
    "grid.alpha":          1.0,
    "grid.linestyle":      "--",

    # Ticks
    "xtick.color":         "#8b949e",
    "ytick.color":         "#8b949e",
    "xtick.labelsize":     10,
    "ytick.labelsize":     10,
    "xtick.major.pad":     6,
    "ytick.major.pad":     6,
    "xtick.major.size":    4,
    "ytick.major.size":    4,
    "xtick.minor.visible": False,
    "ytick.minor.visible": False,

    # Lines & patches
    "lines.linewidth":     2.0,
    "lines.solid_capstyle":"round",
    "patch.linewidth":     0.5,
    "patch.edgecolor":     "#0d1117",

    # Legend
    "legend.facecolor":    "#22272e",
    "legend.edgecolor":    "#30363d",
    "legend.labelcolor":   "#e6edf3",
    "legend.fontsize":     10,
    "legend.framealpha":   1.0,
    "legend.borderpad":    0.6,
    "legend.labelspacing": 0.4,

    # Font
    "font.family":         "sans-serif",
    "font.sans-serif":     ["Inter", "DejaVu Sans", "Liberation Sans", "Arial"],
    "font.size":           11,

    # Color cycle
    "axes.prop_cycle": mpl.cycler(color=[
        "#6e76f7",  # accent indigo
        "#2ea043",  # success green
        "#d4a843",  # warm gold
        "#388bfd",  # info blue
        "#f85149",  # error red/coral
        "#8b92f8",  # accent light
        "#3fb950",  # bright green
        "#e3b341",  # amber
    ]),
}


def apply_psychstats_theme(
    fig,
    ax,
    title: str = None,
    xlabel: str = None,
    ylabel: str = None,
    tight: bool = True,
) -> "plt.Figure":
    """
    Apply the PsychStats dark dashboard theme to a matplotlib figure.

    Call this AFTER creating your plot, BEFORE st.pyplot(fig).

    Parameters
    ----------
    fig   : matplotlib Figure
    ax    : matplotlib Axes or list/array of Axes (for subplots)
    title : Optional title string — styled automatically
    xlabel: Optional x-axis label
    ylabel: Optional y-axis label
    tight : Whether to call fig.tight_layout() (default True)

    Returns
    -------
    fig   : The styled Figure object

    Example
    -------
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(categories, values, color="#6e76f7", alpha=0.85)
        apply_psychstats_theme(fig, ax, title="Grup Ortalamaları", xlabel="Grup", ylabel="Puan")
        st.pyplot(fig)
        plt.close(fig)  # always close to free memory

    Seaborn usage
    -------------
        import seaborn as sns
        with mpl.rc_context(PSYCHSTATS_RC_PARAMS):
            fig, ax = plt.subplots(figsize=(8, 5))
            sns.boxplot(data=df, x="group", y="score", ax=ax,
                        palette=["#6e76f7", "#2ea043", "#d4a843"])
            apply_psychstats_theme(fig, ax, title="Gruplar Arası Dağılım")
            st.pyplot(fig)
    """
    # Normalize to list
    if hasattr(ax, "__iter__"):
        axes = list(ax.flat) if hasattr(ax, "flat") else list(ax)
    else:
        axes = [ax]

    # Figure background
    fig.patch.set_facecolor("#0d1117")
    fig.patch.set_alpha(1.0)

    for a in axes:
        # Axes background
        a.set_facecolor("#1c2128")

        # Spines
        for spine_name, spine in a.spines.items():
            if spine_name in ("top", "right"):
                spine.set_visible(False)
            else:
                spine.set_color("#30363d")
                spine.set_linewidth(0.8)

        # Ticks
        a.tick_params(colors="#8b949e", which="both", length=4, width=0.8)
        a.xaxis.label.set_color("#8b949e")
        a.yaxis.label.set_color("#8b949e")
        a.xaxis.label.set_fontsize(11)
        a.yaxis.label.set_fontsize(11)

        # Grid
        a.set_axisbelow(True)
        a.grid(True, color="#21262d", linewidth=0.8, linestyle="--", alpha=1.0)

        # Optional labels
        if title is not None:
            a.set_title(title, color="#e6edf3", fontsize=13, fontweight="600", pad=12)
        if xlabel is not None:
            a.set_xlabel(xlabel, color="#8b949e", fontsize=11, labelpad=8)
        if ylabel is not None:
            a.set_ylabel(ylabel, color="#8b949e", fontsize=11, labelpad=8)

        # Tick label colors
        for label in a.get_xticklabels() + a.get_yticklabels():
            label.set_color("#8b949e")

        # Legend (if present)
        legend = a.get_legend()
        if legend is not None:
            legend.get_frame().set_facecolor("#22272e")
            legend.get_frame().set_edgecolor("#30363d")
            legend.get_frame().set_linewidth(0.8)
            for text in legend.get_texts():
                text.set_color("#e6edf3")
                text.set_fontsize(10)

    if tight:
        fig.tight_layout(pad=1.5)

    return fig


# ============================================================
# 3. HTML COMPONENT TEMPLATES
# ============================================================

def metric_card(
    label: str,
    value: str,
    delta: str = None,
    delta_positive: bool = True,
    unit: str = None,
    width: str = "100%",
) -> str:
    """
    Metric card — displays a single statistic with label, value, and optional delta.

    Parameters
    ----------
    label          : Metric name  (e.g., "Cronbach's α")
    value          : Metric value (e.g., ".847")
    delta          : Optional change text (e.g., "+.03 from baseline") — shown below value
    delta_positive : True = green arrow ↑, False = red arrow ↓
    unit           : Optional unit appended to value in smaller muted text (e.g., "katılımcı")
    width          : CSS width of the card (default "100%" — fills column)

    Returns
    -------
    HTML string — pass to st.markdown(..., unsafe_allow_html=True)

    Example
    -------
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(metric_card("Cronbach's α", ".847", delta="+.03"), unsafe_allow_html=True)
        with col2:
            st.markdown(metric_card("Örneklem (N)", "203", unit="katılımcı"), unsafe_allow_html=True)
        with col3:
            st.markdown(metric_card("Ortalama", "3.72", delta="−.14", delta_positive=False), unsafe_allow_html=True)
        with col4:
            st.markdown(metric_card("p değeri", "< .001"), unsafe_allow_html=True)
    """
    delta_color = "#3fb950" if delta_positive else "#ff7b72"
    delta_arrow = "↑" if delta_positive else "↓"
    delta_html = (
        f'<div class="metric-delta" style="color:{delta_color}">'
        f'{delta_arrow} {delta}</div>'
        if delta else ""
    )
    unit_html = (
        f'<span style="font-size:0.875rem;color:#6e7681;font-weight:400;margin-left:4px;">'
        f'{unit}</span>'
        if unit else ""
    )

    return f"""
<div class="ps-metric-card" style="width:{width}">
  <div class="metric-label">{label}</div>
  <div class="metric-value">{value}{unit_html}</div>
  {delta_html}
</div>
"""


def result_container(
    icon: str,
    title: str,
    content_html: str,
    subtitle: str = None,
) -> str:
    """
    Section result container — card wrapper for analysis output sections.

    Parameters
    ----------
    icon         : Emoji or icon string (e.g., "📊", "🔗", "⚡", "📈")
    title        : Section heading  (e.g., "Betimleyici İstatistikler")
    content_html : Inner HTML for the body (tables, text, any HTML)
    subtitle     : Optional descriptor below the title  (e.g., "N = 120, M ± SS")

    Returns
    -------
    HTML string — pass to st.markdown(..., unsafe_allow_html=True)

    Example
    -------
        table_html = df.to_html(classes="ps-table", border=0, index=False)
        st.markdown(
            result_container(
                "📊", "Betimleyici İstatistikler", table_html,
                subtitle="N = 203, tüm ölçek değişkenleri için M ± SS"
            ),
            unsafe_allow_html=True
        )
    """
    subtitle_html = (
        f'<div class="result-subtitle">{subtitle}</div>' if subtitle else ""
    )

    return f"""
<div class="ps-result-container">
  <div class="result-header">
    <span class="result-icon">{icon}</span>
    <div class="result-title-group">
      <div class="result-title">{title}</div>
      {subtitle_html}
    </div>
  </div>
  <div class="result-body">
    {content_html}
  </div>
</div>
"""


def apa_note(text: str) -> str:
    """
    APA narrative note block — monospaced, left accent border.

    Ideal for displaying auto-generated APA 7 write-up sentences.

    Example
    -------
        st.markdown(
            apa_note("Anksiyete ölçeğinin stres ölçeğiyle pozitif yönde ilişkili olduğu "
                     "bulunmuştur, r(201) = .54, p < .001, %95 GA [.44, .63]."),
            unsafe_allow_html=True
        )
    """
    return f'<div class="ps-apa-note">{text}</div>'


def info_box(text: str, icon: str = "ℹ️") -> str:
    """
    Info callout box — blue tint, suitable for tips and guidance.

    Example
    -------
        st.markdown(
            info_box("Reverse-coded maddeler ters puanlamadan önce kontrol edilmelidir."),
            unsafe_allow_html=True
        )
    """
    return f'<div class="ps-info-box"><span style="margin-right:8px;">{icon}</span>{text}</div>'


def progress_tracker(steps: list[dict]) -> str:
    """
    Sidebar progress tracker — colored dot checklist.

    Parameters
    ----------
    steps : list of dicts with keys:
        - "label"  : Step name
        - "state"  : "complete" | "active" | "locked"

    Returns
    -------
    HTML string

    Example
    -------
        steps = [
            {"label": "Veri Yükleme",      "state": "complete"},
            {"label": "Sütun Eşleştirme",  "state": "active"},
            {"label": "Ters Puanlama",      "state": "locked"},
            {"label": "Kompozit Oluşturma","state": "locked"},
        ]
        st.sidebar.markdown(progress_tracker(steps), unsafe_allow_html=True)
    """
    icon_map = {"complete": "✓", "active": "●", "locked": "○"}
    items_html = ""
    for step in steps:
        state = step.get("state", "locked")
        label = step.get("label", "")
        icon = icon_map.get(state, "○")
        items_html += f"""
  <li class="ps-progress-item {state}">
    <span class="ps-progress-dot"></span>
    <span>{label}</span>
  </li>"""

    return f'<ul class="ps-progress-list">{items_html}\n</ul>'


def badge(text: str, variant: str = "accent") -> str:
    """
    Inline badge/chip — for status labels, tags, etc.

    Parameters
    ----------
    text    : Badge text
    variant : "accent" | "success" | "warning" | "error"

    Example
    -------
        st.markdown(badge("Tamamlandı", "success") + " " + badge("α > .70", "accent"),
                    unsafe_allow_html=True)
    """
    return f'<span class="ps-badge ps-badge-{variant}">{text}</span>'


# ============================================================
# 4. GLOBAL CSS
# ============================================================

_PSYCHSTATS_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
@import url('https://fonts.googleapis.com/icon?family=Material+Icons');

/* Streamlit uses Material Icons; keep icons from rendering as plain text. */
.material-icons,
.material-icons-outlined,
.material-icons-round,
.material-icons-sharp,
.material-icons-two-tone {
    font-family: 'Material Icons' !important;
    font-weight: normal !important;
    font-style: normal !important;
    text-transform: none !important;
    letter-spacing: normal !important;
    line-height: 1 !important;
    white-space: nowrap !important;
    direction: ltr !important;
}

/* ============================================================
   DESIGN TOKENS
   ============================================================ */
:root {
    /* — Backgrounds — */
    --color-bg:               #0d1117;
    --color-bg-sidebar:       #161b22;
    --color-surface:          #1c2128;
    --color-surface-elevated: #22272e;

    /* — Accent — */
    --color-accent:           #6e76f7;
    --color-accent-hover:     #8b92f8;
    --color-accent-dark:      #5558d9;
    --color-accent-subtle:    rgba(110, 118, 247, 0.12);

    /* — Success — */
    --color-success:          #2ea043;
    --color-success-bg:       #0d2818;
    --color-success-border:   #1a4226;
    --color-success-text:     #3fb950;

    /* — Warning — */
    --color-warning:          #d4a843;
    --color-warning-bg:       #2b1f06;
    --color-warning-border:   #4a3310;
    --color-warning-text:     #e3b341;

    /* — Error — */
    --color-error:            #f85149;
    --color-error-bg:         #2d1117;
    --color-error-border:     #4a1c1a;
    --color-error-text:       #ff7b72;

    /* — Info — */
    --color-info:             #388bfd;
    --color-info-bg:          #0c1929;
    --color-info-border:      #1a3a5c;
    --color-info-text:        #58a6ff;

    /* — Text — */
    --color-text-primary:     #e6edf3;
    --color-text-secondary:   #8b949e;
    --color-text-muted:       #6e7681;
    --color-text-inverse:     #0d1117;

    /* — Borders — */
    --color-border:           #30363d;
    --color-border-subtle:    #21262d;
    --color-border-strong:    #8b949e;

    /* — Step states — */
    --color-step-active:      #d4a843;
    --color-step-active-bg:   rgba(212, 168, 67, 0.06);
    --color-step-complete:    #2ea043;
    --color-step-complete-bg: rgba(46, 160, 67, 0.06);
    --color-step-locked:      #6e7681;
    --color-step-locked-bg:   #1c2128;

    /* — Typography — */
    --font-sans:   'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --font-mono:   'JetBrains Mono', 'Fira Code', monospace;

    --text-display: 2.5rem;
    --text-h1:      1.875rem;
    --text-h2:      1.375rem;
    --text-h3:      1.125rem;
    --text-body:    0.9375rem;
    --text-small:   0.8125rem;
    --text-caption: 0.6875rem;

    --weight-regular:  400;
    --weight-medium:   500;
    --weight-semibold: 600;
    --weight-bold:     700;

    --lh-tight:   1.25;
    --lh-snug:    1.375;
    --lh-normal:  1.5;
    --lh-relaxed: 1.625;

    /* — Spacing (8px grid) — */
    --space-xs:  4px;
    --space-sm:  8px;
    --space-md:  12px;
    --space-lg:  16px;
    --space-xl:  24px;
    --space-2xl: 32px;
    --space-3xl: 48px;
    --space-4xl: 64px;

    --card-padding:  24px;
    --section-gap:   32px;
    --container-max: 900px;

    /* — Border radius — */
    --radius-sm:   4px;
    --radius-md:   8px;
    --radius-lg:   12px;
    --radius-pill: 999px;

    /* — Shadows — */
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.3);
    --shadow-md: 0 4px 12px rgba(0,0,0,0.5), 0 2px 4px rgba(0,0,0,0.3);
    --shadow-lg: 0 8px 24px rgba(0,0,0,0.6), 0 4px 8px rgba(0,0,0,0.4);

    /* — Transitions — */
    --t-fast:   150ms ease;
    --t-normal: 250ms ease;
}


/* ============================================================
   GLOBAL RESET & BASE
   ============================================================ */

.stApp {
    background-color: var(--color-bg) !important;
    font-family: var(--font-sans) !important;
    color: var(--color-text-primary) !important;
}

.main .block-container {
    max-width: var(--container-max);
    padding: var(--space-2xl) var(--space-xl) var(--space-4xl);
    background-color: var(--color-bg) !important;
}

.stApp p, .stApp li {
    color: var(--color-text-primary);
    font-family: var(--font-sans);
    font-size: var(--text-body);
    line-height: var(--lh-relaxed);
}

/* Remove Streamlit's default red focus outlines */
*:focus {
    outline: none !important;
}

/* Scrollbar (webkit) */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--color-bg); }
::-webkit-scrollbar-thumb { background: var(--color-border); border-radius: var(--radius-pill); }
::-webkit-scrollbar-thumb:hover { background: var(--color-border-strong); }


/* ============================================================
   TYPOGRAPHY
   ============================================================ */

.stApp h1 {
    font-size: var(--text-h1) !important;
    font-weight: var(--weight-bold) !important;
    color: var(--color-text-primary) !important;
    letter-spacing: -0.025em !important;
    line-height: var(--lh-tight) !important;
    margin-bottom: var(--space-sm) !important;
}

.stApp h2 {
    font-size: var(--text-h2) !important;
    font-weight: var(--weight-semibold) !important;
    color: var(--color-text-primary) !important;
    letter-spacing: -0.015em !important;
    line-height: var(--lh-snug) !important;
    margin-bottom: var(--space-sm) !important;
}

.stApp h3 {
    font-size: var(--text-h3) !important;
    font-weight: var(--weight-semibold) !important;
    color: var(--color-text-primary) !important;
    letter-spacing: -0.01em !important;
    line-height: var(--lh-snug) !important;
    margin-bottom: var(--space-xs) !important;
}

/* Utility text classes */
.ps-caption {
    font-size: var(--text-caption);
    color: var(--color-text-muted);
    line-height: var(--lh-normal);
    letter-spacing: 0.02em;
    font-family: var(--font-sans);
}
.ps-small {
    font-size: var(--text-small);
    color: var(--color-text-secondary);
    line-height: var(--lh-normal);
    font-family: var(--font-sans);
}
.ps-label {
    font-size: var(--text-caption);
    font-weight: var(--weight-semibold);
    color: var(--color-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-family: var(--font-sans);
}


/* ============================================================
   SIDEBAR
   ============================================================ */

[data-testid="stSidebar"] {
    background-color: var(--color-bg-sidebar) !important;
    border-right: 1px solid var(--color-border-subtle) !important;
}

[data-testid="stSidebar"] > div:first-child {
    background-color: var(--color-bg-sidebar) !important;
    padding: var(--space-xl) var(--space-lg) !important;
}

[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span {
    color: var(--color-text-secondary) !important;
    font-size: var(--text-small) !important;
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: var(--color-text-primary) !important;
}

[data-testid="stSidebar"] hr {
    border-color: var(--color-border-subtle) !important;
    margin: var(--space-lg) 0 !important;
}


/* ============================================================
   SIDEBAR NAVIGATION  —  Radio (step navigation)
   ============================================================ */

[data-testid="stSidebar"] [data-testid="stRadio"] > div {
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
}

[data-testid="stSidebar"] [data-testid="stRadio"] label {
    display: flex !important;
    align-items: center !important;
    padding: var(--space-sm) var(--space-md) !important;
    border-radius: var(--radius-md) !important;
    cursor: pointer !important;
    transition: background-color var(--t-fast), color var(--t-fast) !important;
    font-size: var(--text-small) !important;
    font-weight: var(--weight-medium) !important;
    color: var(--color-text-secondary) !important;
}

[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background-color: rgba(255,255,255,0.05) !important;
    color: var(--color-text-primary) !important;
}

/* Active item — highlight with accent */
[data-testid="stSidebar"] [data-testid="stRadio"] [aria-checked="true"] ~ label,
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input[type="radio"]:checked) {
    background-color: var(--color-accent-subtle) !important;
    color: var(--color-accent-hover) !important;
    font-weight: var(--weight-semibold) !important;
}

/* Hide native radio circle */
[data-testid="stSidebar"] [data-testid="stRadio"] input[type="radio"] {
    accent-color: var(--color-accent) !important;
}


/* ============================================================
   PROGRESS TRACKER  (sidebar mini-checklist)
   Use progress_tracker() helper to generate HTML
   ============================================================ */

.ps-progress-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 0;
    margin: 0;
    list-style: none;
}

.ps-progress-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 5px var(--space-sm);
    border-radius: var(--radius-sm);
    font-size: var(--text-small);
    color: var(--color-text-muted);
    font-family: var(--font-sans);
    transition: color var(--t-fast);
}

.ps-progress-item.complete { color: var(--color-success-text); }
.ps-progress-item.active   { color: var(--color-text-primary); font-weight: var(--weight-medium); }
.ps-progress-item.locked   { color: var(--color-text-muted); opacity: 0.6; }

.ps-progress-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
    background: var(--color-border);
    transition: background-color var(--t-fast), box-shadow var(--t-fast);
}

.ps-progress-item.complete .ps-progress-dot {
    background: var(--color-success);
    box-shadow: 0 0 6px rgba(46, 160, 67, 0.5);
}
.ps-progress-item.active .ps-progress-dot {
    background: var(--color-accent);
    box-shadow: 0 0 6px rgba(110, 118, 247, 0.5);
}
.ps-progress-item.locked .ps-progress-dot {
    background: var(--color-step-locked);
    opacity: 0.35;
}


/* ============================================================
   STEP EXPANDER CARDS
   State classes: wrap expander in <div class="step-active|step-complete">
   ============================================================ */

[data-testid="stExpander"] {
    background-color: var(--color-surface) !important;
    border: 1px solid var(--color-border-subtle) !important;
    border-left: 3px solid var(--color-step-locked) !important;
    border-radius: var(--radius-lg) !important;
    margin-bottom: var(--space-lg) !important;
    overflow: hidden !important;
    transition: border-color var(--t-normal),
                background-color var(--t-normal),
                box-shadow var(--t-normal) !important;
}

[data-testid="stExpander"]:hover {
    background-color: var(--color-surface-elevated) !important;
    box-shadow: var(--shadow-sm) !important;
}

/* Expander header row */
[data-testid="stExpander"] summary,
[data-testid="stExpander"] [data-testid="stExpanderToggleIcon"] {
    padding: var(--space-lg) var(--space-xl) !important;
    color: var(--color-text-primary) !important;
    font-weight: var(--weight-medium) !important;
    font-size: var(--text-body) !important;
    font-family: var(--font-sans) !important;
}

/* Content area */
[data-testid="stExpander"] > div > div:last-child {
    padding: 0 var(--space-xl) var(--space-xl) !important;
    border-top: 1px solid var(--color-border-subtle) !important;
    padding-top: var(--space-lg) !important;
}

/* ACTIVE state  (gold — current step) */
.step-active [data-testid="stExpander"] {
    border-left-color: var(--color-step-active) !important;
    background-color: var(--color-step-active-bg) !important;
}
.step-active [data-testid="stExpander"]:hover {
    background-color: rgba(212, 168, 67, 0.09) !important;
    box-shadow: 0 4px 16px rgba(212, 168, 67, 0.12) !important;
}

/* COMPLETE state  (green — done) */
.step-complete [data-testid="stExpander"] {
    border-left-color: var(--color-step-complete) !important;
    background-color: var(--color-step-complete-bg) !important;
}
.step-complete [data-testid="stExpander"]:hover {
    background-color: rgba(46, 160, 67, 0.09) !important;
    box-shadow: 0 4px 16px rgba(46, 160, 67, 0.12) !important;
}

/* LOCKED state  (default gray — future steps, no extra class needed) */


/* ============================================================
   BUTTONS
   ============================================================ */

/* Primary — pill, filled, accent */
.stButton > button {
    background: var(--color-accent) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: var(--radius-pill) !important;
    padding: 10px 24px !important;
    font-family: var(--font-sans) !important;
    font-size: var(--text-small) !important;
    font-weight: var(--weight-semibold) !important;
    letter-spacing: 0.01em !important;
    cursor: pointer !important;
    transition: transform var(--t-fast),
                box-shadow var(--t-fast),
                background-color var(--t-fast) !important;
    box-shadow: 0 2px 8px rgba(110, 118, 247, 0.30) !important;
}

.stButton > button:hover {
    background: var(--color-accent-hover) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 16px rgba(110, 118, 247, 0.42) !important;
}

.stButton > button:active {
    transform: translateY(0) !important;
    box-shadow: 0 1px 4px rgba(110, 118, 247, 0.28) !important;
}

.stButton > button:disabled {
    background: var(--color-surface-elevated) !important;
    color: var(--color-text-muted) !important;
    box-shadow: none !important;
    cursor: not-allowed !important;
    transform: none !important;
}

/* Secondary / ghost — outlined */
.stButton > button[kind="secondary"],
.stButton > button.secondary {
    background: transparent !important;
    color: var(--color-accent) !important;
    border: 1.5px solid var(--color-accent) !important;
    box-shadow: none !important;
}

.stButton > button[kind="secondary"]:hover,
.stButton > button.secondary:hover {
    background: var(--color-accent-subtle) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(110, 118, 247, 0.18) !important;
}


/* ============================================================
   ALERTS
   ============================================================ */

/* Base: remove Streamlit default styling */
[data-testid="stAlert"] {
    border-radius: var(--radius-md) !important;
    border-width: 1px !important;
    border-style: solid !important;
    border-left-width: 3px !important;
    padding: var(--space-lg) var(--space-xl) !important;
    font-family: var(--font-sans) !important;
}

[data-testid="stAlert"] p {
    font-size: var(--text-small) !important;
    line-height: var(--lh-relaxed) !important;
    margin: 0 !important;
}

/* Success */
[data-testid="stAlert"][data-type="success"],
div.stAlert.success {
    background-color: var(--color-success-bg) !important;
    border-color: var(--color-success-border) !important;
    border-left-color: var(--color-success) !important;
    color: var(--color-success-text) !important;
}

/* Warning */
[data-testid="stAlert"][data-type="warning"],
div.stAlert.warning {
    background-color: var(--color-warning-bg) !important;
    border-color: var(--color-warning-border) !important;
    border-left-color: var(--color-warning) !important;
    color: var(--color-warning-text) !important;
}

/* Error */
[data-testid="stAlert"][data-type="error"],
div.stAlert.error {
    background-color: var(--color-error-bg) !important;
    border-color: var(--color-error-border) !important;
    border-left-color: var(--color-error) !important;
    color: var(--color-error-text) !important;
}

/* Info */
[data-testid="stAlert"][data-type="info"],
div.stAlert.info {
    background-color: var(--color-info-bg) !important;
    border-color: var(--color-info-border) !important;
    border-left-color: var(--color-info) !important;
    color: var(--color-info-text) !important;
}

/* Fallback: style all alerts with info palette (Streamlit sometimes omits data-type) */
[data-testid="stAlert"] {
    background-color: var(--color-info-bg) !important;
    border-color: var(--color-info-border) !important;
    border-left-color: var(--color-info) !important;
}


/* ============================================================
   APA NARRATIVE TEXT AREA
   ============================================================ */

[data-testid="stTextArea"] textarea {
    background-color: var(--color-surface) !important;
    color: var(--color-text-primary) !important;
    font-family: var(--font-mono) !important;
    font-size: var(--text-small) !important;
    line-height: 1.75 !important;
    border: 1px solid var(--color-border) !important;
    border-left: 3px solid var(--color-accent) !important;
    border-radius: var(--radius-md) !important;
    padding: var(--space-lg) !important;
    transition: border-color var(--t-normal),
                box-shadow var(--t-normal) !important;
    resize: vertical !important;
    caret-color: var(--color-accent) !important;
}

[data-testid="stTextArea"] textarea:focus {
    border-color: var(--color-accent) !important;
    border-left-color: var(--color-accent-hover) !important;
    box-shadow: 0 0 0 3px rgba(110, 118, 247, 0.15),
                inset 0 1px 3px rgba(0,0,0,0.2) !important;
}

[data-testid="stTextArea"] textarea::placeholder {
    color: var(--color-text-muted) !important;
}

[data-testid="stTextArea"] label {
    color: var(--color-text-secondary) !important;
    font-size: var(--text-small) !important;
    font-weight: var(--weight-medium) !important;
}


/* ============================================================
   OTHER FORM INPUTS
   ============================================================ */

/* Text / Number inputs */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
    background-color: var(--color-surface) !important;
    color: var(--color-text-primary) !important;
    border: 1px solid var(--color-border) !important;
    border-radius: var(--radius-md) !important;
    font-family: var(--font-sans) !important;
    font-size: var(--text-body) !important;
    transition: border-color var(--t-fast), box-shadow var(--t-fast) !important;
    caret-color: var(--color-accent) !important;
}

[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus {
    border-color: var(--color-accent) !important;
    box-shadow: 0 0 0 3px rgba(110, 118, 247, 0.15) !important;
}

/* Select / Multiselect */
[data-testid="stSelectbox"] > div > div,
[data-testid="stMultiSelect"] > div > div {
    background-color: var(--color-surface) !important;
    border-color: var(--color-border) !important;
    color: var(--color-text-primary) !important;
    border-radius: var(--radius-md) !important;
}

/* All form labels */
[data-testid="stTextInput"] label,
[data-testid="stSelectbox"] label,
[data-testid="stMultiSelect"] label,
[data-testid="stNumberInput"] label,
[data-testid="stSlider"] label,
[data-testid="stCheckbox"] label {
    color: var(--color-text-secondary) !important;
    font-size: var(--text-small) !important;
    font-weight: var(--weight-medium) !important;
    font-family: var(--font-sans) !important;
}

/* Checkbox */
[data-testid="stCheckbox"] {
    accent-color: var(--color-accent);
}


/* ============================================================
   METRIC CARDS  (custom HTML — use metric_card())
   ============================================================ */

.ps-metric-card {
    background-color: var(--color-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: var(--radius-lg);
    padding: var(--card-padding);
    font-family: var(--font-sans);
    transition: border-color var(--t-fast), box-shadow var(--t-fast);
    box-sizing: border-box;
}

.ps-metric-card:hover {
    border-color: var(--color-border);
    box-shadow: var(--shadow-sm);
}

.metric-label {
    font-size: var(--text-caption);
    font-weight: var(--weight-semibold);
    color: var(--color-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: var(--space-sm);
}

.metric-value {
    font-size: var(--text-h2);
    font-weight: var(--weight-semibold);
    color: var(--color-text-primary);
    line-height: 1;
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
}

.metric-delta {
    font-size: var(--text-caption);
    margin-top: var(--space-xs);
    font-weight: var(--weight-medium);
    letter-spacing: 0.01em;
}


/* ============================================================
   RESULT CONTAINERS  (custom HTML — use result_container())
   ============================================================ */

.ps-result-container {
    background-color: var(--color-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: var(--radius-lg);
    overflow: hidden;
    box-shadow: var(--shadow-sm);
    margin-bottom: var(--space-xl);
    font-family: var(--font-sans);
}

.result-header {
    display: flex;
    align-items: center;
    gap: var(--space-md);
    padding: var(--space-lg) var(--space-xl);
    border-bottom: 1px solid var(--color-border-subtle);
    background-color: var(--color-surface-elevated);
}

.result-icon {
    font-size: 1.25rem;
    line-height: 1;
    flex-shrink: 0;
}

.result-title-group {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.result-title {
    font-size: var(--text-h3);
    font-weight: var(--weight-semibold);
    color: var(--color-text-primary);
    line-height: var(--lh-tight);
}

.result-subtitle {
    font-size: var(--text-caption);
    color: var(--color-text-muted);
    line-height: var(--lh-normal);
}

.result-body {
    padding: var(--space-xl);
    color: var(--color-text-primary);
    font-size: var(--text-body);
    line-height: var(--lh-relaxed);
}

/* Table inside result containers */
.ps-result-container table,
table.ps-table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-small);
    font-family: var(--font-sans);
    color: var(--color-text-primary);
}

.ps-result-container th,
table.ps-table th {
    text-align: left;
    padding: var(--space-sm) var(--space-lg);
    border-bottom: 1px solid var(--color-border);
    font-weight: var(--weight-semibold);
    color: var(--color-text-secondary);
    font-size: var(--text-caption);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    background-color: var(--color-surface-elevated);
}

.ps-result-container td,
table.ps-table td {
    padding: var(--space-sm) var(--space-lg);
    border-bottom: 1px solid var(--color-border-subtle);
    color: var(--color-text-primary);
    font-variant-numeric: tabular-nums;
}

.ps-result-container tr:last-child td,
table.ps-table tr:last-child td { border-bottom: none; }

.ps-result-container tr:hover td,
table.ps-table tr:hover td { background-color: rgba(255,255,255,0.025); }


/* ============================================================
   STREAMLIT NATIVE OVERRIDES
   ============================================================ */

/* File uploader */
[data-testid="stFileUploader"] {
    border: 1.5px dashed var(--color-border) !important;
    border-radius: var(--radius-lg) !important;
    background-color: var(--color-surface) !important;
    transition: border-color var(--t-normal),
                background-color var(--t-normal) !important;
}

/* Translate uploader button label (Streamlit 1.57 uses stBaseButton-secondary). */
[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"] {
    position: relative !important;
    font-size: 0 !important;
    line-height: 0 !important;
}
[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"] * {
    font-size: 0 !important;
    line-height: 0 !important;
    color: transparent !important;
    -webkit-text-fill-color: transparent !important;
    text-shadow: none !important;
}
[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"] svg,
[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"] svg * {
    font-size: initial !important;
    line-height: initial !important;
    color: var(--color-text-primary) !important; /* keep icon visible */
    fill: currentColor !important;
    stroke: currentColor !important;
}
[data-testid="stFileUploader"] [data-testid="stBaseButton-secondary"]::after {
    content: "Yükle" !important;
    position: absolute !important;
    left: 50% !important;
    top: 50% !important;
    transform: translate(-35%, -50%) !important;
    color: var(--color-text-primary) !important;
    pointer-events: none !important;
    font-size: var(--text-small) !important;
    line-height: 1 !important;
    font-weight: var(--weight-semibold) !important;
}

[data-testid="stFileUploader"]:hover {
    border-color: var(--color-accent) !important;
    background-color: var(--color-accent-subtle) !important;
}

[data-testid="stFileUploader"] label {
    color: var(--color-text-secondary) !important;
    font-size: var(--text-small) !important;
}

/* Dataframe */
[data-testid="stDataFrame"] {
    border-radius: var(--radius-md) !important;
    overflow: hidden !important;
    border: 1px solid var(--color-border-subtle) !important;
}

/* Progress bar */
[data-testid="stProgress"] > div {
    background-color: var(--color-surface-elevated) !important;
    border-radius: var(--radius-pill) !important;
    height: 6px !important;
}

[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, var(--color-accent), var(--color-accent-hover)) !important;
    border-radius: var(--radius-pill) !important;
    transition: width 0.4s ease !important;
}

/* Tabs */
[data-testid="stTabs"] [role="tab"] {
    font-family: var(--font-sans) !important;
    font-size: var(--text-small) !important;
    font-weight: var(--weight-medium) !important;
    color: var(--color-text-secondary) !important;
    border-bottom: 2px solid transparent !important;
    padding: var(--space-sm) var(--space-lg) !important;
    transition: color var(--t-fast), border-color var(--t-fast) !important;
}

[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: var(--color-accent) !important;
    border-bottom-color: var(--color-accent) !important;
    font-weight: var(--weight-semibold) !important;
}

/* Divider */
hr {
    border: none !important;
    border-top: 1px solid var(--color-border-subtle) !important;
    margin: var(--space-xl) 0 !important;
}

/* Code */
code {
    background-color: var(--color-surface-elevated) !important;
    color: var(--color-accent-hover) !important;
    font-family: var(--font-mono) !important;
    font-size: 0.85em !important;
    padding: 2px 6px !important;
    border-radius: var(--radius-sm) !important;
    border: 1px solid var(--color-border-subtle) !important;
}

pre code {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    color: var(--color-text-primary) !important;
}

pre {
    background-color: var(--color-surface) !important;
    border: 1px solid var(--color-border-subtle) !important;
    border-radius: var(--radius-md) !important;
    padding: var(--space-lg) !important;
    overflow-x: auto !important;
}

/* Spinner */
[data-testid="stSpinner"] > div {
    border-top-color: var(--color-accent) !important;
}

/* Toast / notification */
[data-testid="stToast"] {
    background-color: var(--color-surface-elevated) !important;
    border: 1px solid var(--color-border) !important;
    border-radius: var(--radius-md) !important;
    color: var(--color-text-primary) !important;
    font-family: var(--font-sans) !important;
}


/* ============================================================
   UTILITY CLASSES
   ============================================================ */

/* Badges */
.ps-badge {
    display: inline-flex;
    align-items: center;
    padding: 2px 10px;
    border-radius: var(--radius-pill);
    font-size: var(--text-caption);
    font-weight: var(--weight-semibold);
    letter-spacing: 0.04em;
    font-family: var(--font-sans);
    line-height: 1.5;
}
.ps-badge-accent   { background: var(--color-accent-subtle);    color: var(--color-accent-hover); }
.ps-badge-success  { background: var(--color-success-bg);        color: var(--color-success-text); }
.ps-badge-warning  { background: var(--color-warning-bg);        color: var(--color-warning-text); }
.ps-badge-error    { background: var(--color-error-bg);          color: var(--color-error-text);   }

/* Inline stat highlight (for APA sentences) */
.ps-stat {
    font-family: var(--font-mono);
    font-size: 0.88em;
    color: var(--color-accent-hover);
    background: var(--color-accent-subtle);
    padding: 1px 6px;
    border-radius: var(--radius-sm);
}

/* Info / tip box */
.ps-info-box {
    background: var(--color-info-bg);
    border: 1px solid var(--color-info-border);
    border-left: 3px solid var(--color-info);
    border-radius: var(--radius-md);
    padding: var(--space-lg) var(--space-xl);
    font-size: var(--text-small);
    color: var(--color-text-primary);
    font-family: var(--font-sans);
    line-height: var(--lh-relaxed);
    margin-bottom: var(--space-lg);
}

/* APA note box */
.ps-apa-note {
    background: var(--color-surface);
    border-left: 3px solid var(--color-accent);
    border-radius: 0 var(--radius-md) var(--radius-md) 0;
    padding: var(--space-lg) var(--space-xl);
    font-family: var(--font-mono);
    font-size: var(--text-small);
    line-height: 1.8;
    color: var(--color-text-primary);
    margin-bottom: var(--space-lg);
}

/* Step number badge */
.ps-step-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    font-size: var(--text-caption);
    font-weight: var(--weight-bold);
    font-family: var(--font-sans);
    flex-shrink: 0;
}
.ps-step-badge.active   { background: var(--color-step-active-bg);   border: 1.5px solid var(--color-step-active);   color: var(--color-step-active);   }
.ps-step-badge.complete { background: var(--color-step-complete-bg); border: 1.5px solid var(--color-step-complete); color: var(--color-step-complete); }
.ps-step-badge.locked   { background: var(--color-step-locked-bg);   border: 1.5px solid var(--color-step-locked);   color: var(--color-step-locked);   opacity: 0.6; }

/* Divider with label */
.ps-divider {
    display: flex;
    align-items: center;
    gap: var(--space-lg);
    margin: var(--space-xl) 0;
    color: var(--color-text-muted);
    font-size: var(--text-caption);
    font-family: var(--font-sans);
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
.ps-divider::before,
.ps-divider::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--color-border-subtle);
}

/* Flex & spacing helpers */
.ps-flex     { display: flex; }
.ps-flex-col { display: flex; flex-direction: column; }
.ps-center   { align-items: center; }
.ps-gap-xs   { gap: var(--space-xs); }
.ps-gap-sm   { gap: var(--space-sm); }
.ps-gap-md   { gap: var(--space-lg); }
.ps-gap-lg   { gap: var(--space-xl); }
.ps-mt-sm    { margin-top: var(--space-sm); }
.ps-mt-md    { margin-top: var(--space-lg); }
.ps-mt-lg    { margin-top: var(--space-xl); }
.ps-mb-sm    { margin-bottom: var(--space-sm); }
.ps-mb-md    { margin-bottom: var(--space-lg); }
.ps-mb-lg    { margin-bottom: var(--space-xl); }
"""


# ============================================================
# 5. PUBLIC API
# ============================================================

def inject_css() -> None:
    """
    Inject the complete PsychStats CSS theme into Streamlit.

    Call this ONCE at the top of your main app file, before any other st.* calls.

    Example
    -------
        import streamlit as st
        from psychstats_theme import inject_css

        st.set_page_config(
            page_title="PsychStats",
            page_icon="🧬",
            layout="wide",
            initial_sidebar_state="expanded",
        )
        inject_css()
        # ... rest of your app
    """
    import streamlit as st  # local import so module works without streamlit installed
    st.markdown(f"<style>{_PSYCHSTATS_CSS}</style>", unsafe_allow_html=True)


# ============================================================
# DEMO  —  run this file directly to preview the system
#   streamlit run psychstats_theme.py
# ============================================================

if __name__ == "__main__":
    import numpy as np
    import streamlit as st

    st.set_page_config(
        page_title="PsychStats — Design Preview",
        page_icon="🎨",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_css()

    # ── Sidebar ──────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🧬 PsychStats")
        st.markdown('<hr>', unsafe_allow_html=True)
        st.markdown("**Analiz Adımları**")

        steps = [
            {"label": "Veri Yükleme",        "state": "complete"},
            {"label": "Sütun Eşleştirme",     "state": "complete"},
            {"label": "Ters Puanlama",         "state": "active"},
            {"label": "Kompozit Oluşturma",    "state": "locked"},
            {"label": "Betimleyici İstat.",    "state": "locked"},
            {"label": "Grup Karşılaştırması",  "state": "locked"},
            {"label": "Korelasyon",            "state": "locked"},
            {"label": "Moderasyon",            "state": "locked"},
            {"label": "Word Dışa Aktarma",     "state": "locked"},
        ]
        st.markdown(progress_tracker(steps), unsafe_allow_html=True)

        st.markdown('<hr>', unsafe_allow_html=True)
        st.markdown(badge("v1.0.0", "accent"), unsafe_allow_html=True)

    # ── Main content ─────────────────────────────────────────
    st.markdown("# PsychStats Design System")
    st.markdown('<p class="ps-small">Komponent kütüphanesi önizlemesi — karanlık mod</p>',
                unsafe_allow_html=True)
    st.markdown("---")

    # Metric cards
    st.markdown("## Metric Cards")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(metric_card("Cronbach's α", ".847", delta="+.03"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("Örneklem (N)", "203", unit="katılımcı"), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("Ortalama", "3.72", delta="−.14", delta_positive=False), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card("p değeri", "< .001"), unsafe_allow_html=True)

    st.markdown("---")

    # Result container
    st.markdown("## Result Container")
    table_html = """
    <table class="ps-table">
      <thead>
        <tr><th>Değişken</th><th>M</th><th>SS</th><th>Min</th><th>Max</th><th>α</th></tr>
      </thead>
      <tbody>
        <tr><td>Anksiyete</td><td>3.42</td><td>0.87</td><td>1.00</td><td>5.00</td><td>.83</td></tr>
        <tr><td>Stres</td><td>3.18</td><td>0.93</td><td>1.00</td><td>5.00</td><td>.79</td></tr>
        <tr><td>İyi Oluş</td><td>3.76</td><td>0.74</td><td>1.50</td><td>5.00</td><td>.88</td></tr>
        <tr><td>Öz-Yeterlik</td><td>3.91</td><td>0.68</td><td>2.00</td><td>5.00</td><td>.85</td></tr>
      </tbody>
    </table>
    """
    st.markdown(
        result_container("📊", "Betimleyici İstatistikler", table_html,
                         subtitle="N = 203, tüm ölçek değişkenleri için M ± SS"),
        unsafe_allow_html=True
    )

    st.markdown("---")

    # Alerts
    st.markdown("## Alerts")
    st.success("Analiz başarıyla tamamlandı. Composite değişkenler oluşturuldu.")
    st.warning("Ölçek normallik varsayımını karşılamıyor (Shapiro-Wilk p < .05). Non-parametrik testler önerilir.")
    st.error("Yüklenen dosyada zorunlu sütunlar bulunamadı. Lütfen veri formatını kontrol edin.")
    st.info("İpucu: Reverse-coded maddeler ters puanlamadan önce kontrol edilmelidir.")

    st.markdown("---")

    # Buttons
    st.markdown("## Buttons")
    bc1, bc2, bc3 = st.columns([1, 1, 4])
    with bc1:
        st.button("Analizi Çalıştır")
    with bc2:
        st.button("Sıfırla")

    st.markdown("---")

    # Step expanders
    st.markdown("## Step Expander Cards")

    st.markdown('<div class="step-complete">', unsafe_allow_html=True)
    with st.expander("✓  Adım 1 — Veri Yükleme  (tamamlandı)"):
        st.markdown("Veriler başarıyla yüklendi.")
        st.markdown(badge("203 satır", "success") + "  " + badge("24 sütun", "accent"),
                    unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="step-complete">', unsafe_allow_html=True)
    with st.expander("✓  Adım 2 — Sütun Eşleştirme  (tamamlandı)"):
        st.markdown("Tüm sütunlar eşleştirildi.")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="step-active">', unsafe_allow_html=True)
    with st.expander("3  Adım 3 — Ters Puanlama  ← Şu anda aktif"):
        st.markdown("Hangi maddelerin ters puanlanacağını seçin.")
        st.multiselect("Ters puanlanacak maddeler:", ["Q1", "Q3", "Q5", "Q7", "Q9"],
                        default=["Q3", "Q7"])
        st.button("Ters Puanlamayı Uygula")
    st.markdown('</div>', unsafe_allow_html=True)

    with st.expander("4  Adım 4 — Kompozit Oluşturma  (kilitli)"):
        st.markdown("Bu adım Adım 3 tamamlandığında açılacaktır.")

    st.markdown("---")

    # APA text area
    st.markdown("## APA Narrative Text Area")
    st.text_area(
        "APA 7 Yazım Çıktısı",
        value=(
            "Anksiyete ölçeğinin (M = 3.42, SS = 0.87) stres ölçeğiyle (M = 3.18, SS = 0.93) "
            "pozitif yönde ve anlamlı biçimde ilişkili olduğu bulunmuştur, "
            "r(201) = .54, p < .001, %95 GA [.44, .63]."
        ),
        height=120,
    )

    # APA note component
    st.markdown(
        apa_note(
            "Yüksek anksiyete puanları (M = 3.42, SS = 0.87) ile yüksek stres puanları "
            "(M = 3.18, SS = 0.93) arasında orta düzeyde pozitif bir ilişki "
            "saptanmıştır, r(201) = .54, p &lt; .001."
        ),
        unsafe_allow_html=True
    )

    st.markdown("---")

    # Matplotlib
    st.markdown("## Matplotlib Figures")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    # Bar chart
    groups = ["Kontrol", "Deney A", "Deney B"]
    means  = [3.12, 3.74, 3.91]
    errs   = [0.18, 0.14, 0.12]
    axes[0].bar(groups, means, color=["#6e76f7", "#2ea043", "#d4a843"],
                alpha=0.85, yerr=errs, capsize=5,
                error_kw={"ecolor": "#8b949e", "linewidth": 1.2})
    axes[0].set_ylim(2.5, 4.5)

    # Scatter
    np.random.seed(42)
    x_sc = np.random.normal(3.4, 0.8, 80)
    y_sc = x_sc * 0.54 + np.random.normal(0, 0.6, 80)
    axes[1].scatter(x_sc, y_sc, color="#6e76f7", alpha=0.55, s=30, edgecolors="none")
    m, b = np.polyfit(x_sc, y_sc, 1)
    x_line = np.linspace(x_sc.min(), x_sc.max(), 100)
    axes[1].plot(x_line, m * x_line + b, color="#d4a843", linewidth=2)

    apply_psychstats_theme(fig, axes[0], title="Grup Ortalamaları", xlabel="Grup", ylabel="Puan")
    apply_psychstats_theme(fig, axes[1], title="Korelasyon Saçılım Grafiği",
                           xlabel="Anksiyete", ylabel="Stres")
    st.pyplot(fig)
    plt.close(fig)

    st.markdown("---")

    # Info box
    st.markdown("## Utility Components")
    st.markdown(info_box("Ölçek güvenilirliği için Cronbach alfa değerinin .70'in üzerinde olması beklenmektedir."), unsafe_allow_html=True)

    # Badges
    st.markdown(
        badge("Tamamlandı", "success") + "  " +
        badge("Aktif", "accent") + "  " +
        badge("Uyarı", "warning") + "  " +
        badge("Hata", "error"),
        unsafe_allow_html=True
    )
