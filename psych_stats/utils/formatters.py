"""
Streamlit rules (PsychStats) — apply on every change in modules that use these helpers:
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

"""APA tablo ve anlatı biçimlendirme yardımcıları (saf Python — Streamlit/pandas yok)."""

import hashlib


# APA 7, bu istatistiksel sembolleri italik ister.
# Phase 5 (export.py) Word çıktısında run düzeyinde italik uygularken bu kümeyi
# tek doğruluk kaynağı olarak kullanır. Buradaki düz metin çıktısı değişmez; bu
# yalnızca Phase 5'in python-docx ile italik uygulayabilmesi için belgelenmiş bir kancadır.
APA_ITALIC_SYMBOLS = frozenset({"t", "F", "p", "r", "M", "SD", "N", "n",
                                "U", "H", "Mdn", "d", "η²", "R²", "R"})


def format_p(p_value: float) -> str:
    if p_value < 0.001:
        return "< .001"
    formatted = f"{p_value:.3f}"
    return "= " + formatted.lstrip("0")


def format_stat(value: float, decimals: int = 2) -> str:
    if value is None:
        return "—"
    rounded = round(value, decimals)
    formatted = f"{rounded:.{decimals}f}"
    if -1 < value < 1:
        if formatted.startswith("0."):
            formatted = formatted[1:]
        elif formatted.startswith("-0."):
            formatted = "-" + formatted[2:]
    return formatted


def format_ci(lower: float, upper: float, decimals: int = 2) -> str:
    return f"[{format_stat(lower, decimals)}, {format_stat(upper, decimals)}]"


def interpret_effect_size(value: float, kind: str) -> str:
    """Return Cohen's conventional magnitude label. kind: 'd'|'eta2'|'r'.
    Returns '' if value is None. Labels: negligible/small/medium/large.

    Boundary-inclusive-lower throughout; bare word, no punctuation. This reports
    magnitude only — it never interprets what the result means. Cohen (1988):
      d    : <0.20 negligible, 0.20-0.50 small, 0.50-0.80 medium, >=0.80 large (|d|)
      eta2 : <.01 negligible, .01-.06 small, .06-.14 medium, >=.14 large
      r    : <.10 negligible, .10-.30 small, .30-.50 medium, >=.50 large (|r|)
    """
    if value is None:
        return ""
    if kind == "d":
        v = abs(value)
        if v < 0.20:
            return "negligible"
        if v < 0.50:
            return "small"
        if v < 0.80:
            return "medium"
        return "large"
    if kind == "eta2":
        if value < 0.01:
            return "negligible"
        if value < 0.06:
            return "small"
        if value < 0.14:
            return "medium"
        return "large"
    if kind == "r":
        v = abs(value)
        if v < 0.10:
            return "negligible"
        if v < 0.30:
            return "small"
        if v < 0.50:
            return "medium"
        return "large"
    return ""


# interpret_effect_size'ın İngilizce kanonik anahtarlarını Türkçe anlatı etiketlerine eşler.
_ETKI_TR = {
    "negligible": "ihmal edilebilir",
    "small": "küçük",
    "medium": "orta",
    "large": "büyük",
}


def _etki_ifadesi(value: float, kind: str) -> str:
    """Anlatıya eklenecek Türkçe etki büyüklüğü ibaresi (ör. 'orta düzeyde bir etki').
    Yalnızca büyüklüğü RAPOR eder; sonucun anlamını YORUMLAMAZ."""
    tr = _ETKI_TR.get(interpret_effect_size(value, kind), "")
    return f"{tr} düzeyde bir etki" if tr else ""


def _variant(key: str, variants: list) -> str:
    """Aynı `key` için her zaman aynı ifadeyi seçen, çalıştırmalar arası kararlı ifade
    rotasyonu. Yerleşik hash() str için tuzlandığından (PYTHONHASHSEED) yeniden
    üretilebilirliği bozar; bu yüzden md5 kullanılır."""
    digest = hashlib.md5(str(key).encode("utf-8")).hexdigest()
    return variants[int(digest, 16) % len(variants)]


def _format_df(df) -> str:
    """Serbestlik derecesi: tam sayıysa tam sayı, Welch gibi kesirliyse tek ondalık."""
    if df is None:
        return "—"
    if abs(df - round(df)) < 1e-6:
        return str(int(round(df)))
    return f"{df:.1f}"


def format_normality_narrative(var_name, skewness, kurtosis, sw_stat, sw_p) -> str:
    sw_fmt = format_stat(sw_stat, 3)
    p_fmt = format_p(sw_p)
    sk_fmt = format_stat(skewness, 3)
    ku_fmt = format_stat(kurtosis, 3)
    normal = sw_p > 0.05 and abs(skewness) < 2 and abs(kurtosis) < 7
    sonuc = "normal dağılıma işaret etmektedir" if normal else "normallik varsayımının ihlal edildiğine işaret etmektedir"
    return (
        f"{var_name} değişkeni normallik açısından incelenmiştir. "
        f"Çarpıklık ({sk_fmt}) ve basıklık ({ku_fmt}) değerleri gözden geçirilmiştir. "
        f"Shapiro-Wilk testi W = {sw_fmt}, p {p_fmt} sonucunu vermiş olup {sonuc}."
    )


def format_reliability_narrative(scale_name, n_items, alpha) -> str:
    alpha_fmt = format_stat(alpha, 3)
    if alpha < 0:
        return (
            f"{scale_name} ölçeği ({n_items} madde) negatif Cronbach alfa değeri "
            f"(α = {alpha_fmt}) üretmiştir; bu durum maddeler arasında negatif korelasyona "
            "işaret etmektedir. Ters puanlanan maddelerin doğru şekilde yeniden kodlandığını doğrulayınız."
        )
    yeterli = "kabul edilebilir" if alpha >= 0.70 else "yetersiz"
    return (
        f"{scale_name} ölçeği ({n_items} madde) {yeterli} düzeyde iç tutarlılık "
        f"sergilemiştir, α = {alpha_fmt}."
    )


def format_ttest_narrative(
    var_name, group_var, group_labels,
    n1, n2, mean1, sd1, mean2, sd2,
    t, df, p, d, levene_p,
) -> str:
    p_fmt = format_p(p)
    d_fmt = format_stat(abs(d), 2)
    lev_fmt = format_p(levene_p)
    df_fmt = _format_df(df)
    esit = (
        "eşit varyans varsayımı karşılanmıştır"
        if levene_p > 0.05
        else "eşit varyans varsayımı karşılanmamıştır"
    )
    if mean1 >= mean2:
        yuksek_etiket, yuksek_ort, yuksek_ss = group_labels[0], mean1, sd1
    else:
        yuksek_etiket, yuksek_ort, yuksek_ss = group_labels[1], mean2, sd2
    sig = "istatistiksel olarak anlamlıdır" if p < 0.05 else "istatistiksel olarak anlamlı değildir"
    etki = _etki_ifadesi(d, "d")

    giris = _variant(var_name, [
        f"Bağımsız örneklem t-testi ile {var_name} puanları {group_labels[0]} ve "
        f"{group_labels[1]} grupları arasında karşılaştırılmıştır.",
        f"{var_name} puanlarının {group_labels[0]} ve {group_labels[1]} grupları arasında "
        f"farklılaşıp farklılaşmadığı bağımsız örneklem t-testi ile incelenmiştir.",
        f"{group_var} değişkenine göre {var_name} puanlarındaki farklılıkları incelemek "
        f"amacıyla bağımsız örneklem t-testi uygulanmıştır.",
    ])
    betimsel = (
        f"Betimsel istatistikler {group_labels[0]} grubu için Ort = {mean1:.2f}, "
        f"SS = {sd1:.2f} (n = {n1}) ve {group_labels[1]} grubu için Ort = {mean2:.2f}, "
        f"SS = {sd2:.2f} (n = {n2}) olarak elde edilmiştir."
    )
    levene = f"Varyansların homojenliği Levene testiyle değerlendirilmiş; {esit} (p {lev_fmt})."
    sonuc = f"Gruplar arasındaki fark {sig}, t({df_fmt}) = {t:.2f}, p {p_fmt}, d = {d_fmt}"
    sonuc += f", {etki}." if etki else "."
    yuksek = (
        f"Ortalaması daha yüksek olan grup {yuksek_etiket} grubudur "
        f"(Ort = {yuksek_ort:.2f}, SS = {yuksek_ss:.2f})."
    )
    return f"{giris} {betimsel} {levene} {sonuc} {yuksek}"


def format_anova_narrative(
    var_name, group_var, k_groups,
    F, df_between, df_within, p, eta2,
    tukey_results=None,
) -> str:
    p_fmt = format_p(p)
    eta_fmt = format_stat(eta2, 3)
    sig = p < 0.05
    sig_ifade = "istatistiksel olarak anlamlıdır" if sig else "istatistiksel olarak anlamlı değildir"
    etki = _etki_ifadesi(eta2, "eta2")

    giris = _variant(var_name, [
        f"{group_var} değişkeninin {var_name} üzerindeki etkisini incelemek amacıyla "
        f"tek yönlü ANOVA uygulanmıştır.",
        f"{var_name} puanlarının {group_var} gruplarına göre farklılaşıp farklılaşmadığı "
        f"tek yönlü ANOVA ile test edilmiştir.",
        f"Tek yönlü ANOVA ile {var_name} puanları {group_var} grupları arasında "
        f"karşılaştırılmıştır.",
    ])
    sonuc = (
        f"Sonuç {sig_ifade}, F({_format_df(df_between)}, {_format_df(df_within)}) = "
        f"{F:.2f}, p {p_fmt}, η² = {eta_fmt}"
    )
    sonuc += f", {etki}." if etki else "."
    metin = f"{giris} {sonuc}"
    if sig and tukey_results is not None:
        metin += (
            " Tukey HSD post-hoc karşılaştırmaları anlamlı ikili farklılıklar "
            "olduğuna işaret etmektedir."
        )
    return metin


def format_correlation_narrative(var1, var2, r, p, n) -> str:
    r_fmt = format_stat(r, 2)
    p_fmt = format_p(p)
    df = n - 2  # korelasyon serbestlik derecesi: N - 2
    sig = "istatistiksel olarak anlamlı" if p < 0.05 else "istatistiksel olarak anlamlı olmayan"
    yon = "pozitif" if r > 0 else "negatif"
    etki = _etki_ifadesi(r, "r")
    son = f", {etki}." if etki else "."

    return _variant(f"{var1}|{var2}", [
        f"{var1} ile {var2} arasında {sig} {yon} yönde bir ilişki bulunmuştur, "
        f"r({df}) = {r_fmt}, p {p_fmt}{son}",
        f"{var1} ve {var2} değişkenleri arasındaki Pearson korelasyonu {sig} ve "
        f"{yon} yöndedir, r({df}) = {r_fmt}, p {p_fmt}{son}",
        f"Pearson korelasyon analizi {var1} ile {var2} arasında {sig} {yon} yönde bir "
        f"ilişkiye işaret etmektedir, r({df}) = {r_fmt}, p {p_fmt}{son}",
    ])


def format_mannwhitney_narrative(
    var_name, group_labels, n1, n2, mdn1, mdn2, u_stat, p, z=None,
) -> str:
    """Mann-Whitney U anlatısı (Türkçe, APA 7). z verilirse etki büyüklüğü
    r = Z/√N olarak RAPOR edilir; yalnızca büyüklük bildirilir, yorumlanmaz.
    Henüz canlı modüllere bağlanmadı — ikinci geçişte inferential.py'den çağrılacak."""
    p_fmt = format_p(p)
    sig = "istatistiksel olarak anlamlıdır" if p < 0.05 else "istatistiksel olarak anlamlı değildir"

    giris = _variant(var_name, [
        f"Normallik varsayımı karşılanmadığından {group_labels[0]} ve {group_labels[1]} "
        f"gruplarının {var_name} puanları Mann-Whitney U testiyle karşılaştırılmıştır.",
        f"{var_name} puanlarının {group_labels[0]} ve {group_labels[1]} grupları arasında "
        f"farklılaşıp farklılaşmadığı Mann-Whitney U testiyle incelenmiştir.",
    ])
    betimsel = (
        f"Betimsel olarak {group_labels[0]} grubunun ortancası Mdn = {mdn1:.2f} (n = {n1}), "
        f"{group_labels[1]} grubunun ortancası Mdn = {mdn2:.2f} (n = {n2}) bulunmuştur."
    )
    sonuc = f"Gruplar arasındaki fark {sig}, U = {u_stat:.0f}, p {p_fmt}"
    if z is not None:
        N = n1 + n2
        r = abs(z) / (N ** 0.5)
        etki = _etki_ifadesi(r, "r")
        sonuc += f", r = {format_stat(r, 2)}"
        if etki:
            sonuc += f", {etki}"
    sonuc += "."
    return f"{giris} {betimsel} {sonuc}"


