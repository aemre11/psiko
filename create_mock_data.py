"""Generate mock_psych_data.xlsx for testing PsychStats upload and preprocessing."""

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "mock_psych_data.xlsx"

N_ROWS = 8

SCALE_ITEMS = [
    "Çocuğumun okul performansı konusunda her zaman kusursuz olmasını beklerim.",
    "Çocuğumun fotoğraflarını sosyal medyada paylaşmaktan büyük keyif alırım.",
    "Çocuğumun davranışlarında en küçük hata bile beni endişelendirir.",
    "Çocuğumun başarıları benim için çok önemlidir.",
    "Sosyal medyada çocuğumla ilgili paylaşımlar yapmak beni mutlu eder.",
    "Çocuğumun mükemmel görünmesi benim için önceliklidir.",
]

base_time = datetime(2025, 5, 1, 9, 15, 0)

rng = np.random.default_rng(42)

rows = []
for i in range(N_ROWS):
    row = {
        "Zaman Damgası": (base_time + timedelta(hours=i * 3, minutes=i * 7)).strftime(
            "%d.%m.%Y %H:%M:%S"
        ),
        "E-posta Adresi": f"katilimci{i + 1}@ornek.edu.tr",
        "Yaşınız": int(rng.integers(28, 45)),
    }
    for item in SCALE_ITEMS:
        row[item] = int(rng.integers(1, 6))
    rows.append(row)

form_df = pd.DataFrame(rows)

# At least one missing value for listwise-deletion testing
form_df.loc[2, SCALE_ITEMS[1]] = np.nan
form_df.loc[5, "Yaşınız"] = np.nan

aciklamalar_df = pd.DataFrame(
    {
        "Not": [
            "Bu sayfa Google Forms dışa aktarımındaki açıklama sayfasını simüle eder.",
            "PsychStats yalnızca veri sayfasını seçmelidir.",
        ]
    }
)

with pd.ExcelWriter(OUTPUT, engine="openpyxl") as writer:
    form_df.to_excel(writer, sheet_name="Form Yanıtları 1", index=False)
    aciklamalar_df.to_excel(writer, sheet_name="Açıklamalar", index=False)

print(f"Created: {OUTPUT}")
print(f"  Sheet 1: {len(form_df)} rows x {len(form_df.columns)} columns")
print(f"  Sheet 2: {len(aciklamalar_df)} rows")
