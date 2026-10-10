import srt
import re
import ffmpeg
from AutoVideoEditor.src.utilities import normalize
from AutoVideoEditor.src.transcription_manipulations.get_keep_parts.merge_intervals import merge_intervals
from AutoVideoEditor.src.transcription_manipulations.get_keep_parts.utils import gap_cost
from AutoVideoEditor.src.transcription_manipulations.get_keep_parts.utils import match_percentage
from AutoVideoEditor.src.transcription_manipulations.get_keep_parts.utils import is_taken_by_later_sentence
from AutoVideoEditor.src.transcription_manipulations.get_keep_parts.utils import transcription_sentence_to_words

def get_keep_parts():
    with open(
        "/content/raw_transcription_sentences.srt",
        "r",
        encoding="utf-8"
    ) as f:

        transcription_sentences = list(srt.parse(f.read()))

    with open(
        "/content/transcription.srt",
        "r",
        encoding="utf-8"
    ) as f:

        transcription_words = list(srt.parse(f.read()))


    with open(
        "/content/transcription_cleaned.txt",
        "r",
        encoding="utf-8"
    ) as f:
        clean_transcription_sentences = f.read()
        clean_transcription_sentences = re.split(
            r'(?:^\d+\.\s+|\n\d+\.\s+)',
            clean_transcription_sentences
        )
        clean_transcription_sentences = [
            x for x in clean_transcription_sentences
            if x != ''
        ]

    candidates_map = []
    for ci,clean_sentence in enumerate(clean_transcription_sentences):
        clean_words = normalize(clean_sentence).split(" ")
        candidates = []
        for i in range(0,len(transcription_sentences),1):
            candidate = {}
            normalized_raw_sentence_words = normalize(transcription_sentences[i].content).split(" ")
            candidate["clean_sentence_index"] = ci
            candidate["transcription_sentence_index"] = i
            candidate["gap_cost"] = gap_cost(clean_words,normalized_raw_sentence_words)
            candidate["match_percent"] = match_percentage(clean_words,normalized_raw_sentence_words)
            candidates.append(candidate)
        candidates.sort(
                key=lambda x: (
                -x["match_percent"],
              x["gap_cost"]["cost"]
            )
        )
        candidates_map.append(candidates)
    prime_candidates = [x[0] for x in candidates_map]
    final_sentences = []
    for isentencecandidates in candidates_map:
        for candidate in isentencecandidates:
            taken_status = is_taken_by_later_sentence(candidate,prime_candidates, clean_transcription_sentences)
            if taken_status == True:
                continue
            else:
                final_sentences.append(candidate)
                break;
    info = ffmpeg.probe("/content/video.mp4")
    duration = float(info["format"]["duration"])
    START_PADDING = 0.2
    END_PADDING = 0.3
    keep_intervals = []
    for final_sentence in final_sentences:
        if(final_sentence["gap_cost"]["cost"]==0 and final_sentence["match_percent"]==100):
            target = transcription_sentences[final_sentence["transcription_sentence_index"]]
            interval = [round(max(0,target.start.total_seconds()-START_PADDING),2), round(min(target.end.total_seconds()+END_PADDING,duration),2)]
            print(interval)
            keep_intervals.append([interval])
        elif(final_sentence["gap_cost"]["cost"]!=0):
            temp_interval = []
            sentence_subtitle_object = transcription_sentence_to_words(final_sentence["transcription_sentence_index"], transcription_sentences, transcription_words)
            for gap in final_sentence["gap_cost"]["indices"]:
                sentence_subtitle_object[gap[0]:gap[1]+1] = ["__"] * (gap[1]-gap[0]+1) 

            is_continuing = False
            
            for i_subtitle,subtitle in enumerate(sentence_subtitle_object):
                if(isinstance(subtitle,str)):
                    is_continuing = False
                    continue
                elif is_continuing:
                    temp_interval[-1][1] = subtitle.end.total_seconds()
                elif not is_continuing:
                    temp_interval.append([subtitle.start.total_seconds(),subtitle.end.total_seconds()])
                    is_continuing = True
            if temp_interval == []:
                continue
            temp_interval[0][0] = (round(max(0,temp_interval[0][0]-START_PADDING),2))
            temp_interval[-1][1] = (round(min(duration,temp_interval[-1][1]+END_PADDING),2))
            keep_intervals.append(temp_interval)
    keep_intervals = merge_intervals(keep_intervals)
    return keep_intervals

