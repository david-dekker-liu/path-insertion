import numpy as np
import pandas as pd
from datetime import datetime
from datetime import timedelta
import free_space_detection
import timetable_creation

# TODO Test first if it is a predefined exception,
# TODO i.e., single-track line with smaller blocks.


# Interpolate one time ... guess I did need it after all
def interpolate_single_time(start, end, start_range, new_time):
    return start_range[0] + ((new_time - start).seconds / (end - start).seconds) * (start_range[1] - start_range[0])

# Linearly interpolate the start_range at the origin when the interval is shortened
def update_time_range(start, end, newstart, newend, linear, start_range):
    if not linear:
        raise Exception("Constant functionality deprecated")

    if newstart < start or newend < start or newend > end or newstart > end or newend < newstart:
        raise Exception("The new time window is not contained in the old one.")

    new_startrange_start = interpolate_single_time(start, end, start_range, newstart)
    new_startrange_end = interpolate_single_time(start, end, start_range, newend)
    # new_startrange_start = start_range[0] + ((newstart - start).seconds / (end - start).seconds) * (start_range[1] - start_range[0])
    # new_startrange_end = start_range[0] + ((newend - start).seconds / (end - start).seconds) * (start_range[1] - start_range[0])

    return new_startrange_start, new_startrange_end


# Plainly intersects an interval list with a set of free spaces
# Returns the modified interval list
def intersect(first_free_spaces, intersection_list):
    print("free spaces", first_free_spaces)
    print("intersection lists", intersection_list)
    intersected = []
    for interval in first_free_spaces:
        print(interval)
        start = interval[0]
        end = interval[1]
        original_interval_start = interval[2]
        original_interval_end = interval[3]

        # Continue splitting this interval as long as to-be-intersected is not completely after it
        # Notice: we ignore intervals that contain a single time stamp here!
        # (otherwise we do get a mess when trying to allow the 'relevant' cases, but avoiding the non-relevant cases...)

        while len(intersection_list) > 0 and intersection_list[0][0] < end:
            # If to-be-intersected free-space is completely before first-free-space, ignore it
            if intersection_list[0][1] < start:
                intersection_list = intersection_list[1:]
                continue

            # If free space starts before, were happy and filter until end
            if intersection_list[0][0] <= start and intersection_list[0][1] <= end:
                new_departure_range = update_time_range(start, end, start, intersection_list[0][1], True, (original_interval_start, original_interval_end))
                intersected += [(start, intersection_list[0][1], new_departure_range[0], new_departure_range[1])]
                intersection_list = intersection_list[1:]
            elif intersection_list[0][0] <= start and intersection_list[0][1] >= end:
                intersected += [(start, end, original_interval_start, original_interval_end)]
                intersection_list = [(end, intersection_list[0][1])] + intersection_list[1:]
            elif intersection_list[0][1] <= end:
                new_departure_range = update_time_range(start, end, intersection_list[0][0], intersection_list[0][1], True, (original_interval_start, original_interval_end))
                intersected += [(intersection_list[0][0], intersection_list[0][1], new_departure_range[0], new_departure_range[1])]
                intersection_list = intersection_list[1:]
            else:
                new_departure_range = update_time_range(start, end, intersection_list[0][0], end, True, (original_interval_start, original_interval_end))
                intersected += [(intersection_list[0][0], end, new_departure_range[0], new_departure_range[1])]
                intersection_list = [(end, intersection_list[0][1])] + intersection_list[1:]

    return intersected


