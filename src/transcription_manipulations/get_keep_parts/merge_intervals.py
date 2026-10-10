def merge_intervals(intervals, max_gap=0.2):
    
    if not intervals:
        return []
    merged = []
    last_end = None
    for sentence_intervals in intervals:
        
        if last_end is None:
            merged = [*sentence_intervals]
            last_end = merged[-1][1]
            continue
        if(sentence_intervals[0][0] - last_end <= max_gap and (last_end<=sentence_intervals[0][0] or sentence_intervals[0][1]>=last_end)):
            merged[-1][1] = sentence_intervals[0][1]
            merged.extend(sentence_intervals[1:])
            last_end = sentence_intervals[-1][1]
        else:
            merged.extend(sentence_intervals)
            last_end = sentence_intervals[-1][1]
        

    return merged
