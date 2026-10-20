import os
import re
import subprocess
import tempfile

import ffmpeg

_SILENCE_RE = re.compile(r"silence_(start|end):\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")


# ---------------------------------------------------------
# helpers
# ---------------------------------------------------------

def _ffmpeg_major_version():
    try:
        out = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        raise RuntimeError("ffmpeg was not found in PATH")
    m = re.search(r"ffmpeg version n?(\d+)", out)
    return int(m.group(1)) if m else 0


def _probe(input_video):
    try:
        info = ffmpeg.probe(input_video)
    except ffmpeg.Error as e:
        raise RuntimeError(f"ffprobe failed:\n{e.stderr.decode(errors='replace')}")
    duration = float(info["format"]["duration"])
    has_video = any(s["codec_type"] == "video" for s in info["streams"])
    has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
    return duration, has_video, has_audio


def _detect_pauses(input_video, duration, min_pause, noise_db):
    """Returns a list of (start, end) silences, handles silence that runs to the end of the file."""
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", input_video, "-vn",
        "-af", f"silencedetect=noise={noise_db}dB:d={min_pause}",
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        raise RuntimeError("Silence detection failed:\n" + proc.stderr[-2000:])

    pauses, pending = [], None
    for kind, value in _SILENCE_RE.findall(proc.stderr):
        value = float(value)
        if kind == "start":
            pending = max(0.0, value)
        elif pending is not None:
            pauses.append((pending, min(value, duration)))
            pending = None
    if pending is not None:                 # silence continues until the end of the file
        pauses.append((pending, duration))
    return pauses


def _build_cuts(pauses, duration, keep_pause, min_cut=0.05):
    """Shrink each pause to `keep_pause` seconds instead of removing it completely."""
    pad = keep_pause / 2
    cuts = []
    for s, e in pauses:
        cs = s if s <= 0.01 else s + pad                # pause at very start: nothing to keep before it
        ce = e if e >= duration - 0.05 else e - pad     # pause at very end: nothing to keep after it
        if ce - cs >= min_cut:
            cuts.append((cs, ce))
    return sorted(cuts)


def _cuts_to_keep(cuts, duration, min_keep=0.04):
    keep, cur = [], 0.0
    for cs, ce in cuts:
        if cs - cur >= min_keep:
            keep.append((cur, cs))
        cur = max(cur, ce)
    if duration - cur >= min_keep:
        keep.append((cur, duration))
    return keep


def _build_filter_script(keep):
    n = len(keep)
    parts = []
    if n > 1:
        vin = [f"[v{i}]" for i in range(n)]
        ain = [f"[a{i}]" for i in range(n)]
        parts.append(f"[0:v:0]split={n}" + "".join(vin))
        parts.append(f"[0:a:0]asplit={n}" + "".join(ain))
    else:
        vin, ain = ["[0:v:0]"], ["[0:a:0]"]

    for i, (s, e) in enumerate(keep):
        parts.append(f"{vin[i]}trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[vt{i}]")
        parts.append(f"{ain[i]}atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[at{i}]")

    inputs = "".join(f"[vt{i}][at{i}]" for i in range(n))
    parts.append(f"{inputs}concat=n={n}:v=1:a=1[v][a]")
    return ";\n".join(parts)


# ---------------------------------------------------------
# main function
# ---------------------------------------------------------

def remove_long_pauses(
    input_video,
    output_video="output.mp4",
    min_pause=1.0,       # only pauses at least this long are touched
    keep_pause=0.3,      # how much of each pause to leave (0 = remove completely)
    noise_db=-35,        # silence threshold
    use_gpu=True,        # try h264_nvenc first, fall back to libx264
):
    print("=" * 80)
    print("REMOVE LONG PAUSES")
    print("=" * 80)

    # ---------- validation ----------
    if not os.path.isfile(input_video):
        raise FileNotFoundError(f"Input video not found: {input_video}")
    if os.path.abspath(input_video) == os.path.abspath(output_video):
        raise ValueError("output_video must be different from input_video")
    if keep_pause < 0 or keep_pause >= min_pause:
        raise ValueError("keep_pause must be >= 0 and smaller than min_pause")

    out_dir = os.path.dirname(os.path.abspath(output_video))
    os.makedirs(out_dir, exist_ok=True)

    print(f"Input      : {input_video}")
    print(f"Output     : {output_video}")
    print(f"Min pause  : {min_pause:.2f}s | keep {keep_pause:.2f}s of each pause | threshold {noise_db}dB")

    # ---------- probe ----------
    duration, has_video, has_audio = _probe(input_video)
    print(f"Duration   : {duration:.3f}s")

    if not has_video:
        raise ValueError("Input has no video stream")
    if not has_audio:
        print("No audio stream, cannot detect pauses. Nothing to do.")
        return input_video

    # ---------- detect ----------
    print("\n[1] Detecting pauses...")
    pauses = _detect_pauses(input_video, duration, min_pause, noise_db)
    print(f"Pauses found: {len(pauses)}")

    cuts = _build_cuts(pauses, duration, keep_pause)
    if not cuts:
        print("Nothing to remove.")
        return input_video

    keep = _cuts_to_keep(cuts, duration)
    if not keep:
        raise ValueError("Nothing would be left after removing the pauses")

    removed = sum(ce - cs for cs, ce in cuts)
    print(f"Cuts: {len(cuts)} | removing {removed:.2f}s | new duration ~{duration - removed:.2f}s")
    for i, (cs, ce) in enumerate(cuts[:20], start=1):
        print(f"  CUT {i}: {cs:.3f}s -> {ce:.3f}s ({ce - cs:.3f}s)")
    if len(cuts) > 20:
        print(f"  ... and {len(cuts) - 20} more")

    # ---------- render (single pass, no intermediate files) ----------
    print("\n[2] Rendering...")
    script_text = _build_filter_script(keep)
    script_flag = "-/filter_complex" if _ffmpeg_major_version() >= 7 else "-filter_complex_script"

    root, ext = os.path.splitext(output_video)
    partial = f"{root}.partial{ext}"

    encoders = []
    if use_gpu:
        encoders.append(("h264_nvenc", ["-c:v", "h264_nvenc", "-rc", "vbr", "-cq", "23", "-b:v", "0"]))
    encoders.append(("libx264", ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]))

    script_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
            tf.write(script_text)
            script_path = tf.name

        success = False
        for name, venc in encoders:
            print(f"Encoding with {name}...")
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats",
                "-i", input_video,
                script_flag, script_path,
                "-map", "[v]", "-map", "[a]",
                *venc,
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
            ]
            if ext.lower() in (".mp4", ".mov", ".m4v"):
                cmd += ["-movflags", "+faststart"]
            cmd.append(partial)

            result = subprocess.run(cmd)
            if result.returncode == 0 and os.path.exists(partial) and os.path.getsize(partial) > 0:
                success = True
                break
            print(f"{name} failed, trying next encoder...")

        if not success:
            raise RuntimeError("Rendering failed with all encoders")

        os.replace(partial, output_video)

    finally:
        if script_path and os.path.exists(script_path):
            os.remove(script_path)
        if os.path.exists(partial):
            os.remove(partial)

    size_mb = os.path.getsize(output_video) / (1024 * 1024)
    print("\n[3] COMPLETE")
    print(f"Output file : {output_video} ({size_mb:.2f} MB)")
    print("=" * 80)
    return output_video