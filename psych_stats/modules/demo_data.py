"""
Synthetic teaching dataset for PsychStats.

Generates a reproducible, textbook-clean dataset so a first-time user (or
a psychology student with no SPSS background) can walk the full pipeline
without uploading their own data.

Design choices:
- Fixed seed → identical results every time → safe to use in tutorials.
- N = 180 participants (large enough for inferential tests, small enough
  to render quickly).
- Two scales with intentionally obvious reverse-coded items so students
  see the reverse-scoring detection light up:
    * Life Satisfaction (LS) — 5-item, 1-7 Likert, item LS3 reversed
    * Anxiety (ANX)         — 7-item, 1-5 Likert, items ANX2 + ANX6 reversed
- Demographics chosen for clean group comparisons:
    * Cinsiyet (Kadın / Erkek)        → effect on Anxiety
    * Yaş Grubu (18-22 / 23-30 / 31+) → mild effect on Life Satisfaction
    * Bölüm (5 levels)                → null effect (teaches "non-significant")
    * Sınıf (1-4)                     → ordinal, near-null
- A Timestamp column that should be auto-classified as "Yok say" — teaches
  Step 2's role-assignment logic.
- ~2% missing data sprinkled in scattered cells so the missing-data
  warning fires and students see how the app handles it.
"""

from __future__ import annotations

import datetime as _dt
from typing import Final

import numpy as np
import pandas as pd

DEMO_DATASET_NAME: Final[str] = "PsychStats_demo_veri.xlsx"
DEMO_N: Final[int] = 180
DEMO_SEED: Final[int] = 20240601  # PsychStats v1 release date — arbitrary but fixed.

# Public column order — also used by the Step 1 preview to ensure
# the timestamp shows up first (so students see "Zaman Damgası" auto-classified).
_LS_COLS = [f"LS_{i}" for i in range(1, 6)]
_ANX_COLS = [f"ANX_{i}" for i in range(1, 8)]


def generate_demo_dataframe() -> pd.DataFrame:
    """
    Return a fresh DataFrame each call (callers may mutate, so don't share).
    Deterministic — same seed → same data every call.
    """
    rng = np.random.default_rng(DEMO_SEED)

    # -------------------- Demographics --------------------
    cinsiyet = rng.choice(["Kadın", "Erkek"], size=DEMO_N, p=[0.62, 0.38])
    yas_grubu = rng.choice(
        ["18-22", "23-30", "31+"], size=DEMO_N, p=[0.55, 0.32, 0.13]
    )
    bolum = rng.choice(
        ["Psikoloji", "Sosyoloji", "PDR", "Felsefe", "Eğitim Bilimleri"],
        size=DEMO_N,
        p=[0.35, 0.20, 0.20, 0.10, 0.15],
    )
    sinif = rng.integers(1, 5, size=DEMO_N)  # 1..4 inclusive

    # -------------------- Latent traits --------------------
    # We generate latent "true" Life Satisfaction and Anxiety per participant,
    # then build observable Likert items around them. This gives:
    #   - Internal consistency within each scale (high α)
    #   - A real negative correlation between LS and ANX
    #   - A real group difference (women report higher anxiety in the demo)

    base_ls = rng.normal(loc=4.8, scale=1.1, size=DEMO_N)
    base_anx = rng.normal(loc=3.0, scale=0.9, size=DEMO_N)

    # Couple them: higher LS → lower ANX (r ≈ -0.45)
    base_anx = base_anx - 0.40 * (base_ls - base_ls.mean())

    # Group effect: cinsiyet=Kadın has +0.35 ANX shift
    base_anx[cinsiyet == "Kadın"] += 0.35
    # Mild yaş grubu effect on LS
    base_ls[yas_grubu == "31+"] += 0.35
    base_ls[yas_grubu == "18-22"] -= 0.15

    # -------------------- Life Satisfaction items (1-7) --------------------
    ls_items: dict[str, np.ndarray] = {}
    for i, col in enumerate(_LS_COLS):
        # Item-specific noise + small intercept variation
        noise = rng.normal(0, 0.6, size=DEMO_N)
        score = base_ls + noise
        if col == "LS_3":
            # Reversed: high LS → LOW raw score on this item.
            score = 8.0 - score
        ls_items[col] = _clip_to_likert(score, low=1, high=7)

    # -------------------- Anxiety items (1-5) --------------------
    anx_items: dict[str, np.ndarray] = {}
    for col in _ANX_COLS:
        noise = rng.normal(0, 0.5, size=DEMO_N)
        score = base_anx + noise
        if col in ("ANX_2", "ANX_6"):
            score = 6.0 - score  # reversed
        anx_items[col] = _clip_to_likert(score, low=1, high=5)

    # -------------------- Assemble dataframe --------------------
    timestamps = _generate_timestamps(DEMO_N, rng)
    data: dict[str, object] = {"Zaman Damgası": timestamps}
    data["Cinsiyet"] = cinsiyet
    data["Yaş Grubu"] = yas_grubu
    data["Bölüm"] = bolum
    data["Sınıf"] = sinif
    data.update(ls_items)
    data.update(anx_items)

    df = pd.DataFrame(data)

    # -------------------- Sprinkle ~2% missing --------------------
    df = _inject_missing(df, rate=0.02, rng=rng,
                         protect=["Zaman Damgası", "Cinsiyet"])
    return df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clip_to_likert(arr: np.ndarray, *, low: int, high: int) -> pd.Series:
    """Round and clip continuous scores into a discrete Likert range (nullable Int64)."""
    rounded = np.rint(arr)
    clipped = np.clip(rounded, low, high)
    # Use pandas' nullable integer dtype so later pd.NA injection works cleanly.
    return pd.Series(clipped, dtype="Int64")


def _generate_timestamps(n: int, rng: np.random.Generator) -> list[str]:
    """Plausible Google Forms timestamp strings, 30 days back."""
    start = _dt.datetime(2024, 3, 1, 9, 0, 0)
    offsets = rng.integers(0, 30 * 24 * 60, size=n)  # minutes
    return [
        (start + _dt.timedelta(minutes=int(m))).strftime("%d/%m/%Y %H:%M:%S")
        for m in offsets
    ]


def _inject_missing(
    df: pd.DataFrame,
    *,
    rate: float,
    rng: np.random.Generator,
    protect: list[str],
) -> pd.DataFrame:
    """Replace `rate` of cells (in non-protected cols) with NaN."""
    out = df.copy()
    targets = [c for c in out.columns if c not in protect]
    n_rows = len(out)
    for col in targets:
        n_drop = int(round(n_rows * rate))
        if n_drop <= 0:
            continue
        idx = rng.choice(n_rows, size=n_drop, replace=False)
        out.loc[idx, col] = pd.NA
    return out


# ---------------------------------------------------------------------------
# Convenience metadata for use by the upload step
# ---------------------------------------------------------------------------

DEMO_DESCRIPTION = (
    "180 katılımcılı sentetik bir veri seti. İki ölçek (Yaşam Doyumu — 5 madde "
    "ve Anksiyete — 7 madde), 4 demografik değişken ve ~%2 eksik veri içerir. "
    "Üç madde (LS_3, ANX_2, ANX_6) bilinçli olarak ters puanlanmıştır — Adım 4'te "
    "uygulamanın otomatik tespitini görebilirsiniz."
)