# Merge intervals when obtaining a list of all 'candidate interval lists' arriving from different tracks
# Returns one interval list
def merge_intervals(list_of_intervals):
    # Input is a list of lists of quadruples, i.e., start-end-origstart-origend
    # We will again return such a list of tuples

    # Get all event time stamps and the interval where they belong to
    all_start_times = [(j[0], i) for i, quadruple_list in enumerate(list_of_intervals) for j in quadruple_list]
    all_end_times = [(j[1], i) for i, quadruple_list in enumerate(list_of_intervals) for j in quadruple_list]

    # Get events and sort them
    events = all_start_times + all_end_times
    events.sort(key=lambda x: x[0])
    # Keep track of which intervals are active (when iterating over time) and a pointer to the current one
    active_intervals = []
    active_interval_pointer = dict(list(enumerate([0] * len(list_of_intervals))))

    # Iterate over all events. If we progress in time, then we have some interval where we want to determine the latest departure times.
    # Add this interval to the output
    last_event = 0
    output = []

    for event, list_id in events:
        # If we reach a new event time point, we find the relevant max dep times over the last interval
        if event != last_event and len(active_intervals) > 0:
            actual_intervals = []
            # Determine all active intervals in actual_intervals
            for j in active_intervals:
                actual_intervals += [(j, list_of_intervals[j][active_interval_pointer[j]])]
            # Determine the intervals when restricted to the current time window
            exact_actual_intervals_with_ = [
                (j, last_event, event, update_time_range(i[0], i[1], last_event, event, True, (i[2], i[3]))[0], update_time_range(i[0], i[1], last_event, event, True, (i[2], i[3]))[1]) for j, i in actual_intervals
            ]

            # Find min and max departure time
            relevant_start_time = max(exact_actual_intervals_with_, key=lambda item: item[3])
            relevant_end_time = max(exact_actual_intervals_with_, key=lambda item: item[4])

            # We may need to split up the interval if there are two different maxima at this interval
            if relevant_start_time[3] != relevant_end_time[3] or relevant_start_time[4] != relevant_start_time[4]:
                raise Exception("Need to fix this case lol", relevant_start_time, relevant_end_time)

            # Add the obtained interval to the output
            output += [(last_event, event, relevant_start_time[3], relevant_start_time[4])]

            print(relevant_start_time, "\n", relevant_end_time, "\n")

        # Update last event, the active intervals and the pointers to the actual active ones within those
        last_event = event

        if list_id not in active_intervals:
            active_intervals += [list_id]
        else:
            active_interval_pointer[list_id] = active_interval_pointer[list_id] + 1
            active_intervals.remove(list_id)

    # Last interval. We need to keep track in case two consecutive ones should be merged
    last_start = 0
    last_end = 0
    last_orig_start = 0
    last_orig_end = 0
    last_ratio = 0
    combined_output = []

    for start, end, orig_start, orig_end in output:
        # No single value intervals
        if start == end:
            raise Exception("No single value intervals allowed.")

        # Ignore initial interval
        if last_start == 0:
            last_start = start
            last_end = end
            last_orig_start = orig_start
            last_orig_end = orig_end
            last_ratio = (orig_end - orig_start).seconds / (end - start).seconds
            continue

        ratio = (orig_end - orig_start).seconds / (end - start).seconds

        # If two intervals should be merged, merge them by changing the last remembered interval
        if last_end == start and last_orig_end == orig_start and close(ratio, last_ratio):
            last_end = end
            last_orig_end = orig_end
        # Otherwise, add last interval to the output
        else:
            combined_output += [(last_start, last_end, last_orig_start, last_orig_end)]
            last_start = start
            last_end = end
            last_orig_start = orig_start
            last_orig_end = orig_end
            last_ratio = (orig_end - orig_start).seconds / (end - start).seconds

    combined_output += [(last_start, last_end, last_orig_start, last_orig_end)]
    print(combined_output)
    #  [       ]      [               ]
    #    [   ]     []
    #      [             ]
    # ==> List of all 'events'. Between each pair of events, take all relevant intervals
    # ( == the first intervals of those opened)

    # Maintain which sources are 'active' while scanning the events: e.g. 1 True, 2 False, etc.
    # At each event, toggle the (possible multiple) rows
    # Get all (projected!) orig-ranges, find the max start and max end time (hopefully corresponding to same interval...)
    # if not... find intersection (aargh) and ignore a possible 3rd optimal segment in the middle
    # Notice: and that is perfectly fine, as the slope is either constant, or has a nice one-to-one correspondence

    return combined_output


def close(x, y):
    return -0.000001 <= x - y <= 0.000001


# Link an interval list on a segment track to the free spaces on that segment track
# Returns a dict from each free space (key) to a list of all intervals that should be evaluated within this free space
# def link_with_segments(list_of_intervals, free_space_list):
#     return list_of_intervals, free_space_list


