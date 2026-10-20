import re
import srt
import ffmpeg
from functools import lru_cache
from difflib import SequenceMatcher
from AutoVideoEditor.src.utilities import normalize
from AutoVideoEditor.src.transcription_manipulations.get_keep_parts.merge_intervals import merge_intervals

START_PADDING = 0.2
END_PADDING = 0.3
MIN_SCORE = 0.85      # fraction of clean words that must be found
MAX_GAP = 3           # max extra raw words (stumbles) allowed between two clean words
LOOKBACK = 400        # how many tokens back from the bound to search
FUZZY = 0           # word similarity needed to count as equal


@lru_cache(maxsize=None)
def words_equal(a, b):
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= FUZZY


def match_from(clean, stream, start, limit):
    """Walk forward from `start`, matching clean words in order. Returns matched token indices."""
    matched = []
    ci, j = 0, start
    last_j = start          # position right after the last match
    gap = 0
    while ci < len(clean) and j < limit:
        if words_equal(clean[ci], stream[j]):
            matched.append(j)
            ci += 1
            j += 1
            last_j = j
            gap = 0
        else:
            gap += 1
            j += 1
            if gap > MAX_GAP:
                # this clean word isn't in the raw words, skip it and go back
                ci += 1
                j = last_j
                gap = 0
    return matched


def find_sentence(clean, stream, upper):
    """Search backward from `upper`, return the LATEST good match (list of token indices) or None."""
    lowest = max(0, upper - LOOKBACK)
    for start in range(upper - 1, lowest - 1, -1):
        if not words_equal(clean[0], stream[start]):
            continue
        matched = match_from(clean, stream, start, upper)
        if len(matched) / len(clean) >= MIN_SCORE:
            return matched
    return None


def get_keep_parts():
    # ---------- load ----------
    with open("/content/transcription.srt", "r", encoding="utf-8") as f:
        words = list(srt.parse(f.read()))

    with open("/content/transcription_cleaned.txt", "r", encoding="utf-8") as f:
        clean_sentences = re.split(r'(?:^\d+\.\s+|\n\d+\.\s+)', f.read())
        clean_sentences = [x for x in clean_sentences if x.strip() != ""]

    duration = float(ffmpeg.probe("/content/video.mp4")["format"]["duration"])

    # ---------- flatten words into tokens ----------
    stream, owner = [], []          # owner[t] = index of the SRT word that token t came from
    for wi, w in enumerate(words):
        for tok in normalize(w.content).split(" "):
            if tok:
                stream.append(tok)
                owner.append(wi)

    # ---------- match from last sentence to first ----------
    matches = [None] * len(clean_sentences)
    upper = len(stream)

    for k in range(len(clean_sentences) - 1, -1, -1):
        clean = [t for t in normalize(clean_sentences[k]).split(" ") if t]
        if not clean:
            continue

        matched = find_sentence(clean, stream, upper)
        if matched:
            matches[k] = matched
            upper = matched[0]      # earlier sentences must end before this one starts
            continue

        # fallback: search everywhere, but don't move `upper`
        matched = find_sentence(clean, stream, len(stream))
        if matched:
            print(f"[WARN] sentence {k} matched outside the order bound: {clean_sentences[k][:60]!r}")
            matches[k] = matched
        else:
            print(f"[WARN] sentence {k} not matched: {clean_sentences[k][:60]!r}")

    # ---------- tokens -> time intervals ----------
    keep_intervals = []
    for matched in matches:
        if not matched:
            continue

        word_idx = sorted({owner[t] for t in matched})

        # group consecutive SRT words into runs, gaps between runs are cut out
        runs = []
        for wi in word_idx:
            if runs and wi == runs[-1][1] + 1:
                runs[-1][1] = wi
            else:
                runs.append([wi, wi])

        intervals = [
            [words[a].start.total_seconds(), words[b].end.total_seconds()]
            for a, b in runs
        ]

        # padding, clamped so it doesn't leak into neighbouring (deleted) words
        first, last = runs[0][0], runs[-1][1]
        prev_end = words[first - 1].end.total_seconds() if first > 0 else 0.0
        next_start = words[last + 1].start.total_seconds() if last + 1 < len(words) else duration

        s = intervals[0][0]
        intervals[0][0] = min(s, max(s - START_PADDING, prev_end))
        e = intervals[-1][1]
        intervals[-1][1] = max(e, min(e + END_PADDING, next_start, duration))

        keep_intervals.append([[round(a, 2), round(b, 2)] for a, b in intervals])

    return merge_intervals(keep_intervals)