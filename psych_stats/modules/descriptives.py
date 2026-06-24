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

import numpy as np
import pandas as pd
import streamlit as st
from scipy import stats

from modules.data_manager import KEY_COL_ROLES, KEY_COMPOSITE_CONFIG, KEY_FINAL_DF
from utils.formatters import (
    format_normality_narrative,
    format_p,
    format_reliability_narrative,
    format_stat,
)

KEY_NORMALITY_RESULTS = "normality_results"


def _alpha_interpretation(alpha: float) -> str:
    if alpha >= 0.90:
        return "Mükemmel"
    if alpha >= 0.80:
        return "İyi"
    if alpha >= 0.70:
        return "Kabul Edilebilir"
    if alpha >= 0.60:
        return "Şüpheli"
    return "Yetersiz"


def _pct_str(value: float) -> str:
    return f"{value:.1f}%"


def _is_numeric_demographic(series: pd.Series) -> bool:
    if pd.api.types.is_numeric_dtype(series):
        return True
    non_null = series.dropna()
    if non_null.empty:
        return False
    converted = pd.to_numeric(non_null, errors="coerce")
    return converted.notna().all()


def _frequency_table(series: pd.Series) -> pd.DataFrame:
    total = len(series)
    valid = int(series.notna().sum())
    rows: list[dict] = []

    for value, frequency in series.value_counts(dropna=True).items():
        freq = int(frequency)
        rows.append(
            {
                "value": value,
                "label": value,
                "frequency": freq,
                "percent": (freq / total * 100) if total else 0.0,
                "valid_percent_val": (freq / valid * 100) if valid else 0.0,
                "is_missing": False,
            }
        )

    missing_freq = int(series.isna().sum())
    if missing_freq > 0:
        rows.append(
            {
                "value": None,
                "label": "Kayıp",
                "frequency": missing_freq,
                "percent": (missing_freq / total * 100) if total else 0.0,
                "valid_percent_val": None,
                "is_missing": True,
            }
        )

    non_missing = [r for r in rows if not r["is_missing"]]
    missing_rows = [r for r in rows if r["is_missing"]]

    if _is_numeric_demographic(series):
        non_missing.sort(key=lambda r: float(r["value"]))
    else:
        non_missing.sort(key=lambda r: r["frequency"], reverse=True)

    cum = 0.0
    for r in non_missing:
        cum += r["valid_percent_val"]
        r["valid_percent"] = _pct_str(r["valid_percent_val"])
        r["cumulative"] = _pct_str(cum)
    for r in missing_rows:
        r["valid_percent"] = ""
        r["cumulative"] = ""

    ordered = non_missing + missing_rows
    return pd.DataFrame(
        {
            "Değer": [r["label"] for r in ordered],
            "Frekans": [r["frequency"] for r in ordered],
            "Yüzde": [_pct_str(r["percent"]) for r in ordered],
            "Geçerli Yüzde": [r["valid_percent"] for r in ordered],
            "Kümülatif Yüzde": [r["cumulative"] for r in ordered],
        }
    )


def _descriptive_row(series: pd.Series, var_name: str) -> dict:
    clean = series.dropna()
    n = len(clean)
    if n == 0:
        return {
            "Değişken": var_name,
            "N": 0,
            "Ort": "—",
            "SS": "—",
            "Min": "—",
            "Max": "—",
            "Çarpıklık": "—",
            "Basıklık": "—",
            "95% GA (Ort)": "—",
            "Aykırı (|z|>3.29)": "—",
            "_skewness": None,
            "_kurtosis": None,
            "_outlier_count": 0,
        }
    skew = float(stats.skew(clean, bias=False))
    kurt = float(stats.kurtosis(clean, bias=False, fisher=True))
    if n < 2:
        ci_str = "—"
    else:
        lo, hi = stats.t.interval(
            0.95,
            df=n - 1,
            loc=float(clean.mean()),
            scale=float(clean.std(ddof=1) / np.sqrt(n)),
        )
        ci_str = f"[{lo:.2f}, {hi:.2f}]"
    sd = float(clean.std(ddof=1)) if n > 1 else 0.0
    if n < 2 or sd == 0:
        outlier_count = 0
    else:
        z_scores = (clean - clean.mean()) / sd
        outlier_count = int((np.abs(z_scores) > 3.29).sum())
    outlier_display = "Yok" if outlier_count == 0 else f"{outlier_count} işaretlendi"
    return {
        "Değişken": var_name,
        "N": n,
        "Ort": f"{clean.mean():.2f}",
        "SS": f"{clean.std(ddof=1):.2f}" if n > 1 else "—",
        "Min": f"{clean.min():.2f}",
        "Max": f"{clean.max():.2f}",
        "Çarpıklık": f"{skew:.3f}",
        "Basıklık": f"{kurt:.3f}",
        "95% GA (Ort)": ci_str,
        "Aykırı (|z|>3.29)": outlier_display,
        "_skewness": skew,
        "_kurtosis": kurt,
        "_outlier_count": outlier_count,
    }


