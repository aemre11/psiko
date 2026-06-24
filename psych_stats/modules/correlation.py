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

import io
import re

import matplotlib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import statsmodels.api as sm
import streamlit as st
from scipy import stats
from statsmodels.stats.outliers_influence import variance_inflation_factor

from modules.data_manager import KEY_COL_ROLES, KEY_COMPOSITE_CONFIG, KEY_FINAL_DF
from utils.formatters import (
    format_ci,
    format_conditional_effects_narrative,
    format_correlation_narrative,
    format_moderation_narrative,
    format_p,
    format_stat,
)

KEY_NORMALITY_RESULTS = "normality_results"
KEY_CORRELATION_RUN = "correlation_run"
KEY_INCLUDE_SUBSCALES = "correlation_include_subscales"
KEY_MOD_X = "moderation_x"
KEY_MOD_Y = "moderation_y"
KEY_MOD_W = "moderation_w"
KEY_MOD_CONTROLS = "moderation_controls"
KEY_CORRELATION_PAIR_RESULTS = "correlation_pair_results"
KEY_CORRELATION_RESULTS = "correlation_results"
KEY_MODERATION_RESULTS = "moderation_results"
KEY_APA_NARRATIVE_MODERATION = "apa_narrative_moderation"
KEY_APA_NARRATIVE_CONDITIONAL = "apa_narrative_conditional"
KEY_CORRELATION_FIGURE = "correlation_figure_bytes"
KEY_MODERATION_FIGURE = "moderation_figure_bytes"


def _display_name(var: str) -> str:
    return re.sub(r"_(Mean|Total|Sum)$", "", var, flags=re.IGNORECASE)


def _corr_narrative_key(var1: str, var2: str) -> str:
    safe1 = re.sub(r"[^\w]", "_", var1)
    safe2 = re.sub(r"[^\w]", "_", var2)
    return f"corr_narrative_{safe1}_{safe2}"


