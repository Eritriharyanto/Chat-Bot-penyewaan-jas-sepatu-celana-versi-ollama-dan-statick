"""Klien streaming ke Ollama: kirim prompt, terima balasan token-per-token,
dan pecah jadi per-kalimat biar bisa langsung di-stream ke frontend."""
import json
import re

import requests

from chatbot.config import DEFAULT_MAX_TOKENS, DEFAULT_REPEAT_PENALTY, NUM_CTX, OLLAMA_URL
from chatbot.services.formatting import strip_markdown

_SENTENCE_END_RE = re.compile(r"[.!?]")


def stream_ollama_response(
    model: str,
    messages: list,
    temperature: float,
    repeat_penalty: float = DEFAULT_REPEAT_PENALTY,
    max_tokens: int = DEFAULT_MAX_TOKENS,
):
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": temperature,
            "num_ctx": NUM_CTX,
            "repeat_penalty": repeat_penalty,
            "num_predict": max_tokens,
        },
    }

    sentence_buffer = ""
    last_sentence = None
    try:
        with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line.decode("utf-8"))
                if chunk.get("done"):
                    break
                content = chunk.get("message", {}).get("content", "")
                if not content:
                    continue
                sentence_buffer += strip_markdown(content)

                while True:
                    match = _SENTENCE_END_RE.search(sentence_buffer)
                    if not match:
                        break
                    end = match.end()
                    sentence = sentence_buffer[:end]
                    sentence_buffer = sentence_buffer[end:]
                    normalized = sentence.strip().lower()
                    if normalized and len(normalized) > 15 and normalized == last_sentence:
                        return  # kalimat persis diulang -> stop, jangan yield lagi
                    if normalized:
                        last_sentence = normalized
                    yield sentence

        if sentence_buffer.strip():
            yield sentence_buffer
    except requests.exceptions.Timeout:
        yield (
            "⚠️ Ollama kelamaan mikir (lebih dari 1 menit), jadi dihentikan. "
            "Ini biasanya karena model masih loading pertama kali atau laptop "
            "lagi berat — coba tanya ulang, biasanya percobaan kedua lebih cepat."
        )
    except requests.exceptions.ConnectionError:
        yield (
            "⚠️ Tidak bisa terhubung ke Ollama. Pastikan Ollama sudah jalan "
            "(buka aplikasi Ollama atau jalankan `ollama serve`), lalu coba lagi."
        )
    except requests.exceptions.HTTPError as e:
        yield f"⚠️ Error dari Ollama: {e}. Pastikan model sudah ditarik, misalnya: `ollama pull {model}`."
