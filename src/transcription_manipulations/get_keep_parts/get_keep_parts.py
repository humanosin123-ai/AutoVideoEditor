import re
import srt
import ffmpeg
from AutoVideoEditor.src.utilities import normalize
from AutoVideoEditor.src.transcription_manipulations.get_keep_parts.merge_intervals import merge_intervals

# alignment scores
MATCH, MISMATCH, CLEAN_SKIP, RAW_GAP = 2, -3, -3, -1


def _align(cw, region, retake_tolerance):
    """
    Semi-global alignment: cw (clean tokens) must be fully consumed,
    region (raw tokens) can start/end anywhere. Match must end on the last clean word.
    Among end positions within `retake_tolerance` of the best score, the LATEST wins.
    Returns (normalized_score, [region indices of matched tokens]) or None.
    """
    m, n = len(cw), len(region)
    H = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        H[i][0] = H[i - 1][0] + CLEAN_SKIP
        ci, row, prev = cw[i - 1], H[i], H[i - 1]
        for j in range(1, n + 1):
            diag = prev[j - 1] + (MATCH if ci == region[j - 1] else MISMATCH)
            up = prev[j] + CLEAN_SKIP
            left = row[j - 1] + RAW_GAP
            row[j] = max(diag, up, left)

    last = cw[-1]
    cands = [(H[m - 1][j - 1] + MATCH, j) for j in range(1, n + 1) if region[j - 1] == last]
    if not cands:
        return None
    best = max(s for s, _ in cands)
    tol = retake_tolerance * m * MATCH
    j_end = max(j for s, j in cands if s >= best - tol)   # latest acceptable end
    score = H[m - 1][j_end - 1] + MATCH

    # traceback (prefers diagonal matches, i.e. the latest raw words)
    matched = [j_end - 1]
    i, j = m - 1, j_end - 1
    while i > 0 and j > 0:
        cur = H[i][j]
        equal = cw[i - 1] == region[j - 1]
        if cur == H[i - 1][j - 1] + (MATCH if equal else MISMATCH):
            if equal:
                matched.append(j - 1)
            i -= 1
            j -= 1
        elif cur == H[i][j - 1] + RAW_GAP:
            j -= 1
        else:
            i -= 1
    matched.reverse()
    return score / (m * MATCH), matched


def get_keep_parts(
    words_srt_path="/content/transcription.srt",
    cleaned_path="/content/transcription_cleaned.txt",
    video_path="/content/video.mp4",
    start_padding=0.2,
    end_padding=0.3,
    lookback_words=600,      # how far back from the current bound to search first (falls back to whole prefix)
    min_score=0.6,           # min normalized alignment score to accept a sentence
    retake_tolerance=0.05,   # how much worse a LATER take may score and still win (0 = only exact ties)
    min_cut_gap=0.0,         # unmatched gaps shorter than this (sec) are not cut out
):
    # ---------- load ----------
    with open(words_srt_path, "r", encoding="utf-8") as f:
        words = list(srt.parse(f.read()))

    with open(cleaned_path, "r", encoding="utf-8") as f:
        clean_sentences = re.split(r'(?:^\d+\.\s+|\n\d+\.\s+)', f.read())
        clean_sentences = [x.strip() for x in clean_sentences if x.strip() != ""]

    duration = float(ffmpeg.probe(video_path)["format"]["duration"])

    # ---------- flatten raw words into a token stream ----------
    # a SRT word may normalize to 0 or several tokens, so keep a token -> word index map
    stream, owner = [], []
    for wi, w in enumerate(words):
        for tok in normalize(w.content).split():
            stream.append(tok)
            owner.append(wi)

    clean_tokens = [normalize(s).split() for s in clean_sentences]

    # ---------- align from the END to the START (last retake wins) ----------
    spans = [None] * len(clean_tokens)
    upper = len(stream)  # exclusive bound: sentence k must end before sentence k+1 starts

    for k in range(len(clean_tokens) - 1, -1, -1):
        cw = clean_tokens[k]
        if not cw or upper <= 0:
            continue

        result = None
        for lo in sorted({max(0, upper - lookback_words), 0}, reverse=True):
            r = _align(cw, stream[lo:upper], retake_tolerance)
            if r and r[0] >= min_score:
                result = (r[0], [lo + x for x in r[1]])
                break

        if result is None:
            print(f"[WARN] clean sentence {k} not matched: {clean_sentences[k][:60]!r}")
            continue

        spans[k] = result
        upper = result[1][0]  # next (earlier) sentence must end before this one begins

    # ---------- matched tokens -> time intervals ----------
    keep_intervals = []
    for k, span in enumerate(spans):
        if span is None:
            continue
        score, tok_idx = span
        if score < 0.85:
            print(f"[INFO] low-confidence match {score:.2f} for sentence {k}: {clean_sentences[k][:60]!r}")

        word_idx = sorted({owner[t] for t in tok_idx})

        # group consecutive words into runs; non-matched words inside the span get cut
        runs = []
        for wi in word_idx:
            if runs and wi == runs[-1][1] + 1:
                runs[-1][1] = wi
            else:
                runs.append([wi, wi])

        intervals = []
        for a, b in runs:
            s, e = words[a].start.total_seconds(), words[b].end.total_seconds()
            if intervals and s - intervals[-1][1] < min_cut_gap:
                intervals[-1][1] = e
            else:
                intervals.append([s, e])

        # padding, clamped so it doesn't bleed into the neighbouring raw words (e.g. a discarded retake)
        first_w, last_w = runs[0][0], runs[-1][1]
        prev_end = words[first_w - 1].end.total_seconds() if first_w > 0 else 0.0
        next_start = words[last_w + 1].start.total_seconds() if last_w + 1 < len(words) else duration

        intervals[0][0] = min(intervals[0][0], max(intervals[0][0] - start_padding, prev_end, 0.0))
        intervals[-1][1] = max(intervals[-1][1], min(intervals[-1][1] + end_padding, next_start, duration))

        keep_intervals.append([[round(s, 2), round(e, 2)] for s, e in intervals])

    return merge_intervals(keep_intervals)