# List of intervals is a list of quadruples (start, end, orig_start, orig_end)
# Free spaces is a list of pairs of pairs... Good design choices lol
def evaluate_running_times(list_of_intervals, free_spaces, d):
    free_spaces_first_column = [x[0] for x in free_spaces]
    intersected_intervals = intersect(list_of_intervals, free_spaces_first_column)

    for i in range(len(intersected_intervals)):
        interval = intersected_intervals[i]

        # ... kansloos ...
        while free_spaces[0][0][1] <= interval[0]:
            free_spaces = free_spaces[1:]

        free_space = free_spaces[0]

        ideal_new_start = interval[0] + timedelta(0, d)
        ideal_new_end = interval[1] + timedelta(0, d)

        # If the new start is within the free space, we can derive the new start of the interval easily
        if free_space[1][0] <= ideal_new_start <= free_space[1][1]:
            new_start = ideal_new_start
            old_start = interval[0]
            new_orig_start = interval[2]
        # If it is before, we can only start at the free space start
        elif ideal_new_start <= free_space[1][0] <= free_space[1][1]:
            new_start = free_space[1][0]
            old_start = new_start - d
            new_orig_start = interpolate_single_time(interval[0], interval[1], (interval[2], interval[3]), old_start)
        # Otherwise no point in doing anything

        # Analogous case for the end time...
        if i < len(intersected_intervals) - 1:
            next_interval = intersected_intervals[i+1]
            # TODO bonus interval bepalen





# def merge_runthrough_stop(list_of_intervals_from_runthrough, list_of_intervals_from_stop):
#     return list_of_intervals_from_runthrough, list_of_intervals_from_stop


def get_segment_type_from_row(row):
    return get_segment_type_from_values(row["dest"], row["track_id"])


def get_segment_type_from_values(dest, track_id):
    # dest is Nan if station
    # otherwise, track_id is E if single track
    if pd.isnull(dest):
        return "station"
    if "E" in track_id:
        return "single_block_segment"

    return "multiple_block_segments"


# Returns a dictionary from (station, segment) or (segment, station) and track_id
# to a list with all allowed track_id's to arrive on
# TODO merge with a list of deviations
def get_allowed_movements_at_arrival():
    # WARNING special value for None keys: nananan
    # Notice the sorting on time_end: the start station (with NaN time_start) is now put at the start
    # Filter away all combinations of end first train + start next train
    df = pd.read_csv("../data/t21.csv", sep=",")
    df = df.replace(np.nan, "nananan")
    df = df[["train_ix", "orig", "dest", "time_start", "time_end", "track_id", "ordinal"]]
    df = df.sort_values(["train_ix", "time_end", "ordinal"])
    df_merged = pd.concat([df, df.shift(-1).add_prefix("next_")], axis=1)
    df_merged = df_merged[df_merged["train_ix"] == df_merged["next_train_ix"]]

    df_merged = df_merged.drop_duplicates(["orig", "dest", "next_orig", "next_dest", "track_id", "next_track_id"])
    df_merged = df_merged.groupby(["orig", "dest", "next_orig", "next_dest", "track_id"], dropna=False, as_index=False).agg({"next_track_id": lambda x: list(x)})

    possible_movements_dict = {}
    for index, row in df_merged.iterrows():
        possible_movements_dict[(row["orig"], row["dest"], row["next_orig"], row["next_dest"], row["track_id"])] = row["next_track_id"]
        if pd.isnull(row["dest"]) and pd.isnull(row["next_dest"]):
            print("Detected impossible movement")
            print(row["orig"], row["dest"], row["next_orig"], row["next_dest"], row["track_id"], row["next_track_id"])
            # raise Exception

    return possible_movements_dict


# Assumes "E" means there is 1 track available so single-track
# Assumes key structure orig-dest_trackid and loc/trackid
def is_key_single_track(input_key):
    if "_" not in input_key:
        return False
    return "E" in input_key.rsplit("_", 1)[1]


def is_pair_single_track(orig, dest, all_keys):
    for seg_key in all_keys:
        if get_key(orig, dest, "E") in seg_key:
            return True
    return False


# Returns a string to index each segment with
# for double-track the direction matters, for single track it does not
def get_key(orig, dest, track_id):
    if pd.isnull(dest):
        return orig + "/" + track_id
    return min(orig, dest) + "-" + max(orig, dest) + "_" + track_id


def get_transition_key(orig, dest, station_track_id, segment_track_id, arriving):
    return orig + "=" + dest + "+" + str(station_track_id) + "=" + str(segment_track_id) + "&" + str(arriving)


# For each track number of a segment, one orientation is picked
# For double-track, this is the "logical" orientation (TODO verify: is it?),
# for single-track, an arbitrary orientation is chosen,
# so that is the only occasion where an (oriented) segment may not be found (TODO verify again)
def get_segment_track_list(df, loc_from, loc_to):
    expected_result = df[(df["stn_id_from"] == loc_from) & (df["stn_id_to"] == loc_to)]["line_track_id"].tolist()
    if len(expected_result) != 0:
        return expected_result
    else:
        return df[(df["stn_id_to"] == loc_from) & (df["stn_id_from"] == loc_to)]["line_track_id"].tolist()


