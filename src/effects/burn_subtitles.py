import os
import tempfile

from pycaps import CapsPipelineBuilder, TranscriptFormat, VideoQuality

DEFAULT_CSS = """
.word {
  font-family: Arial, sans-serif;
  font-size: 34px;
  font-weight: bold;
  color: white;
  text-shadow: 2px 2px 5px black;
}
.word-being-narrated {
  color: yellow;
}
"""


def burn_captions(
    input_video,
    srt_path,
    output_video="captioned.mp4",
    css_path=None,                 # your own CSS file, or None to use DEFAULT_CSS
    quality=VideoQuality.HIGH,
):
    if not os.path.isfile(input_video):
        raise FileNotFoundError(f"Video not found: {input_video}")
    if not os.path.isfile(srt_path):
        raise FileNotFoundError(f"SRT not found: {srt_path}")
    if os.path.abspath(input_video) == os.path.abspath(output_video):
        raise ValueError("output_video must be different from input_video")

    tmp_css = None
    try:
        if css_path is None:
            with tempfile.NamedTemporaryFile("w", suffix=".css", delete=False, encoding="utf-8") as f:
                f.write(DEFAULT_CSS)
                tmp_css = css_path = f.name

        pipeline = (
            CapsPipelineBuilder()
            .with_input_video(input_video)
            .with_output_video(output_video)
            .with_transcription_file(srt_path, TranscriptFormat.SRT)
            .with_video_quality(quality)
            .add_css(css_path)
            .build()
        )
        pipeline.run()
    finally:
        if tmp_css and os.path.exists(tmp_css):
            os.remove(tmp_css)

    if not os.path.exists(output_video):
        raise RuntimeError("Caption rendering finished but the output file was not created")
    return output_video