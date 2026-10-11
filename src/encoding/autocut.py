import ffmpeg
import os
import subprocess
import tempfile
import shutil

NVENC_OPTS = [
    "-c:v", "h264_nvenc", "-preset", "p4",
    "-rc", "vbr", "-cq", "23", "-b:v", "0",
    "-pix_fmt", "yuv420p",
]
CPU_OPTS = [
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
    "-pix_fmt", "yuv420p",
]


def _run(cmd, label):
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        print(f"\n{label} FAILED (return code {r.returncode})")
        print(r.stderr.decode(errors="replace")[-2000:])
    return r.returncode == 0


def autocut_video(video_path, merged_parts, out="/content/output.mp4"):
    print("=" * 60)
    print("AUTOCUT VIDEO")
    print("=" * 60)

    # 1. Probe
    info = ffmpeg.probe(video_path)
    duration = float(info["format"]["duration"])
    has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
    print(f"Duration: {duration:.2f}s | audio: {has_audio}")

    # 2. Clamp and validate intervals
    intervals = []
    for start, end in merged_parts:
        start, end = max(0, start), min(duration, end)
        if end - start > 0.05:  # skip empty/tiny intervals
            intervals.append((start, end))
    print(f"Valid intervals: {len(intervals)}")
    if not intervals:
        print("No valid intervals found.")
        return

    tmp = tempfile.mkdtemp(prefix="autocut_")
    encoder_opts = NVENC_OPTS
    seg_files = []

    try:
        # 3. Cut each interval separately
        for i, (start, end) in enumerate(intervals):
            seg = os.path.join(tmp, f"seg_{i:05d}.mp4")

            def build(opts):
                cmd = ["ffmpeg", "-y", "-v", "error",
                       "-ss", f"{start:.3f}", "-i", video_path,
                       "-t", f"{end - start:.3f}"]
                cmd += opts
                if has_audio:
                    cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
                else:
                    cmd += ["-an"]
                return cmd + [seg]

            ok = _run(build(encoder_opts), f"Segment {i + 1}")
            if not ok and encoder_opts is NVENC_OPTS:
                print("NVENC failed, switching to libx264 for the rest.")
                encoder_opts = CPU_OPTS
                ok = _run(build(encoder_opts), f"Segment {i + 1} (CPU)")
            if not ok:
                raise RuntimeError(f"Could not encode segment {i + 1}")

            seg_files.append(seg)
            print(f"  segment {i + 1}/{len(intervals)} done "
                  f"({start:.2f}s -> {end:.2f}s)")

        # 4. Join segments (video copied, audio re-encoded to avoid clicks)
        list_file = os.path.join(tmp, "list.txt")
        with open(list_file, "w") as f:
            for p in seg_files:
                f.write(f"file '{p}'\n")

        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
               "-i", list_file, "-c:v", "copy"]
        cmd += ["-c:a", "aac", "-b:a", "192k"] if has_audio else ["-an"]
        cmd += ["-movflags", "+faststart", out]

        if not _run(cmd, "Concat"):
            raise RuntimeError("Concat failed")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    size_mb = os.path.getsize(out) / (1024 * 1024)
    print(f"\nDONE: {out} ({size_mb:.2f} MB)")
    return out