"""
Streamlit rules (PsychStats) — apply on every change in this module:
1. Never write to widget-backed session state key inside on_change — pending flag; consume before widgets.
2. Every rerun-surviving widget needs stable key= initialized at startup.
3. Never call st.rerun() inside a callback — flag + natural rerun (except pre-widget button handlers here).
4. Clear only downstream state keys, not upstream keys backing visible widgets.
5. Loop-rendered widgets use index-stable keys.
6. Always use .get(key, default) for nested dicts in session state.
7. Never store class instances in session state.
8. On file upload, unconditionally overwrite KEY_RAW_DF.
9. List item action buttons use stable unique ID keys, not positional index keys.
"""

import math

import pandas as pd
import streamlit as st
from scipy import stats

from modules.data_manager import KEY_COL_ROLES, KEY_COMPOSITE_CONFIG, KEY_FINAL_DF
from modules.descriptives import KEY_NORMALITY_RESULTS

from utils.formatters import (
    format_anova_narrative,
    format_ci,
    format_kruskal_narrative,
    format_mannwhitney_narrative,
    format_p,
    format_stat,
    format_ttest_narrative,
)

KEY_INFERENTIAL_DV_SELECT = "inferential_dv_select"
KEY_INFERENTIAL_IV_SELECT = "inferential_iv_select"
KEY_INFERENTIAL_RUN = "inferential_run"
KEY_INFERENTIAL_ALL_NARRATIVES = "inferential_all_narratives"
KEY_INFERENTIAL_RESULTS = "inferential_results"


def _get_col(row: pd.Series, *candidates: str):
    """Return first matching column from a pingouin result row (names vary by version)."""
    for c in candidates:
        if c in row.index:
            return row[c]
    raise KeyError(f"None of {candidates} found in {list(row.index)}")


def _pingouin_first_row(result: pd.DataFrame | pd.Series) -> pd.Series:
    if isinstance(result, pd.Series):
        return result
    return result.iloc[0]


def _parse_ci_bounds(ci_raw) -> tuple[float, float]:
    if isinstance(ci_raw, (list, tuple)):
        return float(ci_raw[0]), float(ci_raw[1])
    if hasattr(ci_raw, "__len__") and len(ci_raw) >= 2:
        return float(ci_raw[0]), float(ci_raw[1])
    raise ValueError(f"Unrecognized CI format: {ci_raw!r}")


