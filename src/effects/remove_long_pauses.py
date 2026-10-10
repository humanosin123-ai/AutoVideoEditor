import ffmpeg
import re
import os


def remove_long_pauses(
    input_video,
    output_video="output.mp4",
    min_pause=1.0
):
    print("=" * 80)
    print("REMOVE LONG PAUSES")
    print("=" * 80)

    print(f"Input video  : {input_video}")
    print(f"Output video : {output_video}")
    print(f"Min pause    : {min_pause:.2f}s")

    # ---------------------------------------------------------
    # Detect silence
    # ---------------------------------------------------------

    print("\n[1] Detecting long pauses...")
    print("-" * 80)

    result = (
        ffmpeg
        .input(input_video)
        .filter(
            "silencedetect",
            n="-35dB",
            d=min_pause
        )
        .output("null", format="null")
        .run(
            capture_stderr=True,
            capture_stdout=True
        )
    )

    log = result[1].decode("utf-8")

    starts = [
        float(x)
        for x in re.findall(
            r"silence_start: ([\d.]+)",
            log
        )
    ]

    ends = [
        float(x)
        for x in re.findall(
            r"silence_end: ([\d.]+)",
            log
        )
    ]

    print(f"Long pauses detected: {len(starts)}")

    for i, (start, end) in enumerate(zip(starts, ends), start=1):
        print(
            f"  Pause {i}: "
            f"{start:.3f}s -> {end:.3f}s "
            f"({end - start:.3f}s)"
        )

    if not starts:
        print("No long pauses detected.")
        print("Nothing to remove.")

    # ---------------------------------------------------------
    # Get video duration
    # ---------------------------------------------------------

    print("\n[2] Getting video duration...")
    print("-" * 80)

    probe = ffmpeg.probe(input_video)
    duration = float(probe["format"]["duration"])

    print(f"Video duration: {duration:.3f}s")

    # ---------------------------------------------------------
    # Build parts to KEEP
    # ---------------------------------------------------------

    print("\n[3] Building keep intervals...")
    print("-" * 80)

    keep_parts = []
    current = 0.0

    for i, (start, end) in enumerate(zip(starts, ends), start=1):

        if start > current:
            keep_parts.append((current, start))

            print(
                f"  KEEP {len(keep_parts)}: "
                f"{current:.3f}s -> {start:.3f}s "
                f"({start - current:.3f}s)"
            )

        print(
            f"  REMOVE pause {i}: "
            f"{start:.3f}s -> {end:.3f}s "
            f"({end - start:.3f}s)"
        )

        current = end

    # Keep everything after the final pause
    if current < duration:
        keep_parts.append((current, duration))

        print(
            f"  KEEP {len(keep_parts)}: "
            f"{current:.3f}s -> {duration:.3f}s "
            f"({duration - current:.3f}s)"
        )

    if not keep_parts:
        raise ValueError(
            "No audio/video content left after removing pauses."
        )

    print(f"\nTotal keep intervals: {len(keep_parts)}")

    # ---------------------------------------------------------
    # Create temporary clips
    # ---------------------------------------------------------

    print("\n[4] Creating video clips...")
    print("-" * 80)

    clips = []

    for i, (start, end) in enumerate(keep_parts):

        clip_path = f"/tmp/pause_clip_{i}.mp4"

        print(
            f"\nClip {i + 1}/{len(keep_parts)}"
        )
        print(
            f"  Start    : {start:.3f}s"
        )
        print(
            f"  End      : {end:.3f}s"
        )
        print(
            f"  Duration : {end - start:.3f}s"
        )
        print(
            f"  Output   : {clip_path}"
        )
        print("  Encoding...")

        (
            ffmpeg
            .input(
                input_video,
                ss=start,
                to=end
            )
            .output(
                clip_path,
                vcodec="libx264",
                acodec="aac"
            )
            .run(
                overwrite_output=True,
                quiet=True
            )
        )

        if os.path.exists(clip_path):
            size_mb = os.path.getsize(clip_path) / (1024 * 1024)

            print(
                f"  SUCCESS ({size_mb:.2f} MB)"
            )

            clips.append(clip_path)

        else:
            print("  ERROR: clip was not created!")

    print(
        f"\nSuccessfully created {len(clips)} clips."
    )

    if not clips:
        raise ValueError("No clips were created.")

    # ---------------------------------------------------------
    # Create concat file
    # ---------------------------------------------------------

    print("\n[5] Creating concat file...")
    print("-" * 80)

    concat_file = "/tmp/pause_concat.txt"

    with open(concat_file, "w") as f:
        for i, clip in enumerate(clips, start=1):
            f.write(f"file '{clip}'\n")
            print(f"  {i}. {clip}")

    # ---------------------------------------------------------
    # Concatenate
    # ---------------------------------------------------------

    print("\n[6] Concatenating clips...")
    print("-" * 80)

    print(f"Output: {output_video}")
    print("Encoding final video...")

    (
        ffmpeg
        .input(
            concat_file,
            format="concat",
            safe=0
        )
        .output(
            output_video,
            vcodec="h264_nvenc",
            acodec="aac"
        )
        .run(
            overwrite_output=True
        )
    )

    # ---------------------------------------------------------
    # Final result
    # ---------------------------------------------------------

    print("\n[7] COMPLETE")
    print("=" * 80)

    if os.path.exists(output_video):
        size_mb = os.path.getsize(output_video) / (1024 * 1024)

        print(f"Output file : {output_video}")
        print(f"Output size : {size_mb:.2f} MB")
        print("Long pauses successfully removed.")

    else:
        print("ERROR: output file was not created!")

    print("=" * 80)