def _normality_decision(sw_p: float, skewness: float, kurtosis: float) -> str:
    if sw_p > 0.05 and abs(skewness) < 2 and abs(kurtosis) < 7:
        return "Normal ✓"
    return "Normal Değil ⚠"


def _render_reliability_section(final_df: pd.DataFrame, composites: list) -> None:
    st.markdown("### Ölçek Güvenilirliği (Cronbach's α)")
    st.caption(
        "Cronbach's α, bir ölçeğin maddelerinin aynı şeyi tutarlı olarak ölçüp "
        "ölçmediğini gösterir. **≥0.70 kabul edilir**, .80–.90 iyi, .90+ çok iyi. "
        "Tez raporlamasında bu değeri yöntem bölümünde belirtmelisiniz."
    )
    import pingouin as pg

    rows = []
    narratives: list[tuple[str, str]] = []

    for comp in composites:
        name = comp.get("name")
        columns = comp.get("cols", comp.get("columns", []))
        if not name or len(columns) < 2:
            continue
        missing_cols = [c for c in columns if c not in final_df.columns]
        if missing_cols:
            continue
        item_data = final_df[columns].dropna()
        n_used = len(item_data)
        if n_used < 2:
            continue
        alpha, _ = pg.cronbach_alpha(data=item_data)
        n_items = int(len(columns))
        rows.append(
            {
                "scale_composite": name,
                "N Items": n_items,
                "alpha": format_stat(float(alpha), 3),
                "n_used": int(n_used),
                "interpretation": _alpha_interpretation(float(alpha)),
            }
        )
        narratives.append(
            (name, format_reliability_narrative(name, n_items, float(alpha)))
        )

    if rows:
        reliability_df = pd.DataFrame(rows)
        st.dataframe(
            reliability_df,
            column_config={
                "scale_composite": st.column_config.TextColumn("Ölçek / Bileşik"),
                "N Items": st.column_config.NumberColumn("Madde Sayısı", format="%d"),
                "alpha": st.column_config.TextColumn("α"),
                "n_used": st.column_config.NumberColumn("N (Kullanılan)", format="%d"),
                "interpretation": st.column_config.TextColumn("Yorum"),
            },
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("Güvenilirlik analizi için 2 veya daha fazla maddeli bileşik değişken bulunamadı.")

    st.info(
        "Güvenilirlik her ölçek için çıkarımsal analizden önce raporlanmalıdır (APA 7)."
    )

    for name, narrative in narratives:
        with st.expander(f"📝 Teze nasıl yazılır? — {name}", expanded=False):
            st.caption(
                "Aşağıdaki metni tezinizin ilgili bölümüne kopyalayabilirsiniz. "
                "Gerekirse düzenleyin."
            )
            st.text_area(
                "APA anlatısı",
                value=narrative,
                height=100,
                key=f"reliability_narrative_{name}",
            )


def _render_demographic_section(final_df: pd.DataFrame, col_roles: dict) -> None:
    st.markdown("### Demografik İstatistikler")
    demo_cols = [c for c in final_df.columns if col_roles.get(c) == "demographic"]

    if not demo_cols:
        st.info(
            "Demografik sütun bulunamadı. Adım 2'ye dönün ve sütunları Demografik olarak işaretleyin."
        )
        return

    for col in demo_cols:
        st.subheader(col if len(col) <= 60 else col[:57] + "…")
        st.dataframe(_frequency_table(final_df[col]), use_container_width=True, hide_index=True)


def _render_missing_data_section(
    final_df: pd.DataFrame, composites: list, col_roles: dict
) -> None:
    st.markdown("### Eksik Veri Deseni")
    rows: list[dict] = []
    total_n = len(final_df)

    for comp in composites:
        name = comp.get("name")
        if not name or name not in final_df.columns:
            continue
        n_missing = int(final_df[name].isna().sum())
        n_valid = int(final_df[name].notna().sum())
        pct = (n_missing / total_n * 100) if total_n else 0.0
        rows.append(
            {
                "Değişken": name,
                "N (Geçerli)": n_valid,
                "N (Kayıp)": n_missing,
                "% Kayıp": f"{pct:.1f}%",
            }
        )

    if not rows:
        st.info("Son veri setinde bileşik değişken bulunamadı.")
        return

    if all(r["N (Kayıp)"] == 0 for r in rows):
        st.success("Tüm bileşik değişkenlerde eksik veri tespit edilmedi.")
    else:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_descriptive_section(final_df: pd.DataFrame, composites: list) -> None:
    st.markdown("### Betimsel İstatistikler")
    rows = []
    stats_cache: dict[str, dict] = {}

    for comp in composites:
        name = comp.get("name")
        if not name or name not in final_df.columns:
            continue
        row = _descriptive_row(final_df[name], name)
        stats_cache[name] = row
        rows.append({k: v for k, v in row.items() if not k.startswith("_")})

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Son veri setinde bileşik değişken bulunamadı.")

    st.caption(
        "Basıklık değerleri artık basıklıktır (Fisher tanımı). Normal dağılım = 0."
    )
    st.caption(
        "95% GA t-dağılımı ile hesaplanmıştır. Aykırı değerler |z| > 3.29 "
        "(p < .001, iki kuyruklu) ile işaretlenmiştir."
    )
    return stats_cache if stats_cache else {}


def _render_normality_section(
    final_df: pd.DataFrame, composites: list, stats_cache: dict
) -> None:
    st.markdown("### Normallik Değerlendirmesi")
    st.caption(
        "Verilerin normal dağılıp dağılmadığını kontrol eder. **Normal dağılmayan** "
        "değişkenler için Grup Karşılaştırmaları sekmesinde otomatik olarak "
        "parametrik olmayan testler (Mann–Whitney, Kruskal–Wallis) önerilir. "
        "Korelasyon sekmesi de Pearson yerine Spearman'a geçer."
    )
    rows = []
    normality_results: dict = {}
    shapiro_large_n = False

    for comp in composites:
        name = comp.get("name")
        if not name or name not in final_df.columns:
            continue
        cached = stats_cache.get(name)
        if cached:
            skewness = cached.get("_skewness")
            kurtosis = cached.get("_kurtosis")
        else:
            row = _descriptive_row(final_df[name], name)
            skewness = row.get("_skewness")
            kurtosis = row.get("_kurtosis")

        clean = final_df[name].dropna()
        n = len(clean)
        if n < 3 or skewness is None or kurtosis is None:
            continue

        if n > 2000:
            shapiro_large_n = True

        sw_stat, sw_p = stats.shapiro(clean)
        sw_stat = float(sw_stat)
        sw_p = float(sw_p)
        normal = sw_p > 0.05 and abs(skewness) < 2 and abs(kurtosis) < 7

        normality_results[name] = {
            "normal": bool(normal),
            "sw_stat": sw_stat,
            "sw_p": sw_p,
            "skewness": float(skewness),
            "kurtosis": float(kurtosis),
        }

        rows.append(
            {
                "Değişken": name,
                "Çarpıklık": f"{skewness:.3f}",
                "Basıklık": f"{kurtosis:.3f}",
                "Shapiro-Wilk W": format_stat(sw_stat, 3),
                "p": format_p(sw_p),
                "Karar": _normality_decision(sw_p, skewness, kurtosis),
            }
        )

    if shapiro_large_n:
        st.warning(
            "Örneklem büyüklüğü Shapiro-Wilk için önerilen sınırı aşıyor (N > 2000). "
            "Dikkatli yorumlayın."
        )

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Normallik değerlendirmesi için bileşik değişken bulunamadı.")

    st.info(
        "Normal Değil olarak işaretlenen değişkenler Grup Karşılaştırmaları'nda "
        "parametrik olmayan test önerilerini tetikleyecektir. "
        "Çarpıklık/basıklık eşikleri: |çarpıklık| < 2, |basıklık| < 7 (George & Mallery, 2010)."
    )

    st.session_state[KEY_NORMALITY_RESULTS] = normality_results

    for comp in composites:
        name = comp.get("name")
        result = normality_results.get(name)
        if not result:
            continue
        narrative = format_normality_narrative(
            name,
            result.get("skewness", 0.0),
            result.get("kurtosis", 0.0),
            result.get("sw_stat", 0.0),
            result.get("sw_p", 1.0),
        )
        with st.expander(f"📝 Teze nasıl yazılır? — {name}", expanded=False):
            st.caption(
                "Aşağıdaki metni tezinizin ilgili bölümüne kopyalayabilirsiniz. "
                "Gerekirse düzenleyin."
            )
            st.text_area(
                "APA anlatısı",
                value=narrative,
                height=120,
                key=f"normality_narrative_{name}",
            )


def render():
    st.header("Betimsel İstatistikler")

    final_df = st.session_state.get(KEY_FINAL_DF)
    if final_df is None:
        st.warning("Önce Modül 1 ön işlemesini tamamlayın (Bileşik Puanlar Oluştur dahil).")
        return

    col_roles = st.session_state.get(KEY_COL_ROLES, {})
    composites = st.session_state.get(KEY_COMPOSITE_CONFIG, [])

    with st.expander("Ölçek Güvenilirliği (Cronbach's α)", expanded=True):
        _render_reliability_section(final_df, composites)

    with st.expander("Demografik İstatistikler", expanded=True):
        _render_demographic_section(final_df, col_roles)

    with st.expander("Eksik Veri Deseni", expanded=True):
        _render_missing_data_section(final_df, composites, col_roles)

    stats_cache: dict = {}
    with st.expander("Betimsel İstatistikler", expanded=True):
        stats_cache = _render_descriptive_section(final_df, composites) or {}

    with st.expander("Normallik Değerlendirmesi", expanded=True):
        _render_normality_section(final_df, composites, stats_cache)
