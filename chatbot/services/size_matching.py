"""Logic khusus soal ukuran: cocokkan angka cm/kg yang disebut user ke
size_chart jas, dan validasi/koreksi kalau LLM menyebut ukuran dengan
rentang cm/kg yang salah (halusinasi angka)."""
import re

from chatbot import state

_CM_RE = re.compile(r"(\d{2,3})\s*cm")
_KG_RE = re.compile(r"(\d{2,3})\s*kg")
_BERAT_TANPA_SATUAN_RE = re.compile(r"berat(?:\s*badan)?\s*(\d{2,3})")

UKURAN_TRIGGER_WORDS = ["ukuran", "size", "cocok pake", "pas pake", "pas nya"]

_RANGE_UNIT_RE = re.compile(r"(\d{2,3})\s*-\s*(\d{2,3})\s*(kg|cm)", re.IGNORECASE)


def _parse_range(s: str) -> tuple:
    lo, hi = s.split("-")
    return int(lo), int(hi)


def _match_sizes(size_chart: list, cm: int = None, kg: int = None) -> tuple:
    cm_matches, kg_matches = [], []
    for row in size_chart:
        lo_cm, hi_cm = _parse_range(row["lingkar_dada_cm"])
        lo_kg, hi_kg = _parse_range(row["berat_badan_kg"])
        if cm is not None and lo_cm <= cm <= hi_cm:
            cm_matches.append(row["ukuran"])
        if kg is not None and lo_kg <= kg <= hi_kg:
            kg_matches.append(row["ukuran"])
    return cm_matches, kg_matches


def try_size_answer(message: str) -> str | None:
    """Kalau pesan user nyebut angka cm dan/atau kg, jawab langsung pakai
    hasil pencocokan pasti ke size_chart jas. Return None kalau gak ada
    angka cm/kg yang kedetek di pesan (biar diserahin ke LLM seperti biasa)."""
    lower = message.lower()
    cm_num = _CM_RE.search(lower)
    kg_num = _KG_RE.search(lower) or _BERAT_TANPA_SATUAN_RE.search(lower)
    if not cm_num and not kg_num:
        return None

    size_chart = state.KB["produk"].get("jas", {}).get("size_chart", [])
    if not size_chart:
        return None

    cm = int(cm_num.group(1)) if cm_num else None
    kg = int(kg_num.group(1)) if kg_num else None
    cm_matches, kg_matches = _match_sizes(size_chart, cm=cm, kg=kg)

    if cm is not None and kg is not None:
        both = [s for s in cm_matches if s in kg_matches]
        if both:
            ukuran_txt = " atau ".join(both)
            return (
                f"Kalau lingkar dada {cm} cm dan berat {kg} kg, ukuran yang pas buat kamu itu {ukuran_txt} ya 👍 "
                f"Kalau masih ragu, boleh banget fitting langsung di toko biar makin yakin pasnya!"
            )
        if cm_matches and kg_matches:
            return (
                f"Dari lingkar dada {cm} cm sebenarnya masuk ukuran {'/'.join(cm_matches)}, tapi dari berat {kg} kg "
                f"lebih cocok ke ukuran {'/'.join(kg_matches)}. Beda dikit ini wajar karena bentuk badan tiap orang gak "
                f"selalu sama persis sama chart -- buat jas, biasanya lebih akurat patokan ke LINGKAR DADA-nya, tapi "
                f"paling aman tetap fitting langsung di toko ya biar pas beneran 😊"
            )

    if cm is not None and cm_matches:
        return f"Lingkar dada {cm} cm itu masuk ukuran {'/'.join(cm_matches)} ya."
    if kg is not None and kg_matches:
        return f"Berat {kg} kg itu masuk ukuran {'/'.join(kg_matches)} ya."

    if cm is not None or kg is not None:
        return (
            "Hmm, angkanya di luar rentang size chart kami nih 🙏 Boleh langsung chat admin ya biar dicariin "
            "solusi ukuran custom atau alternatifnya."
        )
    return None


def mentions_ukuran(message: str) -> bool:
    """Dipakai buat mutusin apakah jawaban LLM ke pesan ini perlu di-buffer
    dulu dan divalidasi (lihat validate_size_mentions), karena topiknya
    masih soal ukuran walau gak kena guard #1 di atas (mis. user nanya
    ukuran secara konsep, gak nyebut angka cm/kg eksplisit)."""
    lower = message.lower()
    return any(kw in lower for kw in UKURAN_TRIGGER_WORDS)


def validate_size_mentions(text: str) -> str:
    """Jaring pengaman terakhir: kalau jawaban LLM nyebut label ukuran (mis.
    "L") diikuti rentang angka cm/kg dalam beberapa kata setelahnya, angka
    itu dicocokkan ke size_chart asli. Kalau meleset (LLM ngarang angka
    mirip-mirip, kayak kasus nyata "L" dibilang "60-80 kg" padahal aslinya
    "70-80 kg"), angkanya diganti otomatis pakai angka yang benar dari data.
    Ini jaring pengaman, bukan pengganti guard #1 -- guard #1 tetap jalan
    duluan buat kasus yang paling sering terjadi (user nyebut cm/kg sendiri)."""
    if not state.SIZE_LABEL_RE or not state.SIZE_CHART_BY_LABEL:
        return text

    corrected = text
    for label_match in state.SIZE_LABEL_RE.finditer(text):
        label = label_match.group(1).upper()
        row = state.SIZE_CHART_BY_LABEL.get(label)
        if not row:
            continue
        window = text[label_match.end(): label_match.end() + 60]
        range_match = _RANGE_UNIT_RE.search(window)
        if not range_match:
            continue
        stated_lo, stated_hi, unit = range_match.group(1), range_match.group(2), range_match.group(3).lower()
        actual = row["lingkar_dada_cm"] if unit == "cm" else row["berat_badan_kg"]
        actual_lo, actual_hi = _parse_range(actual)
        if (stated_lo, stated_hi) != (str(actual_lo), str(actual_hi)):
            wrong_snippet = range_match.group(0)
            right_snippet = f"{actual_lo}-{actual_hi} {unit}"
            corrected = corrected.replace(wrong_snippet, right_snippet, 1)
    return corrected
