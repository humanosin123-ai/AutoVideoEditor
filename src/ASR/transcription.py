from crisperwhisper import CrisperWhisperModel
from AutoVideoEditor.src.utilities import format_srt_time
# Load the model once, outside the function
model = CrisperWhisperModel()

def transcribe(audio_path, language="en", output=False):

    result = model.transcribe(
        audio_path,
        language=language,
        mode="intended" if output else "verbatim",
        
        word_timestamps=True
    )

    # Build transcript from word timestamps
    transcript = " ".join(
        word.word.strip()
        for word in result.words
        if word.word.strip()
    )

    if output ==False:
        with open(
        "/content/transcription.txt",
        "w",
        encoding="utf-8"
        ) as f:
         f.write(transcript)



    with open(
        "/content/transcription.srt" if not output else "/content/transcript_output.srt",
        "w",
        encoding="utf-8"
        ) as f:

        subtitle_index = 1

        for word in result.words:

            text = word.word.strip()

            if not text:
                continue

            start = format_srt_time(word.start)
            end = format_srt_time(word.end)

            f.write(f"{subtitle_index}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{text}\n\n")

            subtitle_index += 1

    print("TRANSCRIPT:")
    print(transcript)
    print("\nSaved: /content/transcription.txt")
    print("Saved: /content/transcription.srt")

    return result