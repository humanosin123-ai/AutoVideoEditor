import re
import ffmpeg
def format_srt_time(seconds):

    milliseconds = round(seconds * 1000)

    hours = milliseconds // 3_600_000
    milliseconds %= 3_600_000

    minutes = milliseconds // 60_000
    milliseconds %= 60_000

    secs = milliseconds // 1000
    milliseconds %= 1000

    return (
        f"{hours:02}:{minutes:02}:{secs:02},"
        f"{milliseconds:03}"
    )

def normalize(word):
    print(word)
    return re.sub(r"[^\w'\s]", "", word.lower())

def extract_audio(video_path):

    output_audio = "/content/denoised.wav"

    (
        ffmpeg
        .input(video_path)
        .output(
            output_audio,
            vn=None,
            ar=48000,
            ac=1,
            acodec="pcm_s16le"
        )
        .overwrite_output()
        .run(
            capture_stdout=True,
            capture_stderr=True
        )
    )

    print("Done!")
    print("Audio:", output_audio)

    return output_audio