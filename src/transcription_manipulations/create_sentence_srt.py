import srt
import re
from src.utilities import normalize

def create_sentence_srt(
    srt_path="/content/transcription.srt",
    transcription_path="/content/transcription.txt",
    output_path="/content/raw_transcription_sentences.srt"
):
    # ---------------------------------------------------------
    # 1. Read word-level SRT
    # ---------------------------------------------------------

    with open(srt_path, "r", encoding="utf-8-sig") as f:
        word_subtitles = list(srt.parse(f.read()))

    # ---------------------------------------------------------
    # 3. Read transcription
    # ---------------------------------------------------------

    with open(transcription_path, "r", encoding="utf-8") as f:
        transcript = f.read().strip()

    # ---------------------------------------------------------
    # 4. Split transcript into sentences
    # ---------------------------------------------------------

    sentences = re.split(r'(?<=[.!?])\s+', transcript)
    sentences = [s.strip() for s in sentences if s.strip()]
    print(sentences)
    # ---------------------------------------------------------
    # 5. Get cleaned SRT words
    # ---------------------------------------------------------

    srt_words = [
        sub.content.strip()
        for sub in word_subtitles
        if sub.content.strip()
    ]

    

    # ---------------------------------------------------------
    # 6. Match sentences to word timestamps
    # ---------------------------------------------------------

    srt_pointer = 0
    sentence_subtitles = []

    for sentence_index, sentence in enumerate(sentences, start=1):

        target_words = sentence.split()
        matched_subtitles = []

        for target_word in target_words:

            target_normalized = normalize(target_word)

            found = False

            for i in range(
                srt_pointer,
                min(srt_pointer + 6, len(srt_words))
            ):

                if normalize(srt_words[i]) == target_normalized:
                    matched_subtitles.append(word_subtitles[i])
                    srt_pointer = i + 1
                    found = True
                    break

            if not found:
                raise ValueError(
                    f"Could not match '{target_word}' "
                    f"while reconstructing sentence {sentence_index}. "
                    f"SRT pointer: {srt_pointer}"
                )

        # -----------------------------------------------------
        # IMPORTANT:
        # Build sentence text from the ACTUAL matched SRT words
        # -----------------------------------------------------

        sentence_content = " ".join(
            sub.content.strip()
            for sub in matched_subtitles
        )

        start = matched_subtitles[0].start
        end = matched_subtitles[-1].end

        sentence_subtitles.append(
            srt.Subtitle(
                index=sentence_index,
                start=start,
                end=end,
                content=sentence_content
            )
        )

    # ---------------------------------------------------------
    # 7. Write sentence SRT
    # ---------------------------------------------------------

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt.compose(sentence_subtitles))

    print(f"\nCreated {len(sentence_subtitles)} sentence subtitles.")
    print(f"Saved: {output_path}")

    return output_path