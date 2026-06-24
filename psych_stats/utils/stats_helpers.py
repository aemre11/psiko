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

import pandas as pd


def _sort_item_total_dataframe(stats_df: pd.DataFrame) -> pd.DataFrame:
    sort_key = stats_df["Item"].str.extract(r"(\d+)$", expand=False).astype(int)
    return (
        stats_df.assign(sort_key=sort_key)
        .sort_values("sort_key")
        .drop(columns="sort_key")
        .reset_index(drop=True)
    )


def item_total_statistics_table(
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
                "Düzeltilmiş Madde-Toplam Korelasyonu": f"{corrected_r:.3f}"
                if pd.notna(corrected_r)
                else "—",
                "Madde Silinirse α": alpha_str if alpha_str != "N/A" else "—",
            }
        )
    stats_df = pd.DataFrame(rows)
    return _sort_item_total_dataframe(stats_df)