def format_kruskal_narrative(
    var_name, group_var, k_groups, h_stat, df, p, n_total=None,
) -> str:
    """Kruskal-Wallis H anlatısı (Türkçe, APA 7). n_total verilirse etki büyüklüğü
    epsilon-kare (ε² = H / (N − 1); Tomczak & Tomczak, 2014) olarak RAPOR edilir;
    eta-kare eşikleriyle etiketlenir. Yalnızca büyüklük bildirilir, yorumlanmaz.
    Henüz canlı modüllere bağlanmadı — ikinci geçişte inferential.py'den çağrılacak."""
    p_fmt = format_p(p)
    sig = "istatistiksel olarak anlamlıdır" if p < 0.05 else "istatistiksel olarak anlamlı değildir"

    giris = _variant(var_name, [
        f"Normallik varsayımı karşılanmadığından {group_var} gruplarına göre {var_name} "
        f"puanları Kruskal-Wallis H testiyle karşılaştırılmıştır.",
        f"{var_name} puanlarının {group_var} grupları arasında farklılaşıp farklılaşmadığı "
        f"Kruskal-Wallis H testiyle incelenmiştir.",
    ])
    sonuc = f"Gruplar arasındaki fark {sig}, H({df}) = {h_stat:.2f}, p {p_fmt}"
    if n_total is not None and n_total > 1:
        epsilon2 = h_stat / (n_total - 1)
        etki = _etki_ifadesi(epsilon2, "eta2")
        sonuc += f", ε² = {format_stat(epsilon2, 3)}"
        if etki:
            sonuc += f", {etki}"
    sonuc += "."
    return f"{giris} {sonuc}"


