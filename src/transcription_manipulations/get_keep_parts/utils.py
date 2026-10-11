from difflib import SequenceMatcher
from AutoVideoEditor.src.utilities import normalize

def gap_cost(list1, list2):
    i = len(list1) - 1
    gaps = 0
    in_gap = False
    gap_end = None
    gap_indices = []

    for index in range(len(list2) - 1, -1, -1):
        word = list2[index]

        if i >= 0 and word == list1[i]:
            if in_gap:
                gap_indices.append([index + 1, gap_end])

            i -= 1
            in_gap = False

        else:
            if not in_gap:
                gaps += 1
                gap_end = index
                in_gap = True

    # If the sentence starts while still inside a gap
    if in_gap:
        gap_indices.append([0, gap_end])

    # We discovered gaps backwards, so restore chronological order
    gap_indices.reverse()

    return {
        "cost": gaps,
        "indices": gap_indices
    }

def match_percentage(list1, list2):
    if not list1:
        return 0

    i = 0

    for word in list2:
        if i < len(list1) and word == list1[i]:
            i += 1

    return (i / len(list1)) * 100

def is_similar(candidate, prime_candidate,clean_transcription_sentences):
        candidate_clean_transcript = clean_transcription_sentences[candidate["clean_sentence_index"]]
        prime_clean_transcript = clean_transcription_sentences[prime_candidate["clean_sentence_index"]]
        similarity = SequenceMatcher(None, candidate_clean_transcript, prime_clean_transcript).ratio() * 100
        if similarity >= 80:
            print(candidate.content + "  ______  "+ prime_candidate.content)
            return True
        else:
            return False


def is_taken_by_later_sentence(candidate,prime_candidates, clean_transcription_sentences):
        taken = False
        for prime_candidate in prime_candidates:
            if(candidate["transcription_sentence_index"]==prime_candidate["transcription_sentence_index"] and candidate["clean_sentence_index"]>prime_candidate["clean_sentence_index"] and is_similar(candidate,prime_candidate, clean_transcription_sentences)):
                print(candidate,prime_candidate["transcription_sentence_index"])
                taken = True
                break
        return taken


def transcription_sentence_to_words(sentence_index, transcription_sentences, transcription_words):
        
        start_index = 0
        for i in range(0,sentence_index,1):
            start_index = start_index + len(normalize(transcription_sentences[i].content).split())
        sentence_size = len(normalize(transcription_sentences[sentence_index].content).split())
        end_index = start_index + sentence_size
        selected_subtitles = transcription_words[start_index:end_index]
        return selected_subtitles