def _init_correlation_state() -> None:
    defaults = {
        KEY_CORRELATION_RUN: False,
        KEY_INCLUDE_SUBSCALES: True,
        KEY_MOD_X: None,
        KEY_MOD_Y: None,
        KEY_MOD_W: None,
        KEY_MOD_CONTROLS: [],
        KEY_CORRELATION_PAIR_RESULTS: {},
        KEY_CORRELATION_RESULTS: None,
        KEY_MODERATION_RESULTS: None,
        KEY_CORRELATION_FIGURE: None,
        KEY_MODERATION_FIGURE: None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _composite_names(composites: list, *, include_subscales: bool) -> list[str]:
    names: list[str] = []
    for comp in composites:
        name = comp.get("name")
        if not name:
            continue
        if include_subscales or name.endswith("_Total") or name.endswith("_Mean"):
            names.append(name)
    return sorted(names)


def _find_composite_match(composite_names: list[str], patterns: list[str]) -> str | None:
    for pattern in patterns:
        needle = pattern.lower()
        for name in composite_names:
            if needle in name.lower():
                return name
    return None


def _choose_correlation_method(
    composite_names: list[str], normality: dict
) -> str:
    if not composite_names:
        return "pearson"
    for name in composite_names:
        entry = normality.get(name, {})
        if not entry.get("normal", False):
            return "spearman"
    return "pearson"


def _pairwise_correlation(
    df: pd.DataFrame, cols: list[str], method: str
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    n = len(cols)
    r_vals = np.full((n, n), np.nan)
    p_vals = np.full((n, n), np.nan)
    n_vals = np.zeros((n, n), dtype=int)

    for i, c1 in enumerate(cols):
        for j, c2 in enumerate(cols):
            if i == j:
                r_vals[i, j] = 1.0
                p_vals[i, j] = 0.0
                n_vals[i, j] = int(df[c1].dropna().shape[0])
                continue
            sub = df[[c1, c2]].dropna()
            n_pair = len(sub)
            n_vals[i, j] = n_vals[j, i] = n_pair
            if n_pair < 3:
                continue
            if method == "pearson":
                r, p = stats.pearsonr(sub[c1], sub[c2])
            else:
                r, p = stats.spearmanr(sub[c1], sub[c2])
            r_vals[i, j] = r_vals[j, i] = float(r)
            p_vals[i, j] = p_vals[j, i] = float(p)

    r_df = pd.DataFrame(r_vals, index=cols, columns=cols)
    p_df = pd.DataFrame(p_vals, index=cols, columns=cols)
    n_df = pd.DataFrame(n_vals, index=cols, columns=cols)
    return r_df, p_df, n_df


def _format_correlation_cell(r: float, p: float) -> str:
    if pd.isna(r) or pd.isna(p):
        return "—"
    stars = "**" if p < 0.01 else ("*" if p < 0.05 else "")
    return f"{format_stat(r, 2)}{stars}"


def _correlation_display_table(r_df: pd.DataFrame, p_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row_name in r_df.index:
        row_label = _display_name(row_name)
        row_cells = {"Değişken": row_label}
        for col_name in r_df.columns:
            row_cells[_display_name(col_name)] = _format_correlation_cell(
                r_df.loc[row_name, col_name],
                p_df.loc[row_name, col_name],
            )
        rows.append(row_cells)
    return pd.DataFrame(rows)


def _render_correlation_matrix_section(
    final_df: pd.DataFrame,
    composites: list,
    normality: dict,
) -> dict | None:
    st.markdown("### Korelasyon Matrisi")
    include_subscales = st.checkbox(
        "Alt ölçek bileşiklerini dahil et",
        value=bool(st.session_state.get(KEY_INCLUDE_SUBSCALES, True)),
        key=KEY_INCLUDE_SUBSCALES,
    )
    cols = _composite_names(composites, include_subscales=include_subscales)
    cols = [c for c in cols if c in final_df.columns]

    if len(cols) < 2:
        st.info("Korelasyon matrisi için en az iki bileşik değişken gerekir.")
        return None

    method = _choose_correlation_method(cols, normality)
    method_label = "Pearson" if method == "pearson" else "Spearman"
    normality_note = (
        "seçilen tüm bileşikler normallik kontrollerini geçti"
        if method == "pearson"
        else "en az bir bileşik normal değildi — SPSS tüm matris kuralı"
    )
    st.caption(
        f"Korelasyon yöntemi: **{method_label}** ({normality_note}). "
        f"* p < .05, ** p < .01."
    )

    r_df, p_df, n_df = _pairwise_correlation(final_df, cols, method)
    display_df = _correlation_display_table(r_df, p_df)
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    display_labels = [_display_name(c) for c in cols]
    r_plot = r_df.copy()
    r_plot.index = display_labels
    r_plot.columns = display_labels
    corr_matrix = r_plot.astype(float)

    matplotlib.rcParams["font.family"] = "Times New Roman"
    matplotlib.rcParams["font.size"] = 11

    fig, ax = plt.subplots(figsize=(7, 6))
    mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
    sns.heatmap(
        corr_matrix,
        ax=ax,
        mask=mask,
        annot=True,
        fmt=".2f",
        annot_kws={"size": 11, "family": "Times New Roman"},
        cmap=sns.diverging_palette(220, 10, as_cmap=True),
        vmin=-1,
        vmax=1,
        center=0,
        square=True,
        linewidths=0.5,
        linecolor="white",
        cbar_kws={"shrink": 0.8, "label": "r"},
    )
    ax.set_xticklabels(
        [_display_name(c) for c in corr_matrix.columns],
        rotation=45,
        ha="right",
        fontsize=10,
    )
    ax.set_yticklabels(
        [_display_name(c) for c in corr_matrix.index],
        rotation=0,
        fontsize=10,
    )
    ax.set_title(
        f"{method_label} Korelasyon Matrisi",
        fontsize=13,
        fontweight="bold",
        pad=12,
        fontfamily="Times New Roman",
    )
    fig.tight_layout()

    buf_heatmap = io.BytesIO()
    fig.savefig(buf_heatmap, format="png", dpi=300, bbox_inches="tight")
    buf_heatmap.seek(0)
    st.session_state[KEY_CORRELATION_FIGURE] = buf_heatmap.getvalue()
    st.pyplot(fig)
    plt.close(fig)

    pair_results: dict[str, dict] = {}
    narrative_keys: list[str] = []
    significant_pairs: list[tuple[str, str, float, float, int]] = []
    pair_ns = [
        int(n_df.loc[v1, v2])
        for v1 in cols
        for v2 in cols
        if v1 != v2 and not pd.isna(n_df.loc[v1, v2])
    ]
    typical_n = max(pair_ns) if pair_ns else len(final_df)

    for i, v1 in enumerate(cols):
        for j, v2 in enumerate(cols):
            if j <= i:
                continue
            r = r_df.loc[v1, v2]
            p = p_df.loc[v1, v2]
            n = int(n_df.loc[v1, v2])
            if pd.isna(r) or pd.isna(p):
                continue
            pair_key = f"{v1}|{v2}"
            pair_results[pair_key] = {
                "var1": v1,
                "var2": v2,
                "r": float(r),
                "p": float(p),
                "n": n,
                "method": method,
            }
            if p < 0.05:
                significant_pairs.append((v1, v2, float(r), float(p), n))

    if significant_pairs:
        st.markdown("**Anlamlı korelasyonlar — APA anlatıları**")
        for v1, v2, r_val, p_val, n_val in significant_pairs:
            narrative_key = _corr_narrative_key(v1, v2)
            narrative_keys.append(narrative_key)
            text = format_correlation_narrative(v1, v2, r_val, p_val, n_val)
            if "prementaliz" in v1.lower() or "prementaliz" in v2.lower():
                text += (
                    " Not: Ön-mentalizasyon alt ölçeğinde yüksek puanlar "
                    "daha düşük yansıtıcı işlevi gösterir."
                )
            with st.expander(
                f"📝 Teze nasıl yazılır? — {_display_name(v1)} × {_display_name(v2)}",
                expanded=False,
            ):
                st.caption(
                    "Aşağıdaki metni tezinizin ilgili bölümüne kopyalayabilirsiniz. "
                    "Gerekirse düzenleyin."
                )
                st.text_area(
                    "APA anlatısı",
                    value=text,
                    height=100,
                    key=narrative_key,
                )
    else:
        st.info("Seçilen matriste p < .05 düzeyinde anlamlı korelasyon bulunamadı.")

    st.session_state[KEY_CORRELATION_PAIR_RESULTS] = pair_results
    st.session_state[KEY_CORRELATION_RESULTS] = {
        "method": method_label,
        "matrix": r_df,
        "pmatrix": p_df,
        "n": typical_n,
        "narrative_keys": narrative_keys,
    }

    return pair_results


def _get_pair_result(
    pair_results: dict, name_a: str, name_b: str
) -> dict | None:
    key1 = f"{name_a}|{name_b}"
    key2 = f"{name_b}|{name_a}"
    return pair_results.get(key1) or pair_results.get(key2)


def _demographic_columns(final_df: pd.DataFrame, col_roles: dict) -> list[str]:
    return [c for c in final_df.columns if col_roles.get(c) == "demographic"]


def _prep_moderation_data(
    df: pd.DataFrame,
    x_col: str,
    w_col: str,
    y_col: str,
    control_cols: list[str],
) -> tuple[pd.DataFrame, float, float, float]:
    use_cols = [y_col, x_col, w_col] + [c for c in control_cols if c in df.columns]
    data = df[use_cols].copy()
    # statsmodels cannot fit with object dtypes; coerce all model columns to numeric
    for col in use_cols:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.dropna()
    x_mean = float(data[x_col].mean())
    w_mean = float(data[w_col].mean())
    w_sd = float(data[w_col].std(ddof=1))
    data["X_c"] = data[x_col] - x_mean
    data["W_c"] = data[w_col] - w_mean
    data["XW"] = data["X_c"] * data["W_c"]
    return data, x_mean, w_mean, w_sd


def _fit_ols(y: pd.Series, predictors: pd.DataFrame):
    x = sm.add_constant(predictors, has_constant="add")
    return sm.OLS(y, x).fit()


def _nested_model_delta(model_small, model_large) -> tuple[float, float, float]:
    delta_r2 = float(model_large.rsquared - model_small.rsquared)
    df_num = int(model_large.df_model - model_small.df_model)
    df_den = int(model_large.df_resid)
    if df_num <= 0 or df_den <= 0:
        return delta_r2, float("nan"), float("nan")
    f_change = (
        (model_small.ssr - model_large.ssr) / df_num
    ) / (model_large.ssr / df_den)
    p_change = float(stats.f.sf(f_change, df_num, df_den))
    return delta_r2, float(f_change), p_change


def _bootstrap_interaction_ci(
    data: pd.DataFrame,
    y_col: str,
    predictor_cols: list[str],
    interaction_col: str,
    n_boot: int = 5000,
    seed: int = 42,
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(data)
    coefs: list[float] = []
    y = data[y_col]
    x_base = data[predictor_cols]
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        sample_x = x_base.iloc[idx]
        sample_y = y.iloc[idx]
        try:
            fit = _fit_ols(sample_y, sample_x)
            coefs.append(float(fit.params.get(interaction_col, np.nan)))
        except Exception:
            continue
    if not coefs:
        return float("nan"), float("nan")
    return float(np.percentile(coefs, 2.5)), float(np.percentile(coefs, 97.5))


def _conditional_effect_raw(
    model,
    w_c_value: float,
    level_label: str,
    w_display: float,
) -> dict:
    params = model.params
    cov = model.cov_params()
    b_x = float(params.get("X_c", 0.0))
    b_xw = float(params.get("XW", 0.0))
    effect = b_x + b_xw * w_c_value
    idx_x = params.index.get_loc("X_c")
    idx_xw = params.index.get_loc("XW")
    var_effect = (
        cov.iloc[idx_x, idx_x]
        + (w_c_value**2) * cov.iloc[idx_xw, idx_xw]
        + 2 * w_c_value * cov.iloc[idx_x, idx_xw]
    )
    se = float(np.sqrt(var_effect)) if var_effect > 0 else float("nan")
    t_val = effect / se if se and not np.isnan(se) else float("nan")
    p_val = (
        float(2 * (1 - stats.t.cdf(abs(t_val), model.df_resid)))
        if not np.isnan(t_val)
        else float("nan")
    )
    ci_lo = effect - stats.t.ppf(0.975, model.df_resid) * se
    ci_hi = effect + stats.t.ppf(0.975, model.df_resid) * se
    return {
        "level": level_label,
        "w_val": float(w_display),
        "b": float(effect),
        "se": float(se),
        "t": float(t_val),
        "p": float(p_val),
        "ci": [float(ci_lo), float(ci_hi)],
    }


def _conditional_effect_row(
    model,
    w_c_value: float,
    w_label: str,
    w_display: float,
) -> dict:
    params = model.params
    cov = model.cov_params()
    b_x = float(params.get("X_c", 0.0))
    b_xw = float(params.get("XW", 0.0))
    effect = b_x + b_xw * w_c_value
    idx_x = params.index.get_loc("X_c")
    idx_xw = params.index.get_loc("XW")
    var_effect = (
        cov.iloc[idx_x, idx_x]
        + (w_c_value**2) * cov.iloc[idx_xw, idx_xw]
        + 2 * w_c_value * cov.iloc[idx_x, idx_xw]
    )
    se = float(np.sqrt(var_effect)) if var_effect > 0 else float("nan")
    t_val = effect / se if se and not np.isnan(se) else float("nan")
    p_val = (
        float(2 * (1 - stats.t.cdf(abs(t_val), model.df_resid)))
        if not np.isnan(t_val)
        else float("nan")
    )
    ci_lo = effect - stats.t.ppf(0.975, model.df_resid) * se
    ci_hi = effect + stats.t.ppf(0.975, model.df_resid) * se
    return {
        "W düzeyi": w_label,
        "W değeri": round(w_display, 3),
        "X'in Y üzerindeki etkisi": format_stat(effect, 3),
        "SS": format_stat(se, 3),
        "t": f"{t_val:.2f}" if not np.isnan(t_val) else "—",
        "p": format_p(p_val),
        "95% GA": format_ci(ci_lo, ci_hi, 3),
    }


def _compute_vif_table(model) -> pd.DataFrame:
    exog = model.model.exog
    names = model.model.exog_names
    rows = []
    for i, name in enumerate(names):
        if name == "const":
            continue
        try:
            vif = float(variance_inflation_factor(exog, i))
        except Exception:
            vif = float("nan")
        rows.append({"Yordayıcı": name, "VIF": round(vif, 2) if pd.notna(vif) else "—"})
    return pd.DataFrame(rows)


def _hypothesis_supported(result: dict | None, *, positive: bool | None = None) -> str:
    if not result:
        return "—"
    p = result.get("p", 1.0)
    r = result.get("r", 0.0)
    if p >= 0.05:
        return "Hayır"
    if positive is True:
        return "Evet" if r > 0 else "Hayır"
    if positive is False:
        return "Evet" if r < 0 else "Hayır"
    return "Evet"


def _render_moderation_section(
    final_df: pd.DataFrame,
    composites: list,
    col_roles: dict,
    pair_results: dict,
) -> None:
    st.markdown("### Moderasyon Analizi (PROCESS Model 1)")

    composite_names = _composite_names(composites, include_subscales=True)
    composite_names = [c for c in composite_names if c in final_df.columns]
    if len(composite_names) < 3:
        st.info("Moderasyon analizi için en az üç bileşik değişken gerekir.")
        return

    default_x = _find_composite_match(composite_names, ["CBMO", "Mükemmeliyetçi", "Mukemmeliyetc"])
    default_y = _find_composite_match(composite_names, ["Sharenting"])
    default_w = _find_composite_match(composite_names, ["PRFQ"])

    if st.session_state.get(KEY_MOD_X) not in composite_names:
        st.session_state[KEY_MOD_X] = default_x or composite_names[0]
    if st.session_state.get(KEY_MOD_Y) not in composite_names:
        st.session_state[KEY_MOD_Y] = default_y or composite_names[min(1, len(composite_names) - 1)]
    if st.session_state.get(KEY_MOD_W) not in composite_names:
        st.session_state[KEY_MOD_W] = default_w or composite_names[min(2, len(composite_names) - 1)]

    x_col = st.selectbox("X (yordayıcı)", composite_names, key=KEY_MOD_X)
    y_col = st.selectbox("Y (sonuç)", composite_names, key=KEY_MOD_Y)
    w_col = st.selectbox("W (moderatör)", composite_names, key=KEY_MOD_W)

    demo_cols = _demographic_columns(final_df, col_roles)
    used = {x_col, y_col, w_col}
    control_options = sorted(
        set(demo_cols) | {c for c in composite_names if c not in used}
    )
    control_options = [c for c in control_options if c in final_df.columns]

    st.multiselect(
        "Kontrol değişkenleri (ortalaması alınmaz; etkileşime dahil edilmez)",
        options=control_options,
        default=[
            c
            for c in st.session_state.get(KEY_MOD_CONTROLS, [])
            if c in control_options
        ],
        key=KEY_MOD_CONTROLS,
    )
    control_cols = list(st.session_state.get(KEY_MOD_CONTROLS, []))

    if x_col == y_col or x_col == w_col or y_col == w_col:
        st.error("X, Y ve W üç farklı değişken olmalıdır.")
        return

    data, x_mean, w_mean, w_sd = _prep_moderation_data(
        final_df, x_col, w_col, y_col, control_cols
    )
    if len(data) < 10:
        st.warning(
            "Liste bazlı silme sonrası moderasyon analizi için yeterli tam vaka yok."
        )
        return

    st.caption(
        "Etkileşim terimi hesaplanmadan önce X ve W ortalamaları alındı (Hayes, 2013)."
    )

    pred_m1 = ["X_c", "W_c"] + [c for c in control_cols if c in data.columns]
    pred_m2 = ["X_c", "W_c", "XW"] + [c for c in control_cols if c in data.columns]
    model1 = _fit_ols(data[y_col], data[pred_m1])
    model2 = _fit_ols(data[y_col], data[pred_m2])

    delta_r2, delta_f, delta_p = _nested_model_delta(model1, model2)
    b_int = float(model2.params.get("XW", 0.0))
    se_int = float(model2.bse.get("XW", np.nan))
    t_int = float(model2.tvalues.get("XW", np.nan))
    p_int = float(model2.pvalues.get("XW", np.nan))
    ci_int = model2.conf_int().loc["XW"] if "XW" in model2.params.index else (np.nan, np.nan)
    boot_lo, boot_hi = _bootstrap_interaction_ci(data, y_col, pred_m2, "XW")

    st.markdown("**Model özeti (X + W + etkileşim + kontroller)**")
    st.write(
        f"R = {format_stat(float(np.sqrt(max(model2.rsquared, 0))), 3)}, "
        f"R² = {format_stat(float(model2.rsquared), 3)}, "
        f"adj. R² = {format_stat(float(model2.rsquared_adj), 3)}, "
        f"F({model2.df_model:.0f}, {model2.df_resid:.0f}) = {model2.fvalue:.2f}, "
        f"p {format_p(float(model2.f_pvalue))}"
    )

    st.markdown("**ΔR² — etkileşim bloğu**")
    st.write(
        f"Model 1: X + W + kontroller → Model 2: + X×W. "
        f"ΔR² = {format_stat(delta_r2, 3)}, ΔF = {delta_f:.2f}, p {format_p(delta_p)}"
    )

    st.markdown("**Etkileşim terimi (OLS ve bootstrap)**")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Terim": f"{x_col} × {w_col}",
                    "B": format_stat(b_int, 3),
                    "SS (OLS)": format_stat(se_int, 3),
                    "t": f"{t_int:.2f}",
                    "p": format_p(p_int),
                    "95% GA (OLS)": format_ci(float(ci_int[0]), float(ci_int[1]), 3),
                    "95% GA (bootstrap)": format_ci(boot_lo, boot_hi, 3),
                }
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )

    cond_raw = [
        _conditional_effect_raw(
            model2, -w_sd, "W-1SD", float(w_mean - w_sd)
        ),
        _conditional_effect_raw(model2, 0.0, "W mean", float(w_mean)),
        _conditional_effect_raw(
            model2, w_sd, "W+1SD", float(w_mean + w_sd)
        ),
    ]
    cond_rows = [
        _conditional_effect_row(
            model2,
            -w_sd,
            "W ortalaması − 1 SS",
            float(w_mean - w_sd),
        ),
        _conditional_effect_row(model2, 0.0, "W ortalaması", float(w_mean)),
        _conditional_effect_row(
            model2,
            w_sd,
            "W ortalaması + 1 SS",
            float(w_mean + w_sd),
        ),
    ]
    st.markdown("**X'in Y üzerindeki koşullu etkileri**")
    st.dataframe(pd.DataFrame(cond_rows), use_container_width=True, hide_index=True)

    vif_df = _compute_vif_table(model2)
    st.markdown("**Varyans şişkinlik faktörleri (VIF)**")
    st.dataframe(vif_df, use_container_width=True, hide_index=True)
    if any(isinstance(v, (int, float)) and v > 10 for v in vif_df["VIF"]):
        st.warning(
            "Bir veya daha fazla yordayıcının VIF > 10 — çoklu doğrusallık standart hataları şişirebilir."
        )

    b0 = float(model2.params.get("const", 0.0))
    b1 = float(model2.params.get("X_c", 0.0))
    b2 = float(model2.params.get("W_c", 0.0))
    b3 = float(model2.params.get("XW", 0.0))
    control_contrib = 0.0
    for c in control_cols:
        if c in model2.params.index:
            control_contrib += float(model2.params[c]) * float(data[c].mean())

    intercept = b0 + control_contrib
    b_x = b1
    b_w = b2
    b_xw = b3

    fig, ax = plt.subplots(figsize=(8, 5))
    colors = {"W − 1 SS": "#1f4e79", "W ortalaması": "#2e7d32", "W + 1 SS": "#b71c1c"}
    markers = {"W − 1 SS": "o", "W ortalaması": "s", "W + 1 SS": "^"}
    x_range = np.linspace(float(data[x_col].min()), float(data[x_col].max()), 100)
    x_c_range = x_range - x_mean

    w_levels = [
        ("W − 1 SS", -w_sd),
        ("W ortalaması", 0.0),
        ("W + 1 SS", w_sd),
    ]

    for label, w_c_val in w_levels:
        y_pred = (
            intercept
            + b_x * x_c_range
            + b_w * w_c_val
            + b_xw * x_c_range * w_c_val
        )
        color = colors[label]
        marker = markers[label]
        ax.plot(x_range, y_pred, color=color, linewidth=2.5, label=label)
        ax.plot(
            [x_range[0], x_range[-1]],
            [y_pred[0], y_pred[-1]],
            marker=marker,
            color=color,
            markersize=7,
            linestyle="none",
        )

    ax.set_xlabel(_display_name(x_col), fontsize=12, fontfamily="Times New Roman")
    ax.set_ylabel(_display_name(y_col), fontsize=12, fontfamily="Times New Roman")
    ax.set_title(
        f"Moderasyon: {_display_name(w_col)}, {_display_name(x_col)} → {_display_name(y_col)} "
        f"ilişkisini düzenlemektedir",
        fontsize=12,
        fontweight="bold",
        pad=10,
        fontfamily="Times New Roman",
    )
    ax.legend(
        title=_display_name(w_col),
        title_fontsize=10,
        fontsize=10,
        framealpha=0.9,
        edgecolor="lightgrey",
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.tick_params(labelsize=10)
    fig.tight_layout()

    buf_plot = io.BytesIO()
    fig.savefig(buf_plot, format="png", dpi=300, bbox_inches="tight")
    buf_plot.seek(0)
    st.session_state[KEY_MODERATION_FIGURE] = buf_plot.getvalue()
    st.pyplot(fig)
    plt.close(fig)

    h1_supported = "Evet" if p_int < 0.05 else "Hayır"
    prfq_total = _find_composite_match(composite_names, ["PRFQ"])
    perf = x_col
    share = y_col
    h2_res = _get_pair_result(pair_results, perf, share)
    h3_res = _get_pair_result(pair_results, perf, prfq_total or w_col)
    h4_res = _get_pair_result(pair_results, share, prfq_total or w_col)

    st.markdown("**Hipotez özeti**")
    w_mod = _display_name(w_col)
    x_pred = _display_name(x_col)
    y_out = _display_name(y_col)
    w_corr = _display_name(prfq_total or w_col)

    hyp_df = pd.DataFrame(
        [
            {
                "Hipotez": (
                    f"H1: {w_mod}, {x_pred}→{y_out} ilişkisini moderatör olarak düzenlemektedir"
                ),
                "Test": "Etkileşim terimi B, p, bootstrap GA",
                "Sonuç": (
                    f"B = {format_stat(b_int, 3)}, p {format_p(p_int)}, "
                    f"boot GA {format_ci(boot_lo, boot_hi, 3)}"
                ),
                "Desteklendi mi?": h1_supported,
            },
            {
                "Hipotez": f"H2: {x_pred} → {y_out} (pozitif)",
                "Test": "Korelasyon r, p",
                "Sonuç": (
                    f"r = {format_stat(h2_res['r'], 2)}, p {format_p(h2_res['p'])}"
                    if h2_res
                    else "—"
                ),
                "Desteklendi mi?": _hypothesis_supported(h2_res, positive=True),
            },
            {
                "Hipotez": f"H3: {x_pred} → {w_corr} (negatif)",
                "Test": "Korelasyon r, p",
                "Sonuç": (
                    f"r = {format_stat(h3_res['r'], 2)}, p {format_p(h3_res['p'])}"
                    if h3_res
                    else "—"
                ),
                "Desteklendi mi?": _hypothesis_supported(h3_res, positive=False),
            },
            {
                "Hipotez": f"H4: {y_out} → {w_corr} (negatif)",
                "Test": "Korelasyon r, p",
                "Sonuç": (
                    f"r = {format_stat(h4_res['r'], 2)}, p {format_p(h4_res['p'])}"
                    if h4_res
                    else "—"
                ),
                "Desteklendi mi?": _hypothesis_supported(h4_res, positive=False),
            },
        ]
    )
    st.dataframe(hyp_df, use_container_width=True, hide_index=True)

    mod_narrative = format_moderation_narrative(
        x_col,
        y_col,
        w_col,
        float(model2.rsquared),
        float(model2.fvalue),
        float(model2.df_model),
        float(model2.df_resid),
        float(model2.f_pvalue),
        b_int,
        se_int,
        t_int,
        p_int,
        float(ci_int[0]),
        float(ci_int[1]),
        delta_r2,
    )
    cond_narrative = format_conditional_effects_narrative(
        x_col,
        y_col,
        w_col,
        cond_raw[0]["b"],
        cond_raw[0]["p"],
        cond_raw[1]["b"],
        cond_raw[1]["p"],
        cond_raw[2]["b"],
        cond_raw[2]["p"],
    )
    with st.expander("📝 Teze nasıl yazılır? — moderasyon", expanded=False):
        st.caption(
            "Aşağıdaki metni tezinizin ilgili bölümüne kopyalayabilirsiniz. "
            "Gerekirse düzenleyin."
        )
        st.text_area(
            "APA anlatısı",
            value=mod_narrative,
            height=160,
            key=KEY_APA_NARRATIVE_MODERATION,
        )
    with st.expander("📝 Teze nasıl yazılır? — koşullu etkiler", expanded=False):
        st.caption(
            "Aşağıdaki metni tezinizin ilgili bölümüne kopyalayabilirsiniz. "
            "Gerekirse düzenleyin."
        )
        st.text_area(
            "APA anlatısı",
            value=cond_narrative,
            height=120,
            key=KEY_APA_NARRATIVE_CONDITIONAL,
        )

    st.session_state[KEY_MODERATION_RESULTS] = {
        "x": x_col,
        "y": y_col,
        "w": w_col,
        "R2": float(model2.rsquared),
        "adj_R2": float(model2.rsquared_adj),
        "F": float(model2.fvalue),
        "df1": float(model2.df_model),
        "df2": float(model2.df_resid),
        "p_model": float(model2.f_pvalue),
        "delta_R2": delta_r2,
        "delta_F": delta_f,
        "delta_p": delta_p,
        "b_interaction": b_int,
        "se_interaction": se_int,
        "t_interaction": t_int,
        "p_interaction": p_int,
        "ci_ols": [float(ci_int[0]), float(ci_int[1])],
        "ci_boot": [boot_lo, boot_hi],
        "conditional_effects": cond_raw,
        "vif_df": vif_df,
        "hypothesis_df": hyp_df,
        "moderation_narrative_key": KEY_APA_NARRATIVE_MODERATION,
        "conditional_narrative_key": KEY_APA_NARRATIVE_CONDITIONAL,
    }


def render():
    st.header("Korelasyon ve Moderasyon")
    _init_correlation_state()

    final_df = st.session_state.get(KEY_FINAL_DF)
    if final_df is None:
        st.warning("Önce Modül 1 ön işlemesini tamamlayın (Bileşik Puanlar Oluştur dahil).")
        return

    composites = st.session_state.get(KEY_COMPOSITE_CONFIG, [])
    col_roles = st.session_state.get(KEY_COL_ROLES, {})
    normality = st.session_state.get(KEY_NORMALITY_RESULTS, {})

    pair_results: dict = {}
    with st.expander("Korelasyon Matrisi", expanded=True):
        pair_results = _render_correlation_matrix_section(
            final_df, composites, normality
        )

    with st.expander("Moderasyon Analizi", expanded=True):
        pair_results = st.session_state.get(KEY_CORRELATION_PAIR_RESULTS, pair_results)
        _render_moderation_section(final_df, composites, col_roles, pair_results)

    st.session_state[KEY_CORRELATION_RUN] = True