def format_moderation_narrative(
    x_name, y_name, w_name,
    R2, F, df1, df2, p_model,
    b_interaction, se, t, p_int,
    ci_lower, ci_upper, delta_R2,
) -> str:
    R2_fmt = format_stat(R2, 3)
    p_model_fmt = format_p(p_model)
    b_fmt = format_stat(b_interaction, 3)
    se_fmt = format_stat(se, 3)
    t_fmt = f"{t:.2f}"
    p_int_fmt = format_p(p_int)
    ci_fmt = format_ci(ci_lower, ci_upper, 3)
    dR2_fmt = format_stat(delta_R2, 3)
    sig = p_int < 0.05
    return (
        f"{w_name} değişkeninin {x_name} ile {y_name} arasındaki ilişkiyi moderatör olarak "
        f"düzenleyip düzenlemediğini test etmek amacıyla PROCESS Makrosu Model 1 (Hayes, 2013) "
        f"çerçevesinde moderasyon analizi uygulanmıştır. X ve W değişkenleri etkileşim terimi "
        f"hesaplanmadan önce ortalama merkezleme işlemine tabi tutulmuştur (Hayes, 2013). "
        f"Tam model {'istatistiksel olarak anlamlı' if p_model < 0.05 else 'istatistiksel olarak anlamlı değil'} "
        f"bulunmuştur, R\u00b2 = {R2_fmt}, F({df1:.0f}, {df2:.0f}) = {F:.2f}, p {p_model_fmt}. "
        f"Etkileşim bloğunun modele katkısı \u0394R\u00b2 = {dR2_fmt} olarak hesaplanmıştır. "
        f"Etkileşim terimi {'anlamlı' if sig else 'anlamlı değil'} bulunmuştur, "
        f"B = {b_fmt}, SH = {se_fmt}, t = {t_fmt}, p {p_int_fmt}, 95% GA {ci_fmt} (OLS)."
    )


def format_conditional_effects_narrative(
    x_name, y_name, w_name,
    low_effect, low_p, mean_effect, mean_p, high_effect, high_p,
) -> str:
    def _ef(b, p):
        return f"B = {format_stat(b, 3)}, p {format_p(p)}"

    return (
        f"{w_name} değişkeninin farklı değerlerinde (ortalama merkezlenmiş W: "
        f"\u22121 SS, ortalama ve +1 SS) {x_name} değişkeninin {y_name} üzerindeki "
        f"basit eğim analizleri şu şekildedir: "
        f"W = ortalama \u2212 1 SS düzeyinde {_ef(low_effect, low_p)}; "
        f"W = ortalama düzeyinde {_ef(mean_effect, mean_p)}; "
        f"W = ortalama + 1 SS düzeyinde {_ef(high_effect, high_p)}."
    )