# Returns all track ids that are used in a station in input dataframe
# Only considers first station in pairs
def get_station_track_list(df, loc):
    expected_result = df[(df["orig"] == loc) & (df["dest"].isnull())]["track_id"].tolist()
    return expected_result


if __name__ == '__main__':
    # Time frame to be considered
    TIME_FROM = "2021-05-10 20:00"
    TIME_TO = "2021-05-12 10:00"
    TIME_FROM_DATETIME = datetime.strptime(TIME_FROM, "%Y-%m-%d %H:%M")
    TIME_TO_DATETIME = datetime.strptime(TIME_TO, "%Y-%m-%d %H:%M")

    # Manual list of vertices to be explored
    # Derive the filtered t21 timetable, export it and detect Parallelfahrts
    vertices = ["Lp", "Lgm", "Gi", "Nh", "Kms", "Fi", "Nr", "Nrgb", "Åby", "Gtå", "Kon", "Åba", "Jår", "Ebg", "Nk", "Ssa", "Tba", "Lre", "Vhd", "Hlö", "Jn"]

    t21 = timetable_creation.get_timetable(TIME_FROM, TIME_TO, vertices)
    t21.to_csv("../data/filtered_t21.csv", sep=";")

    # timetable_creation.verify_timetable_consistency(t21)

    train_to_insert = 6424
    free_space_dict = free_space_detection.get_free_spaces(t21, train_to_insert, TIME_FROM_DATETIME, TIME_TO_DATETIME)

    # For each single-track segment, obtain the free-space list
    # The free_space_dict maps from segment keys to a list of free slots
    # In the single track case, these are rectangles indicated by their start- and endtime
    train_route = ["Lp", "Lgm", "Gi", "Nh", "Kms", "Fi", "Nr", "Nrgb", "Åby", "Gtå", "Kon", "Åba", "Jår", "Ebg", "Nk", "Ssa", "Tba", "Lre", "Vhd", "Hlö", "Jn"]

    usable_tracks = {("Lp", "Lgm"): ["U"], ("Lgm", "Gi"): ["U"], ("Gi", "Nh"): ["U"], ("Nh", "Kms"): ["U"], ("Kms", "Fi"): ["U"], ("Fi", "Nr"): ["U"], ("Nr", "Nrgb"): ["U"], ("Nrgb", "Åby"): ["U"], ("Åby", "Gtå"): ["E"], ("Gtå", "Kon"): ["E"], ("Kon", "Åba"): ["E"], ("Åba", "Jår"): ["E"], ("Jår", "Ebg"): ["E"], ("Ebg", "Nk"): ["E"], ("Nk", "Ssa"): ["E"], ("Ssa", "Tba"): ["E"], ("Tba", "Lre"): ["E"], ("Lre", "Vhd"): ["E"], ("Vhd", "Hlö"): ["E"], ("Hlö", "Jn"): ["E"]}

    print(free_space_dict.keys())
    first_loc = train_route[0]

    station_parked_occupations = {}
    station_runthrough_occupations = {}

    candidate_track_occupations = {}
    segment_track_occupations_at_start = {}
    segment_track_occupations_at_end = {}
    allowed_movements_at_arrival = get_allowed_movements_at_arrival()

    # Initialize the dynamic-ish program at the start location
    # Initial run-through is impossible, all free spaces at all tracks give possible departures
    for station_track in get_station_track_list(t21, first_loc):
        station_parked_occupations[(first_loc, station_track)] = [(x[0], x[1], x[0], x[1]) for x in free_space_dict[get_key(first_loc, None, station_track)]]
        station_runthrough_occupations[(first_loc, station_track)] = []

    # Now traverse all given segments
    for count in range(len(train_route) - 1):
        # Identify segment
        current_vertex = train_route[count]
        next_vertex = train_route[count+1]

        # Determine for each segment track, when you can enter that track
        # i.e. these dicts contain a list of interval lists for each segment track
        # After merging, they become an interval list
        entering_main_segment_candidates_after_stop = {}
        entering_main_segment_candidates_after_runthrough = {}
        entering_station_candidates_towards_stop = {}
        entering_station_candidates_towards_runthrough = {}

        # First, intersect track possibilities with transition free spaces
        for station_track in get_station_track_list(t21, current_vertex):
            # Filter the theoretically possible tracks by the allowed tracks (i.e., only use U northbound)
            allowed_next_tracks = [v for v in allowed_movements_at_arrival[(current_vertex, "nananan", current_vertex, next_vertex, station_track)] if v in usable_tracks[(current_vertex, next_vertex)]]

            for next_track in allowed_next_tracks:
                if next_track not in entering_main_segment_candidates_after_stop.keys():
                    entering_main_segment_candidates_after_stop[next_track] = []
                    entering_main_segment_candidates_after_runthrough[next_track] = []

                entering_main_segment_candidates_after_stop[next_track] += [intersect(station_parked_occupations[(current_vertex, station_track)], free_space_dict[get_transition_key(current_vertex, next_vertex, station_track, next_track, False)])]

                entering_main_segment_candidates_after_runthrough[next_track] += [intersect(station_runthrough_occupations[(current_vertex, station_track)], free_space_dict[
                    get_transition_key(current_vertex, next_vertex, station_track, next_track, False)])]

        # Then, modify the dictionary entries by merging the list of interval lists to one interval list
        for next_track in entering_main_segment_candidates_after_stop.keys():
            entering_main_segment_candidates_after_stop[next_track] = merge_intervals(entering_main_segment_candidates_after_stop[next_track])

            entering_main_segment_candidates_after_runthrough[next_track] = merge_intervals(entering_main_segment_candidates_after_runthrough[next_track])

        # Now extend this for the segments
        # Start from the segment free spaces, and map each segment free space to a (possibly empty) list of time intervals to enter the segment
        # Perhaps (is this needed?) make sure that the corr starting times are strictly increasing, so remove any bit that is below two other values.
        # E.g.: if one interval is 8-11 and a later one has starting times 10-16, drop 10-11 of the second one, as you could also start at 11 and get there at that time

        # Now duplicate both to get such a mapping for all four stopping patterns
        # Then extrapolate each segment free space (i.e. add min running time)
        # If no interval is present after the segment, add a bonus "slow moving" segment with constant departure time.

        for next_track in entering_main_segment_candidates_after_stop.keys():
            # This function trims the timing-wise unnecessary parts, links with the free spaces and returns a dict from free_space to a list of starting times
            # TODO fix ofc with new extend setup
            from_stop_linked = evaluate_running_times(entering_main_segment_candidates_after_stop, free_space_dict[get_key(current_vertex, next_vertex, next_track)], 1)
            from_runthrough_linked = evaluate_running_times(entering_main_segment_candidates_after_runthrough, free_space_dict[get_key(current_vertex, next_vertex, next_track)], 1)

            # Determine interval lists
            leaving_segment_list_ss = evaluate_running_times(from_stop_linked, False, False)
            leaving_segment_list_sr = evaluate_running_times(from_stop_linked, False, True)
            leaving_segment_list_rs = evaluate_running_times(from_runthrough_linked, True, False)
            leaving_segment_list_rr = evaluate_running_times(from_runthrough_linked, True, True)

            leaving_segment_towards_stop = merge_intervals([leaving_segment_list_rs, leaving_segment_list_ss])
            leaving_segment_towards_runthrough = merge_intervals([leaving_segment_list_rr, leaving_segment_list_sr])

            for entering_track in allowed_movements_at_arrival[(current_vertex, next_vertex, next_vertex, None, next_track)]:
                if entering_track not in entering_station_candidates_towards_stop.keys():
                    entering_station_candidates_towards_stop[entering_track] = []
                    entering_station_candidates_towards_runthrough[entering_track] = []

                entering_station_candidates_towards_stop[entering_track] += [intersect(leaving_segment_towards_stop, free_space_dict[get_transition_key(current_vertex, next_vertex, next_track, entering_track, True)])]

                entering_station_candidates_towards_runthrough[entering_track] += [intersect(leaving_segment_towards_runthrough, free_space_dict[get_transition_key(current_vertex, next_vertex, next_track, entering_track, True)])]

        for entering_track in entering_station_candidates_towards_stop.keys():
            entering_station_candidates_towards_stop[entering_track] = merge_intervals(
                entering_station_candidates_towards_stop[entering_track])

            entering_station_candidates_towards_runthrough[entering_track] = merge_intervals(
                entering_station_candidates_towards_runthrough[entering_track])
