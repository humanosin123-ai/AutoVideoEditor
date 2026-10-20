import re
import srt
import ffmpeg
from functools import lru_cache
from difflib import SequenceMatcher
from AutoVideoEditor.src.utilities import normalize
from AutoVideoEditor.src.transcription_manipulations.get_keep_parts.merge_intervals import merge_intervals

START_PADDING = 0.2
END_PADDING = 0.3
MIN_SCORE = 0.85     # fraction of clean words that must be found
LOOKBACK = 400       # how many tokens back from the bound to search
FUZZY = 0.8          # word similarity needed to count as equal
ANCHORS = 3          # the sentence may start at any of its first N clean words
GAP_SPLIT = 6        # matched words further apart than this (in raw tokens) belong to different clusters
MIN_CLUSTER = 3      # a cluster with fewer matched words than this is treated as noise
MIN_CUT_GAP = 0.4    # seconds, gaps shorter than this are NOT cut out


@lru_cache(maxsize=None)
def words_equal(a, b):
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= FUZZY


def prune(matched, clean_len):
    """Drop isolated matches (common words picked up from neighbouring sentences)."""
    if not matched:
        return []
    clusters = [[matched[0]]]
    for t in matched[1:]:
        if t - clusters[-1][-1] - 1 > GAP_SPLIT:
            clusters.append([t])
        else:
            clusters[-1].append(t)
    need = min(MIN_CLUSTER, clean_len)
    return [t for c in clusters if len(c) >= need for t in c]


def match_from(clean, stream, start, limit):
    """Best in-order (LCS) match of `clean` inside a window of the stream starting at `start`."""
    end = min(limit, start + len(clean) * 2 + 5)
    window = stream[start:end]
    m, n = len(clean), len(window)

    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if words_equal(clean[i - 1], window[j - 1]):
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    matched = []
    i, j = m, n
    while i > 0 and j > 0:
        if words_equal(clean[i - 1], window[j - 1]) and dp[i][j] == dp[i - 1][j - 1] + 1:
            matched.append(start + j - 1)
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    matched.reverse()
    return matched


def find_sentence(clean, stream, upper, lookback=LOOKBACK, min_score=MIN_SCORE):
    """Search backward from `upper`, return the LATEST good match (token indices) or None."""
    lowest = 0 if lookback is None else max(0, upper - lookback)
    for start in range(upper - 1, lowest - 1, -1):
        for c in range(min(ANCHORS, len(clean))):
            if not words_equal(clean[c], stream[start]):
                continue
            matched = prune(match_from(clean[c:], stream, start, upper), len(clean))
            if len(matched) / len(clean) >= min_score:
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
            print(f"[WARN] sentence {k} is empty after normalize: {clean_sentences[k]!r}")
            continue

        matched = find_sentence(clean, stream, upper)
        if matched:
            matches[k] = matched
            upper = matched[0]      # earlier sentences must end before this one starts
            continue

        # fallback: search everywhere, but don't move `upper`
        matched = find_sentence(clean, stream, len(stream), lookback=None)
        if matched:
            print(f"[WARN] sentence {k} matched outside the order bound: {clean_sentences[k][:60]!r}")
            matches[k] = matched
        else:
            print(f"[WARN] sentence {k} not matched: {clean_sentences[k][:60]!r}")

    # ---------- report: where did each sentence land? ----------
    for k, m in enumerate(matches):
        sent = clean_sentences[k][:50]
        if not m:
            print(f"{k:3d} NO MATCH | {sent!r}")
        else:
            t0 = words[owner[m[0]]].start.total_seconds()
            t1 = words[owner[m[-1]]].end.total_seconds()
            print(f"{k:3d} {t0:8.2f}-{t1:8.2f} | {sent!r}")

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

        # don't cut out tiny gaps
        merged = [intervals[0]]
        for s_, e_ in intervals[1:]:
            if s_ - merged[-1][1] < MIN_CUT_GAP:
                merged[-1][1] = e_
            else:
                merged.append([s_, e_])
        intervals = merged

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