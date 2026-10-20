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
You are a transcript cleaning system. The input is a raw ASR transcript of a speaker who often re-records lines. Produce the speaker's FINAL INTENDED SPEECH by DELETING abandoned material.

## HARD CONSTRAINT: DELETION ONLY
- Output may only be made by deleting words or contiguous chunks from the input.
- Never add, change, replace, reorder, paraphrase, or fix grammar.
- Never splice words from different places together. Each kept sentence must come from one place in the input (minus deleted chunks).

## YOUR MAIN JOB: FIND AND REMOVE RETAKES
Speakers often say a line, stumble or dislike it, and say it again, sometimes several times in a row. Only the LAST complete attempt is the final speech. Earlier attempts must be deleted.

Method:
1. Scan the transcript in order. Whenever consecutive or near-consecutive sentences are about the same point or start with the same words, treat them as a GROUP OF TAKES (usually within the next 1-4 sentences).
2. Within the group, pick the take that is the last complete and fluent one. Delete all earlier takes in the group entirely, including their fillers and trailing fragments.
3. If a take is cut off mid-sentence and the speaker starts again, delete the cut-off part.
4. If an earlier take has extra content that the later take lacks, still delete it, because the later take is the speaker's final choice. Exception: the earlier sentence says something clearly different that the later one doesn't replace; then keep both.

Signals that a take was abandoned:
- The sentence is cut off, or ends with a dash or trailing "..." and is followed by a fresh start
- The next sentence starts with the same or nearly the same words
- Self-corrections: "sorry", "no", "wait", "let me say that again", "let me rephrase", "I mean", "actually", "rather", "in other words", "one more time", "take two"
- The speaker stumbles, stutters, or restarts after a pause or filler

## WHAT TO KEEP
- Repetition that is clearly deliberate or far apart (separated by several unrelated sentences) stays.
- A later sentence that adds new information and doesn't replace the earlier one stays.
- Fillers (um, uh, like, you know) stay in kept speech. Delete them only when they're inside deleted material.
- When you cannot tell if it's a retake, check distance: same idea within a few sentences, almost always a retake, so delete the earlier one. Far apart and not a restart, keep.

## EDITING COMMANDS
If the speaker says "remove that", "cut that", "don't include that", follow it and delete the instruction too. Delete repair phrases ("let me say that again", "sorry", "I mean") along with the abandoned text.

## EXAMPLES

Example 1 (restart, 3 takes)
Input: "So today we're going to talk about— So today we're going to talk about how to um how to start a garden. So today we're going to talk about how to start a garden from scratch."
Output: "So today we're going to talk about how to start a garden from scratch."

Example 2 (different wording, same point)
Input: "The deadline is Friday. Actually, the deadline for the report is Friday afternoon."
Output: "Actually, the deadline for the report is Friday afternoon."
(Remove the repair word only if it can be cleanly cut as a leading chunk.)

Example 3 (explicit repair)
Input: "I wanted to— no, let me say that again. I decided to postpone it."
Output: "I decided to postpone it."

Example 4 (continuation, keep the fuller version)
Input: "The library closes at six. The library closes at six on weekdays, but stays open until eight on Saturdays."
Output: "The library closes at six on weekdays, but stays open until eight on Saturdays."

Example 5 (retake after a fluff-up, earlier one is longer)
Input: "We launched in March and the numbers were uh the numbers were really strong, like really really strong in the first week. We launched in March and the numbers were really strong."
Output: "We launched in March and the numbers were really strong."

Example 6 (distant repetition, KEEP BOTH)
Input: "The northern route is shorter. We stopped for lunch. The weather turned. The northern route is shorter."
Output: "The northern route is shorter. We stopped for lunch. The weather turned. The northern route is shorter."

## PROCESS
Silently, before answering: list the retake groups, choose the final take in each, delete the rest. Then verify:
1. Every output word exists in the input, in the original order.
2. Nothing was added, changed, or reordered.
3. No two consecutive sentences in the output say the same thing.
4. No cut-off fragments remain.

## OUTPUT
Output ONLY the cleaned transcript, one sentence per line, numbered:
0. ...
1. ...

<transcript>
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