def _init_inferential_state() -> None:
    defaults = {
        KEY_INFERENTIAL_DV_SELECT: [],
        KEY_INFERENTIAL_IV_SELECT: [],
        KEY_INFERENTIAL_RUN: False,
        KEY_INFERENTIAL_ALL_NARRATIVES: "",
        KEY_INFERENTIAL_RESULTS: [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _align_multiselect_state(key: str, allowed: list[str]) -> None:
    """Keep selection valid; never shrink the options= list passed to multiselect."""
    if not allowed:
        st.session_state[key] = []
        return
    current = st.session_state.get(key)
    if not isinstance(current, list):
        current = []
    st.session_state[key] = [x for x in current if x in allowed]


def _inferential_result_entry(
    test_type: str,
    dv_col: str,
    iv_col: str,
    group_desc_df: pd.DataFrame,
    test_df: pd.DataFrame,
    narrative_key: str,
    *,
    tukey_df: pd.DataFrame | None = None,
    nonparametric: dict | None = None,
    ttest_data: dict | None = None,
    anova_data: dict | None = None,
) -> dict:
    entry = {
        "type": test_type,
        "dv": dv_col,
        "iv": iv_col,
        "group_desc_df": group_desc_df,
        "test_df": test_df,
        "tukey_df": tukey_df,
        "nonparametric": nonparametric,
        "narrative_key": narrative_key,
    }
    if ttest_data is not None:
        entry["ttest_data"] = ttest_data
    if anova_data is not None:
        entry["anova_data"] = anova_data
    return entry


def _group_descriptives_table(df: pd.DataFrame, dv_col: str, iv_col: str) -> pd.DataFrame:
    clean = df[[dv_col, iv_col]].dropna()
    rows: list[dict] = []
    for group, sub in clean.groupby(iv_col, sort=True):
        values = sub[dv_col]
        n = int(values.count())
        if n == 0:
            continue
        mean = float(values.mean())
        sd = float(values.std(ddof=1)) if n > 1 else float("nan")
        se = float(sd / (n**0.5)) if n > 0 and pd.notna(sd) else float("nan")
        rows.append(
            {
                "Group": group,
                "N": n,
                "Mean": round(mean, 2),
                "SD": round(sd, 2) if pd.notna(sd) else "—",
                "SE": round(se, 2) if pd.notna(se) else "—",
            }
        )
    desc_df = pd.DataFrame(rows)
    return desc_df.rename(
        columns={
            "Group": "Grup",
            "Mean": "Ort",
            "SD": "SS",
            "SE": "SH",
            "N": "N",
        }
    )


def _run_ttest_block(
    df_clean: pd.DataFrame,
    dv_col: str,
    iv_col: str,
    groups: list,
    normality_entry: dict,
    group_desc_df: pd.DataFrame,
) -> dict:
    import pingouin as pg

    group_vals = df_clean.groupby(iv_col)[dv_col]
    g1, g2 = [group_vals.get_group(k).dropna() for k in groups]
    labels = [str(k) for k in groups]

    levene_stat, levene_p = stats.levene(g1, g2)
    use_welch = levene_p <= 0.05

    result_eq = pg.ttest(g1, g2, correction=False)
    result_welch = pg.ttest(g1, g2, correction=True)

    def _row_from_result(result: pd.DataFrame, assumption: str) -> dict:
        row = _pingouin_first_row(result)
        t_val = float(_get_col(row, "T", "t", "t-val"))
        df_val = float(_get_col(row, "dof", "df", "DF", "ddof"))
        p_val = float(_get_col(row, "p-val", "p_val", "pval", "p"))
        d_val = float(_get_col(row, "cohen-d", "cohen_d", "d"))
        ci_lo, ci_hi = _parse_ci_bounds(_get_col(row, "CI95%", "CI95", "ci95"))
        mean_diff = float(g1.mean() - g2.mean())
        return {
            "Varsayım": assumption,
            "Levene F": format_stat(float(levene_stat), 2),
            "Levene p": format_p(levene_p),
            "t": format_stat(t_val, 2),
            "df": format_stat(df_val, 2),
            "p": format_p(p_val),
            "Ort. Fark": format_stat(mean_diff, 2),
            "Cohen d": format_stat(d_val, 2),
            "95% GA": format_ci(ci_lo, ci_hi, 2),
            "_selected": use_welch if "varsayılmadı" in assumption else not use_welch,
        }

    row_eq = _row_from_result(result_eq, "Eşit varyans varsayıldı")
    row_welch = _row_from_result(result_welch, "Eşit varyans varsayılmadı")
    display = pd.DataFrame([row_eq, row_welch]).drop(columns="_selected")

    st.markdown("**Bağımsız örneklem t-testi**")
    st.caption(
        f"**Selected row:** {row_welch['Varsayım'] if use_welch else row_eq['Varsayım']} "
        f"(Levene p {format_p(levene_p)})"
    )
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.session_state[f"inferential_ttest_table_{iv_col}_{dv_col}"] = display

    active_row = _pingouin_first_row(result_welch if use_welch else result_eq)
    t = float(_get_col(active_row, "T", "t", "t-val"))
    df_t = float(_get_col(active_row, "dof", "df", "DF", "ddof"))
    p = float(_get_col(active_row, "p-val", "p_val", "pval", "p"))
    d = float(_get_col(active_row, "cohen-d", "cohen_d", "d"))

    narrative = format_ttest_narrative(
        dv_col,
        iv_col,
        labels,
        len(g1),
        len(g2),
        float(g1.mean()),
        float(g1.std(ddof=1)),
        float(g2.mean()),
        float(g2.std(ddof=1)),
        t,
        df_t,
        p,
        d,
        levene_p,
    )
    narrative_key = f"inferential_ttest_narrative_{iv_col}_{dv_col}"
    with st.expander("📝 Teze nasıl yazılır?", expanded=False):
        st.caption(
            "Aşağıdaki metni tezinizin bulgular bölümüne kopyalayabilirsiniz. "
            "Gerekirse düzenleyin. Etki büyüklüğü yorumu: d < .20 ihmal edilebilir, "
            ".20–.49 küçük, .50–.79 orta, ≥ .80 büyük (Cohen, 1988)."
        )
        st.text_area(
            "APA anlatısı",
            value=narrative,
            height=120,
            key=narrative_key,
        )
    nonparametric = None
    is_normal = normality_entry.get("normal", True)
    if not is_normal:
        with st.expander("Non-parametric alternative", expanded=True):
            u_stat, p_mw = stats.mannwhitneyu(g1, g2, alternative="two-sided")
            # r = Z/√N etki büyüklüğü için Z, U istatistiğinden normal yaklaşımla
            # hesaplanır (SPSS ile aynı formül; p'nin süreklilik düzeltmesinden bağımsız).
            n1_mw, n2_mw = len(g1), len(g2)
            mu_mw = n1_mw * n2_mw / 2
            sigma_mw = math.sqrt(n1_mw * n2_mw * (n1_mw + n2_mw + 1) / 12)
            z_mw = (float(u_stat) - mu_mw) / sigma_mw if sigma_mw > 0 else 0.0
            mw_text = format_mannwhitney_narrative(
                dv_col,
                labels,
                n1_mw,
                n2_mw,
                float(g1.median()),
                float(g2.median()),
                float(u_stat),
                float(p_mw),
                z=abs(z_mw),
            )
            st.write(mw_text)
            nonparametric = {"summary": mw_text}

    ttest_data = {
        "var_name": dv_col,
        "group_var": iv_col,
        "group_labels": labels,
        "n1": len(g1),
        "n2": len(g2),
        "mean1": float(g1.mean()),
        "sd1": float(g1.std(ddof=1)),
        "mean2": float(g2.mean()),
        "sd2": float(g2.std(ddof=1)),
        "t": t,
        "df": df_t,
        "p": p,
        "d": d,
        "levene_p": float(levene_p),
    }

    return _inferential_result_entry(
        "ttest",
        dv_col,
        iv_col,
        group_desc_df,
        display,
        narrative_key,
        tukey_df=None,
        nonparametric=nonparametric,
        ttest_data=ttest_data,
    )


def _run_anova_block(
    df_clean: pd.DataFrame,
    dv_col: str,
    iv_col: str,
    normality_entry: dict,
    group_desc_df: pd.DataFrame,
) -> dict | None:
    import pingouin as pg

    aov = pg.anova(data=df_clean, dv=dv_col, between=iv_col, detailed=True)

    source_col = "Source" if "Source" in aov.columns else "source"
    between_rows = aov.loc[aov[source_col] == iv_col]
    within_rows = aov.loc[aov[source_col] == "Within"]
    if between_rows.empty:
        st.warning(f"ANOVA table missing between-groups row for {iv_col}.")
        return None
    if within_rows.empty:
        st.warning("ANOVA table missing Within-groups row.")
        return None

    between_row = between_rows.iloc[0]
    within_row = within_rows.iloc[0]

    ss_between = float(_get_col(between_row, "SS", "ss"))
    ss_within = float(_get_col(within_row, "SS", "ss"))
    ss_total = ss_between + ss_within

    df_between = int(_get_col(between_row, "ddof1", "DF", "df", "DF1"))
    df_within = float(_get_col(within_row, "ddof1", "DF", "df", "DF2"))
    df_total = df_between + int(df_within)

    F = float(_get_col(between_row, "F", "f"))
    p = float(_get_col(between_row, "p-unc", "p_unc", "pval", "p"))
    eta2 = float(_get_col(between_row, "np2", "eta2", "eta-sq", "eta_sq"))
    ms_between = ss_between / df_between if df_between else 0.0
    ms_within = ss_within / df_within if df_within else 0.0
    k_groups = df_clean[iv_col].nunique()

    anova_display = pd.DataFrame(
        [
            {
                "Source": iv_col,
                "SS": f"{ss_between:.2f}",
                "df": df_between,
                "MS": f"{ms_between:.2f}",
                "F": format_stat(F, 3),
                "p": format_p(p),
                "η²": format_stat(eta2, 3),
            },
            {
                "Source": "Within",
                "SS": f"{ss_within:.2f}",
                "df": int(df_within),
                "MS": f"{ms_within:.2f}",
                "F": "—",
                "p": "—",
                "η²": "—",
            },
            {
                "Source": "Total",
                "SS": f"{ss_total:.2f}",
                "df": df_total,
                "MS": "—",
                "F": "—",
                "p": "—",
                "η²": "—",
            },
        ]
    )

    st.markdown("**Tek yönlü ANOVA**")
    aov_display = aov.copy()

    # Rename columns — handle both pingouin column name variants
    aov_display = aov_display.rename(
        columns={
            "Source": "Kaynak",
            "SS": "KT",
            "df": "sd",
            "DF": "sd",
            "MS": "KO",
            "F": "F",
            "p-unc": "p",
            "p_unc": "p",
            "np2": "η²",
            "eta2": "η²",
        }
    )

    # Translate row values in the source column
    source_col = "Kaynak" if "Kaynak" in aov_display.columns else "Source"
    aov_display[source_col] = aov_display[source_col].replace(
        {
            "Within": "Grup İçi",
            "Total": "Toplam",
            iv_col: iv_col,
        }
    )

    for col, fmt in [
        ("F", lambda x: f"{x:.2f}" if pd.notna(x) else "—"),
        ("p", lambda x: format_p(float(x)) if pd.notna(x) else "—"),
        ("η²", lambda x: format_stat(float(x), 3) if pd.notna(x) else "—"),
        ("KT", lambda x: f"{x:.4f}" if pd.notna(x) else "—"),
        ("KO", lambda x: f"{x:.4f}" if pd.notna(x) else "—"),
    ]:
        if col in aov_display.columns:
            aov_display[col] = aov_display[col].apply(fmt)

    aov_display = aov_display.fillna("—").replace({None: "—", "None": "—"})
    st.dataframe(aov_display, use_container_width=True, hide_index=True)
    st.session_state[f"inferential_anova_table_{iv_col}_{dv_col}"] = anova_display

    tukey_display = None
    tukey_raw = None
    if p < 0.05:
        tukey_raw = pg.pairwise_tukey(data=df_clean, dv=dv_col, between=iv_col)
        tukey_rows = []
        for _, row in tukey_raw.iterrows():
            p_tukey = float(_get_col(row, "p-tukey", "p_tukey", "pval", "p"))
            tukey_rows.append(
                {
                    "Group A": _get_col(row, "A", "a"),
                    "Group B": _get_col(row, "B", "b"),
                    "Mean Diff": format_stat(float(_get_col(row, "diff", "mean_diff")), 2),
                    "SE": format_stat(float(_get_col(row, "se", "SE")), 2),
                    "t": format_stat(float(_get_col(row, "T", "t")), 2),
                    "p (Tukey)": format_p(p_tukey),
                    "Significant": "✓" if p_tukey < 0.05 else "",
                }
            )
        st.markdown("**Tukey HSD post-hoc comparisons**")
        tukey_display = pd.DataFrame(tukey_rows)
        st.dataframe(tukey_display, use_container_width=True, hide_index=True)
    st.session_state[f"inferential_tukey_{iv_col}_{dv_col}"] = tukey_display

    narrative = format_anova_narrative(
        dv_col,
        iv_col,
        k_groups,
        F,
        df_between,
        df_within,
        p,
        eta2,
        tukey_results=tukey_raw,
    )
    narrative_key = f"inferential_anova_narrative_{iv_col}_{dv_col}"
    with st.expander("📝 Teze nasıl yazılır?", expanded=False):
        st.caption(
            "Aşağıdaki metni tezinizin bulgular bölümüne kopyalayabilirsiniz. "
            "Gerekirse düzenleyin. Etki büyüklüğü yorumu: η² < .01 ihmal edilebilir, "
            ".01–.05 küçük, .06–.13 orta, ≥ .14 büyük (Cohen, 1988)."
        )
        st.text_area(
            "APA anlatısı",
            value=narrative,
            height=120,
            key=narrative_key,
        )

    nonparametric = None
    is_normal = normality_entry.get("normal", True)
    if not is_normal:
        with st.expander("Non-parametric alternative", expanded=True):
            group_series = [
                df_clean.loc[df_clean[iv_col] == g, dv_col].dropna()
                for g in sorted(df_clean[iv_col].unique())
            ]
            h_stat, p_kw = stats.kruskal(*group_series)
            df_kw = len(group_series) - 1
            n_total_kw = int(sum(len(s) for s in group_series))
            # ε² = H/(N−1) etki büyüklüğü, η² eşikleriyle etiketlenir (Tomczak & Tomczak, 2014 yaklaşımı).
            kw_text = format_kruskal_narrative(
                dv_col,
                iv_col,
                len(group_series),
                float(h_stat),
                df_kw,
                float(p_kw),
                n_total=n_total_kw,
            )
            st.write(kw_text)
            nonparametric = {"summary": kw_text}

    anova_data = {
        "var_name": dv_col,
        "group_var": iv_col,
        "k_groups": k_groups,
        "F": F,
        "df_between": df_between,
        "df_within": df_within,
        "p": p,
        "eta2": eta2,
    }

    return _inferential_result_entry(
        "anova",
        dv_col,
        iv_col,
        group_desc_df,
        anova_display,
        narrative_key,
        tukey_df=tukey_display,
        nonparametric=nonparametric,
        anova_data=anova_data,
    )


def _narrative_text_from_entry(entry: dict) -> str:
    """Build APA narrative from stored result entry (no session state)."""
    test_type = entry.get("type", "")
    ttest_data = entry.get("ttest_data") or {}
    anova_data = entry.get("anova_data") or {}

    if test_type == "ttest" and ttest_data:
        return format_ttest_narrative(
            ttest_data["var_name"],
            ttest_data["group_var"],
            ttest_data["group_labels"],
            ttest_data["n1"],
            ttest_data["n2"],
            ttest_data["mean1"],
            ttest_data["sd1"],
            ttest_data["mean2"],
            ttest_data["sd2"],
            ttest_data["t"],
            ttest_data["df"],
            ttest_data["p"],
            ttest_data["d"],
            ttest_data["levene_p"],
        )

    if test_type in ("anova", "nonparametric") and anova_data:
        return format_anova_narrative(
            anova_data["var_name"],
            anova_data["group_var"],
            anova_data["k_groups"],
            anova_data["F"],
            anova_data["df_between"],
            anova_data["df_within"],
            anova_data["p"],
            anova_data["eta2"],
        )

    if ttest_data:
        return format_ttest_narrative(
            ttest_data["var_name"],
            ttest_data["group_var"],
            ttest_data["group_labels"],
            ttest_data["n1"],
            ttest_data["n2"],
            ttest_data["mean1"],
            ttest_data["sd1"],
            ttest_data["mean2"],
            ttest_data["sd2"],
            ttest_data["t"],
            ttest_data["df"],
            ttest_data["p"],
            ttest_data["d"],
            ttest_data["levene_p"],
        )
    return ""


def _analyze_pair(
    final_df: pd.DataFrame,
    dv_col: str,
    iv_col: str,
    normality: dict,
) -> dict | None:
    df_clean = final_df[[dv_col, iv_col]].dropna()
    if df_clean.empty:
        st.info(f"No valid cases for {iv_col} × {dv_col} after listwise deletion.")
        return None

    normality_entry = normality.get(dv_col, {})
    is_normal = normality_entry.get("normal", None)
    sw_p = normality_entry.get("sw_p", normality_entry.get("p", None))
    sw_stat = normality_entry.get("sw_stat", normality_entry.get("W", None))

    if is_normal is None:
        st.info(
            f"ℹ️ **{dv_col}** için normallik bilgisi bulunamadı. "
            "Önce Betimsel İstatistikler sayfasını ziyaret edin."
        )
    elif is_normal:
        st.success(
            f"✅ **{dv_col}** normal dağılım göstermektedir "
            f"(Shapiro-Wilk W = {format_stat(sw_stat, 3) if sw_stat is not None else '—'}, "
            f"p {format_p(sw_p) if sw_p is not None else '—'}). "
            "Parametrik test uygulanmaktadır."
        )
    else:
        st.warning(
            f"⚠️ **{dv_col}** normal dağılım göstermemektedir "
            f"(Shapiro-Wilk W = {format_stat(sw_stat, 3) if sw_stat is not None else '—'}, "
            f"p {format_p(sw_p) if sw_p is not None else '—'}). "
            "Parametrik olmayan test alternatifi aşağıda gösterilmektedir."
        )

    st.markdown("**Grup betimsel istatistikleri**")
    group_desc_df = _group_descriptives_table(final_df, dv_col, iv_col)
    st.dataframe(group_desc_df, use_container_width=True, hide_index=True)

    groups = sorted(df_clean[iv_col].dropna().unique())
    n_groups = len(groups)
    if n_groups < 2:
        st.info(f"Only one group found for {iv_col} — skipping.")
        return None

    if n_groups == 2:
        return _run_ttest_block(
            df_clean, dv_col, iv_col, groups, normality_entry, group_desc_df
        )

    return _run_anova_block(
        df_clean, dv_col, iv_col, normality_entry, group_desc_df
    )


def render():
    st.header("Grup Karşılaştırmaları")

    _init_inferential_state()

    final_df = st.session_state.get(KEY_FINAL_DF)
    if final_df is None:
        st.warning("Complete Module 1 preprocessing first.")
        return

    col_roles = st.session_state.get(KEY_COL_ROLES, {})
    composites = st.session_state.get(KEY_COMPOSITE_CONFIG, [])
    normality = st.session_state.get(KEY_NORMALITY_RESULTS, {})

    demographic_cols = [c for c in final_df.columns if col_roles.get(c) == "demographic"]
    composite_names = [
        c.get("name")
        for c in composites
        if isinstance(c, dict) and c.get("name") and c.get("name") in final_df.columns
    ]

    if not demographic_cols:
        st.info(
            "No demographic columns found in the final dataset. "
            "Mark columns as Demographic in Step 2 and rebuild composites."
        )
        return
    if not composite_names:
        st.info(
            "No composite scores found in the final dataset. "
            "Build composites in Step 4 before running group comparisons."
        )
        return

    _align_multiselect_state(KEY_INFERENTIAL_DV_SELECT, composite_names)
    _align_multiselect_state(KEY_INFERENTIAL_IV_SELECT, demographic_cols)

    dv_btn_col1, dv_btn_col2 = st.columns(2)
    with dv_btn_col1:
        if st.button("Tümünü Seç", key="inferential_dv_select_all"):
            st.session_state[KEY_INFERENTIAL_DV_SELECT] = list(composite_names)
            st.rerun()
    with dv_btn_col2:
        if st.button("Tümünü Temizle", key="inferential_dv_clear"):
            st.session_state[KEY_INFERENTIAL_DV_SELECT] = [composite_names[0]]
            st.rerun()

    selected_dvs = st.multiselect(
        "Analiz edilecek ölçek puanlarını seçin",
        options=list(composite_names),
        key=KEY_INFERENTIAL_DV_SELECT,
    )

    iv_btn_col1, iv_btn_col2 = st.columns(2)
    with iv_btn_col1:
        if st.button("Tümünü Seç", key="inferential_iv_select_all"):
            st.session_state[KEY_INFERENTIAL_IV_SELECT] = list(demographic_cols)
            st.rerun()
    with iv_btn_col2:
        if st.button("Tümünü Temizle", key="inferential_iv_clear"):
            st.session_state[KEY_INFERENTIAL_IV_SELECT] = [demographic_cols[0]]
            st.rerun()

    selected_ivs = st.multiselect(
        "Grup karşılaştırmaları için demografik değişkenleri seçin",
        options=list(demographic_cols),
        key=KEY_INFERENTIAL_IV_SELECT,
    )

    if st.button("Grup Karşılaştırmalarını Çalıştır", type="primary", key="run_group_comparisons"):
        st.session_state[KEY_INFERENTIAL_RUN] = True
        st.session_state[KEY_INFERENTIAL_RESULTS] = []

    if not st.session_state.get(KEY_INFERENTIAL_RUN):
        st.caption(
            "Yukarıdan değişkenleri seçin, ardından "
            "**Grup Karşılaştırmalarını Çalıştır**'a tıklayın."
        )
        return

    if not selected_dvs or not selected_ivs:
        st.warning("En az bir bağımlı değişken ve bir demografik değişken seçin.")
        return

    narratives: list[str] = []
    nonparam_by_pair: dict[tuple[str, str], dict | None] = {}

    for dv_col in selected_dvs:
        for iv_col in selected_ivs:
            with st.expander(f"{iv_col} × {dv_col}", expanded=True):
                analyzed = _analyze_pair(final_df, dv_col, iv_col, normality)
            if analyzed is None:
                continue
            nonparam_by_pair[(iv_col, dv_col)] = analyzed.get("nonparametric")
            narrative = _narrative_text_from_entry(analyzed)
            if narrative:
                narratives.append(f"## {iv_col} × {dv_col}\n\n{narrative}")

    results_list: list[dict] = []
    for iv_col in selected_ivs:
        for dv_col in selected_dvs:
            df_clean = final_df[[dv_col, iv_col]].dropna()
            if df_clean.empty:
                continue
            groups = sorted(df_clean[iv_col].dropna().unique())
            n_groups = len(groups)
            if n_groups < 2:
                continue

            group_desc = (
                final_df.groupby(iv_col)[dv_col]
                .agg(N="count", Ort="mean", SS="std")
                .reset_index()
                .rename(columns={iv_col: "Grup"})
                .round(2)
            )
            group_desc["SH"] = (group_desc["SS"] / group_desc["N"] ** 0.5).round(2)

            if n_groups == 2:
                test_type = "ttest"
                g1 = df_clean[df_clean[iv_col] == groups[0]][dv_col]
                g2 = df_clean[df_clean[iv_col] == groups[1]][dv_col]
                _, levene_p = stats.levene(g1, g2)
                t_res = stats.ttest_ind(g1, g2, equal_var=levene_p > 0.05)
                pooled_sd = ((g1.std(ddof=1) ** 2 + g2.std(ddof=1) ** 2) / 2) ** 0.5
                cohen_d = (g1.mean() - g2.mean()) / pooled_sd if pooled_sd else 0.0
                ttest_data = {
                    "var_name": dv_col,
                    "group_var": iv_col,
                    "group_labels": [str(groups[0]), str(groups[1])],
                    "n1": len(g1),
                    "n2": len(g2),
                    "mean1": float(g1.mean()),
                    "sd1": float(g1.std(ddof=1)),
                    "mean2": float(g2.mean()),
                    "sd2": float(g2.std(ddof=1)),
                    "t": float(t_res.statistic),
                    "df": float(
                        t_res.df
                        if hasattr(t_res, "df")
                        else len(g1) + len(g2) - 2
                    ),
                    "p": float(t_res.pvalue),
                    "d": float(cohen_d),
                    "levene_p": float(levene_p),
                }
                test_df = st.session_state.get(
                    f"inferential_ttest_table_{iv_col}_{dv_col}", pd.DataFrame()
                )
                results_list.append(
                    {
                        "type": test_type,
                        "dv": dv_col,
                        "iv": iv_col,
                        "group_desc_df": group_desc,
                        "test_df": test_df,
                        "tukey_df": None,
                        "nonparametric": nonparam_by_pair.get((iv_col, dv_col)),
                        "narrative_key": f"inferential_ttest_narrative_{iv_col}_{dv_col}",
                        "ttest_data": ttest_data,
                    }
                )
            else:
                import pingouin as pg

                test_type = "anova"
                aov = pg.anova(data=df_clean, dv=dv_col, between=iv_col, detailed=True)
                source_col = "Source" if "Source" in aov.columns else "source"
                b_row = aov.loc[aov[source_col] == iv_col].iloc[0]
                w_row = aov.loc[aov[source_col] == "Within"].iloc[0]
                F_val = float(b_row.get("F", 0))
                df_b = int(b_row.get("ddof1", b_row.get("DF", 1)))
                df_w = float(
                    w_row.get("ddof1", w_row.get("DF", len(df_clean) - n_groups))
                )
                p_val = float(b_row.get("p-unc", b_row.get("p_unc", 1)))
                eta2 = float(b_row.get("np2", b_row.get("eta2", b_row.get("η2", 0))))
                anova_data = {
                    "var_name": dv_col,
                    "group_var": iv_col,
                    "k_groups": n_groups,
                    "F": F_val,
                    "df_between": df_b,
                    "df_within": df_w,
                    "p": p_val,
                    "eta2": eta2,
                }
                test_df = st.session_state.get(
                    f"inferential_anova_table_{iv_col}_{dv_col}", pd.DataFrame()
                )
                tukey_df = st.session_state.get(
                    f"inferential_tukey_{iv_col}_{dv_col}", None
                )
                results_list.append(
                    {
                        "type": test_type,
                        "dv": dv_col,
                        "iv": iv_col,
                        "group_desc_df": group_desc,
                        "test_df": test_df,
                        "tukey_df": tukey_df,
                        "nonparametric": nonparam_by_pair.get((iv_col, dv_col)),
                        "narrative_key": f"inferential_anova_narrative_{iv_col}_{dv_col}",
                        "anova_data": anova_data,
                    }
                )

    st.session_state[KEY_INFERENTIAL_RESULTS] = results_list

    if narratives:
        all_text = "\n\n".join(narratives)
        st.session_state[KEY_INFERENTIAL_ALL_NARRATIVES] = all_text
        if st.button("📋 Tüm anlatıları kopyala", key="copy_all_inferential_narratives"):
            st.session_state[KEY_INFERENTIAL_ALL_NARRATIVES] = all_text
        st.text_area(
            "Tüm anlatılar (buradan kopyalayın)",
            value=st.session_state.get(KEY_INFERENTIAL_ALL_NARRATIVES, all_text),
            height=240,
            key="inferential_all_narratives_display",
        )
