from google import genai
import os
from dotenv import load_dotenv
load_dotenv(override=True)

def clean_transcript(transcript_path):
    key = os.getenv("GEMINI_API_KEY")

    if not key:
        raise ValueError("GEMINI_API_KEY not found")

    client = genai.Client(api_key=key)

    with open(transcript_path, "r", encoding="utf-8") as f:
        transcription = f.read()

    prompt = f"""
You are a transcript cleaning system.

Reconstruct the speaker's FINAL INTENDED SPEECH from the raw ASR transcript.

## CORE RULE — DELETION ONLY

The output may ONLY be created by deleting words or contiguous chunks from the input.

NEVER:

* add, change, replace, or reorder words
* paraphrase or correct grammar
* combine separate attempts
* stitch words from different regions together
* try to cut single word(s) from a sentence unless very necessary.
Every output word must exist in the input and remain in its original order.

## RETAKES AND FALSE STARTS

Remove clearly abandoned speech, including:

* false starts
* immediate retakes
* self-corrections
* accidental repetitions
* incomplete thoughts that are immediately abandoned

A false start does NOT need to repeat any words.

Example:

Input:
"I wanted to explain the budget— [UM] let's look at the timeline first."

Output:
"Let's look at the timeline first."

The abandoned phrase can be completely different from the final attempt.

Example:

Input:
"The deadline is Friday. Actually, the deadline for the report is Friday afternoon."

Output:
"The deadline for the report is Friday afternoon."

## DO NOT OVER-CLEAN

Do NOT remove speech merely because:

* it sounds awkward
* it is grammatically incorrect
* it expresses an idea mentioned earlier
* it contains filler words
* it is semantically similar to another distant passage

Intentional repetition and explanation must be preserved.

When uncertain whether something was abandoned, KEEP it.

## EXPLICIT REPAIRS

When the speaker explicitly signals a replacement, such as:
"let me say that again", "let me rephrase that", "I mean", "no, what I mean is", "actually", "rather", or "in other words":

Treat the preceding abandoned formulation as deleted when the following speech clearly replaces it.

Keep the replacement speech.
Remove the repair instruction itself.

Example:
"I wanted to— no, let me say that again. I decided to postpone it."
→ "I decided to postpone it."

Example:
"The first option is— actually, let me rephrase that. The second option is safer."
→ "The second option is safer."

## REPETITION VS CONTINUATION

Do not automatically delete a passage just because it expresses a similar idea.

The key distinction is whether the later passage is:

* a genuinely new explanation → KEEP
* a continuation that adds meaningful information → KEEP
* a nearby reformulation that replaces the earlier attempt → DELETE the abandoned version
* a near-duplicate with no meaningful new information → DELETE the duplicate

Example of a continuation:

Input:
"The library closes at six.
The library closes at six on weekdays, but stays open until eight on Saturdays."

Output:
"The library closes at six on weekdays, but stays open until eight on Saturdays."

Example of a genuine repetition:

Input:
"The northern route is shorter.

Several unrelated sentences.

The northern route is shorter."

Output:
KEEP BOTH.

Example of a near-duplicate:

Input:
"I'll send the document tomorrow.
I'll send the document tomorrow."

Output:
"I'll send the document tomorrow."

When two nearby passages are highly similar, prefer the version that contains the speaker's complete intended information. Do not keep both merely because the second version contains a few additional words.

When uncertain whether a repetition is intentional or a retake, KEEP it.


## FILLERS

Keep fillers such as "um", "uh", "like", and "you know" when they belong to valid final speech.

If a filler occurs inside an abandoned passage, delete it with that passage.

## EDITING INSTRUCTIONS

If the speaker says things like "remove that", "cut that", or "don't include that", treat them as editing instructions, follow them, and remove the instruction itself.

## ORDER

Preserve the exact original chronological order.

Never combine separate transcript regions to create a better sentence.

**STRICT SOURCE-REGION PRESERVATION:**
Every output sentence must be derived exclusively from its original source sentence/region. You may delete words or contiguous chunks from that region, but you must never combine words from different source sentences/regions, even when they describe the same idea or one region appears to complete another. Use surrounding regions only to identify abandoned speech or retakes; never use them to complete, repair, or replace speech in another region. Preserve the original order of all retained words. If a sentence cannot be cleaned without borrowing words from another region, do not borrow them.


## VALIDATION

Before answering, verify:

1. Every output word exists in the input.
2. Nothing was added, changed, or reordered.
3. All clearly abandoned retakes and false starts are removed.
4. Intentional and distant repetitions are preserved.
5. The result can be produced from the input by deletion alone.
6. There is no consecutive repetition in final output.

Output ONLY the cleaned transcript.

Number each sentence:

0. ...
1. ...
2. ...

INPUT:
{transcription}

"""

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt
    )

    cleaned_transcription = response.text.strip()

    with open("/content/transcription_cleaned.txt", "w", encoding="utf-8") as f:
        f.write(cleaned_transcription)
        print(cleaned_transcription)

    return cleaned_transcription
