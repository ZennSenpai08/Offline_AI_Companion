"""Reference scoring is evaluation-only, never used to guide recognition."""
import re
import unicodedata
import wave


def normalize(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.findall(r"[^\W_]+", text, flags=re.UNICODE))


def distance(reference, actual):
    previous = list(range(len(actual) + 1))
    for i, expected in enumerate(reference, 1):
        row = [i]
        for j, received in enumerate(actual, 1):
            row.append(min(row[-1] + 1, previous[j] + 1, previous[j - 1] + (expected != received)))
        previous = row
    return previous[-1]


def score(reference, actual):
    reference, actual = normalize(reference), normalize(actual)
    words, hypothesis = reference.split(), actual.split()
    if not words:
        raise ValueError("Reference transcript must not be empty.")
    characters = reference.replace(" ", "")
    word_errors = distance(words, hypothesis)
    char_errors = distance(characters, actual.replace(" ", ""))
    return {"word_errors": word_errors, "reference_words": len(words), "wer": word_errors / len(words),
            "character_errors": char_errors, "reference_characters": len(characters), "cer": char_errors / len(characters)}


def read_pcm(path):
    with wave.open(str(path), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype()) != (1, 2, 16000, "NONE"):
            raise ValueError("Evaluation requires mono uncompressed 16-bit 16 kHz WAV.")
        if not 1600 <= source.getnframes() <= 400000:
            raise ValueError("Evaluation recordings must be 0.1–25 seconds.")
        pcm = source.readframes(source.getnframes())
        if len(pcm) != source.getnframes() * 2:
            raise ValueError("Truncated WAV data.")
        return pcm
