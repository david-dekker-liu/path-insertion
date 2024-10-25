import time

import numpy as np
import pandas as pd
from datetime import datetime
from datetime import timedelta

import interval_utils
import src.free_space_detection as free_space_detection
import src.timetable_creation as timetable_creation
import src.interval_utils as intutils
from src.intervals import LinkedInterval, Interval
from src.infrastructure import Infrastructure, Station, Segment

# TODO Test first if it is a predefined exception,
# TODO i.e., single-track line with smaller blocks.


def get_segment_type_from_row(row):
    return get_segment_type_from_values(row["dest"], row["track_id"])


def get_segment_type_from_values(dest, track_id):
    # dest is Nan if station
    # otherwise, track_id is E if single track
    if pd.isnull(dest):
        return "station"
    if "E" in track_id or "A" in track_id:
        return "single_block_segment"

    return "multiple_block_segments"


# TODO deprecated replaced by infrastructure file
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
    # Hardcode avoiding tracks that should not be used for northbound running trains, but are used as track to turn round (or go in a different direction)
    possible_movements_dict[("Nol", "Än", "Än", "nananan", "U")] = ["2"]
    possible_movements_dict[("Veas", "Thn", "Thn", "nananan", "U")] = ["1"]
    possible_movements_dict[("Öx", "nananan", "Öx", "Bjh", "60")] = []
    possible_movements_dict[("Öx", "nananan", "Öx", "Bjh", "3")] = []
    possible_movements_dict[("Gbm", "nananan", "Gbm", "Agb", "41")] = []
    possible_movements_dict[("Veas", "Thn", "Thn", "nananan", "U")] = ["1"]

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
    expected_result = df[(df["stn_id_from"] == loc_from) & (df["stn_id_to"] == loc_to)]["line_track_id"].drop_duplicates().tolist()
    if len(expected_result) != 0:
        return expected_result
    else:
        return df[(df["stn_id_to"] == loc_from) & (df["stn_id_from"] == loc_to)]["line_track_id"].drop_duplicates().tolist()


# Returns all track ids that are used in a station in input dataframe
# Only considers first station in pairs
def get_station_track_list(df, loc):
    expected_result = df[(df["orig"] == loc) & (df["dest"].isnull())]["track_id"].drop_duplicates().tolist()
    return expected_result


def generate_candidate_paths(infra, train_to_insert, speed_profile, running_time, t21, TIME_FROM_DATETIME, TIME_TO_DATETIME, train_route, output_file, filter_close_paths):
    segments = [(train_route[i], train_route[i+1]) for i in range(len(train_route) - 1)]

    # Get all station tracks for which we need precomputations
    # These are derived from the infra neighborhood dicts,
    # i.e., for each segment, get the tracks that it can use and the tracks where it can depart from
    # For the last station, there might be no departures, so all possible tracks are used there
    relevant_station_tracks_keys = [key for key in infra.N_stations if (key[0], key[1]) in segments]
    relevant_station_tracks = {}
    for station in train_route:
        relevant_station_tracks[station] = [v[2] for v in relevant_station_tracks_keys if v[0] == station]
    relevant_station_tracks[train_route[-1]] = infra.stations[train_route[-1]].tracks

    # Similar for obtaining all possible segment tracks
    relevant_segment_tracks_keys = [key for key in infra.N_segments if (key[0], key[1]) in segments]
    relevant_segment_tracks = {}
    for segment in segments:
        relevant_segment_tracks[segment] = [v[2] for v in relevant_segment_tracks_keys if (v[0] == segment[0] and v[1] == segment[1]) or (v[1] == segment[0] and v[0] == segment[1])]

    # Get minimum running time for the full path
    # min_time = 0
    # min_time += running_time[("Gsv", "Or1", "s", "r")]
    # min_time += running_time[("Mon", "Ko", "r", "s")]
    # for i in range(len(train_route) - 3):
    #     min_time += running_time[(train_route[i+1], train_route[i+2], "r", "r")]
    # print(f"Minimum travel time for profile {speed_profile} on Gsv-Ko: {min_time}")

    first_loc = train_route[0]

    station_parked_occupations = {}
    station_runthrough_occupations = {}
    backtrack_after_stop = {}
    backtrack_after_runthrough = {}

    candidate_track_occupations = {}
    segment_track_occupations_at_start = {}
    segment_track_occupations_at_end = {}

    # Initialize the dynamic-ish program at the start location
    # Initial run-through is impossible, all free spaces at all tracks give possible departures
    for station_track in relevant_station_tracks[first_loc]:
        station_parked_occupations[(first_loc, station_track)] = [LinkedInterval(x.start, x.end, x.start, x.end) for x in free_space_dict_stations[(first_loc, station_track)]]
        station_runthrough_occupations[(first_loc, station_track)] = []

    # Now traverse all given segments
    for count in range(len(train_route) - 1):
        # Identify segment
        current_vertex = train_route[count]
        next_vertex = train_route[count+1]

        # print("Current vertex", current_vertex, "with tracks", get_station_track_list(t21, current_vertex))

        # Determine for each segment track, when you can enter that track
        # i.e. these dicts contain a list of interval lists for each segment track
        # After merging, they become an interval list
        entering_main_segment_candidates_after_stop = {}
        entering_main_segment_candidates_after_runthrough = {}
        entering_station_candidates_towards_stop = {}
        entering_station_candidates_towards_runthrough = {}
        # First, intersect track possibilities with transition free spaces
        # TODO only take station tracks that were reachable i.e. have existing index!
        # for station_track in get_station_track_list(t21, current_vertex):
        for station_track in relevant_station_tracks[current_vertex]:
            # Obtain possible tracks on the following segment
            allowed_next_tracks = infra.N_stations[(current_vertex, next_vertex, station_track)]

            for next_track in allowed_next_tracks:
                if next_track not in entering_main_segment_candidates_after_stop.keys():
                    entering_main_segment_candidates_after_stop[next_track] = []
                    entering_main_segment_candidates_after_runthrough[next_track] = []

                if (current_vertex, station_track, next_vertex, next_track) in infra.transitions:
                    # print((current_vertex, station_track, next_vertex, next_track), "is an important transition")
                    new_intervals_after_stop = intutils.intersect_intervals(station_parked_occupations[(current_vertex, station_track)], free_space_dict_transitions[(current_vertex, station_track, next_vertex, next_track)])
                    new_intervals_after_runthrough = intutils.intersect_intervals(station_runthrough_occupations[(current_vertex, station_track)], free_space_dict_transitions[(current_vertex, station_track, next_vertex, next_track)])
                    entering_main_segment_candidates_after_stop[next_track] += [new_intervals_after_stop]
                    entering_main_segment_candidates_after_runthrough[next_track] += [new_intervals_after_runthrough]
                    backtrack_after_stop[(current_vertex, station_track)] = new_intervals_after_stop
                    backtrack_after_runthrough[(current_vertex, station_track)] = new_intervals_after_runthrough

                else:
                    # print((current_vertex, station_track, next_vertex, next_track), "is not an important transition")
                    entering_main_segment_candidates_after_stop[next_track] += [station_parked_occupations[(current_vertex, station_track)]]
                    entering_main_segment_candidates_after_runthrough[next_track] += [station_runthrough_occupations[(current_vertex, station_track)]]
                    backtrack_after_stop[(current_vertex, station_track)] = station_parked_occupations[(current_vertex, station_track)]
                    backtrack_after_runthrough[(current_vertex, station_track)] = station_runthrough_occupations[(current_vertex, station_track)]

        # Then, modify the dictionary entries by merging the list of interval lists to one interval list
        for next_track in relevant_segment_tracks[(current_vertex, next_vertex)]:
            entering_main_segment_candidates_after_stop[next_track] = intutils.merge_intervals(entering_main_segment_candidates_after_stop[next_track])

            entering_main_segment_candidates_after_runthrough[next_track] = intutils.merge_intervals(entering_main_segment_candidates_after_runthrough[next_track])

        # Now extend this for the segments
        # Start from the segment free spaces, and map each segment free space to a (possibly empty) list of time intervals to enter the segment
        # Perhaps (is this needed?) make sure that the corr starting times are strictly increasing, so remove any bit that is below two other values.
        # E.g.: if one interval is 8-11 and a later one has starting times 10-16, drop 10-11 of the second one, as you could also start at 11 and get there at that time

        # Now duplicate both to get such a mapping for all four stopping patterns
        # Then extrapolate each segment free space (i.e. add min running time)
        # If no interval is present after the segment, add a bonus "slow moving" segment with constant departure time.

        # print("shit", entering_main_segment_candidates_after_stop.keys())
        for next_track in relevant_segment_tracks[(current_vertex, next_vertex)]:
            # Determine interval lists for the next station by extending with the appropriate running time
            # print(current_vertex, next_vertex, next_track, get_key(current_vertex, next_vertex, next_track), free_space_dict[get_key(current_vertex, next_vertex, next_track)])
            # print(running_time)
            leaving_segment_list_ss = intutils.evaluate_running_times(entering_main_segment_candidates_after_stop[next_track], free_space_dict_segments[(current_vertex, next_vertex, next_track)], running_time[(current_vertex, next_vertex, "s", "s")])
            leaving_segment_list_sr = intutils.evaluate_running_times(entering_main_segment_candidates_after_stop[next_track], free_space_dict_segments[(current_vertex, next_vertex, next_track)], running_time[(current_vertex, next_vertex, "s", "r")])
            leaving_segment_list_rs = intutils.evaluate_running_times(entering_main_segment_candidates_after_runthrough[next_track], free_space_dict_segments[(current_vertex, next_vertex, next_track)], running_time[(current_vertex, next_vertex, "r", "s")])
            leaving_segment_list_rr = intutils.evaluate_running_times(entering_main_segment_candidates_after_runthrough[next_track], free_space_dict_segments[(current_vertex, next_vertex, next_track)], running_time[(current_vertex, next_vertex, "r", "r")])

            # print(leaving_segment_list_rs)
            # print(leaving_segment_list_ss)

            leaving_segment_towards_stop = intutils.merge_intervals([leaving_segment_list_rs, leaving_segment_list_ss])
            leaving_segment_towards_runthrough = intutils.merge_intervals([leaving_segment_list_rr, leaving_segment_list_sr])

            for entering_track in infra.N_segments[(current_vertex, next_vertex, next_track)]:
                if entering_track not in entering_station_candidates_towards_stop.keys():
                    entering_station_candidates_towards_stop[entering_track] = []
                    entering_station_candidates_towards_runthrough[entering_track] = []

                if (current_vertex, next_track, next_vertex, entering_track) in infra.transitions:
                    # print((current_vertex, next_track, next_vertex, entering_track), "is important")
                    # print(entering_station_candidates_towards_stop[entering_track])
                    # print(free_space_dict_transitions[(current_vertex, next_track, next_vertex, entering_track)])
                    entering_station_candidates_towards_stop[entering_track] += [intutils.intersect_intervals(leaving_segment_towards_stop, free_space_dict_transitions[(current_vertex, next_track, next_vertex, entering_track)])]

                    entering_station_candidates_towards_runthrough[entering_track] += [intutils.intersect_intervals(leaving_segment_towards_runthrough, free_space_dict_transitions[(current_vertex, next_track, next_vertex, entering_track)])]
                else:
                    entering_station_candidates_towards_stop[entering_track] += [leaving_segment_towards_stop]

                    entering_station_candidates_towards_runthrough[entering_track] += [leaving_segment_towards_runthrough]

        for entering_track in relevant_station_tracks[next_vertex]:
            entering_station_candidates_towards_stop[entering_track] = intutils.merge_intervals(
                entering_station_candidates_towards_stop[entering_track])

            entering_station_candidates_towards_runthrough[entering_track] = intutils.merge_intervals(
                entering_station_candidates_towards_runthrough[entering_track])

        station_parked_occupations_temp = {}
        station_runthrough_occupations_temp = {}

        for station_track in relevant_station_tracks[next_vertex]:
            station_parked_occupations_temp[(next_vertex, station_track)] = intutils.extend_parked_times(entering_station_candidates_towards_stop[station_track], free_space_dict_stations[(next_vertex, station_track)])

            interm = [lint for lint in station_parked_occupations_temp[(next_vertex, station_track)] if lint.start != lint.end]

            station_parked_occupations[(next_vertex, station_track)] = intutils.merge_intervals([interm])

            station_runthrough_occupations_temp[(next_vertex, station_track)] = intutils.intersect_intervals(entering_station_candidates_towards_runthrough[station_track], free_space_dict_stations[(next_vertex, station_track)])

            interm = [lint for lint in station_runthrough_occupations_temp[(next_vertex, station_track)] if lint.start != lint.end]

            station_runthrough_occupations[(next_vertex, station_track)] = intutils.merge_intervals([interm])

    end = time.time()
    last_vertex = train_route[-1]
    options = []

    #########################
    ### PATH BACKTRACKING ###
    #########################

    # Generate a discrete number of paths, as there could be continuous ranges
    # We merge all options for all tracks
    for track in infra.stations[last_vertex].tracks:
        if (last_vertex, track) not in station_parked_occupations:
            continue

        for interval in station_parked_occupations[(last_vertex, track)]:
            # Each interval with one departure time gives one path (i.e., .orig_start to .start)
            if interval.orig_start == interval.orig_end:
                options += [(track, interval.start, interval.orig_start, "s")]
            # Otherwise, we will generate paths with a separation of 180 seconds in between
            else:
                timestamp_orig = interval.orig_start
                timestamp_now = interval.start
                while timestamp_orig <= interval.orig_end:
                    options += [(track, timestamp_now, timestamp_orig, "s")]
                    timestamp_orig = timestamp_orig + timedelta(0, 180)
                    timestamp_now = timestamp_now + timedelta(0, 180)

    # print(options)
    filtered_options = []

    # Remove duplicate options and options that are dominated by others
    # (may occur due to different available tracks)
    for option in options:
        dominant = True
        for other_track, other_here, other_start, startstop in options:
            if other_here <= option[1] and other_start >= option[2] and (other_here < option[1] or other_start > option[2]):
                dominant = False

        if dominant and all([y != option[1] or z != option[2] for x, y, z, t in filtered_options]):
            filtered_options += [option]

    # Sort by departure at the start
    filtered_options.sort(key=lambda x: x[2])
    # print(filtered_options)

    # Removing paths that start or end very close to another path
    # When start times are close (< 180 seconds), we remove the later departing path;
    # when the end times are close (< 180 seconds), we remove the earlier departing path.
    # NOTE: perhaps not wise when it is a suitable candidate path
    filtered_filtered_options = []
    last_start_time = 0
    last_end_time = 0
    count = 1
    # print("filtered options", filtered_options)
    for w,x,y,z in filtered_options:
        if last_end_time == 0:
            filtered_filtered_options += [(w,x,y,z,count)]
            last_end_time = x
            last_start_time = y
            count += 1
            continue
        if filter_close_paths and (y - last_start_time).total_seconds() < 180:
            continue
        if filter_close_paths and (x - last_end_time).total_seconds() < 180:
            filtered_filtered_options = filtered_filtered_options[:-1]
            count -= 1

        last_start_time = y
        last_end_time = x
        filtered_filtered_options += [(w,x,y,z,count)]
        count += 1

    next_options = filtered_filtered_options

    ###########################
    ### ACTUAL BACKTRACKING ###
    ###########################

    # Write header, arrivals at destination and store those times for segment descriptions
    last_time = {}
    with open(output_file, 'w+', encoding='utf-8') as f:
        f.write("train_ix;train_id;variant;orig;dest;track_id;time_start;time_end;date\n")
        for opt in next_options:
            f.write(f"{train_to_insert}999{opt[4]};{train_to_insert};{opt[4]};{train_route[-1]};;{opt[0]};{datetime.strftime(opt[1], '%Y-%m-%d %H:%M:%S')};;{datetime.strftime(opt[1], '%Y-%m-%d')}\n")
            last_time[opt[4]] = opt[1]

    for trafikplats in reversed(train_route[:-1]):
        updated_options = []
        # Iterate over each of the candidate paths
        for track_id, end_time, start_time, startstop, train_id in next_options:
            # At the start, we want the latest time, otherwise the earliest
            # best_time keeps track of the earliest (or latest) departure time,
            # best_time_arr keeps track of an arrival time if different
            # and the tracks keep track of the corresponding tracks at the segment and station
            if trafikplats != train_route[0]:
                best_time = TIME_TO_DATETIME
            else:
                best_time = TIME_FROM_DATETIME
            best_time_arr = 0
            best_arrival_track = None
            best_segment_track = None

            # Test possible segment tracks
            for segment_track in infra.segments[(trafikplats, last_vertex)].tracks:
                if (trafikplats, last_vertex, segment_track) not in free_space_dict_segments:
                    continue
                if (trafikplats, last_vertex, segment_track) not in infra.N_segments or track_id not in infra.N_segments[(trafikplats, last_vertex, segment_track)]:
                    continue

                # Get free spaces and minimum running times
                free_spaces = free_space_dict_segments[(trafikplats, last_vertex, segment_track)]
                from_r = running_time[(trafikplats, last_vertex, "r", startstop)]
                from_s = running_time[(trafikplats, last_vertex, "s", startstop)]

                for free_space in free_spaces:
                    # Should be exactly one case where this is not true
                    if not free_space.second_start <= end_time <= free_space.second_end:
                        continue

                    # Get the interval which the train could have used at the start of the segment
                    if end_time - timedelta(seconds=from_s) >= free_space.first_end:
                        from_s_range = Interval(free_space.first_start, free_space.first_end)
                    elif free_space.first_start <= end_time - timedelta(seconds=from_s) <= free_space.first_end:
                        from_s_range = Interval(free_space.first_start, end_time - timedelta(seconds=from_s))
                    else:
                        # Magic value if no such interval exists
                        from_s_range = 0

                    # If a stop is possible at the previous station,
                    # get the time it would depart from there (+ arrive)
                    # TODO may be a problem when longer intervals are split due to rounding?
                    if from_s_range != 0:
                        # Try all possible tracks at the previous trafikplats
                        for prev_track in infra.stations[trafikplats].tracks:
                            if (trafikplats, last_vertex, prev_track) not in infra.N_stations or segment_track not in infra.N_stations[(trafikplats, last_vertex, prev_track)]:
                                continue

                            # Get intervals that correspond with the given original departure
                            track_options = [v for v in backtrack_after_stop[(trafikplats, prev_track)] if v.orig_start <= start_time <= v.orig_end]

                            # Get intersection of the two
                            new_times = interval_utils.intersect_one_interval(from_s_range, track_options)

                            if new_times == 0:
                                continue

                            # Get parked occupations and find relevant interval there
                            with_original_times = station_parked_occupations[(trafikplats, prev_track)]
                            for linked_interval in with_original_times:
                                if linked_interval.start > new_times.end or linked_interval.end < new_times.start:
                                    continue
                                if start_time < linked_interval.orig_start or start_time > linked_interval.orig_end:
                                    continue
                                if trafikplats == train_route[0]:
                                    # If we are finished, we want the LATEST departure time
                                    new_time_option = min(linked_interval.end, new_times.end)
                                    if new_time_option >= best_time:
                                        best_segment_track = segment_track
                                        best_arrival_track = prev_track
                                        best_time = new_time_option
                                elif linked_interval.orig_end == linked_interval.orig_start:
                                    # Otherwise, the EARLIEST
                                    new_time_option = max(linked_interval.start, new_times.start)
                                    if new_time_option <= best_time:
                                        best_segment_track = segment_track
                                        best_arrival_track = prev_track
                                        best_time = new_time_option

                                        # And get the corresponding earliest possible arrival time
                                        station_occ = [v for v in station_parked_occupations[(trafikplats, prev_track)] if v.orig_start == start_time and start_time == v.orig_end]
                                        # if len(station_occ) != 1:
                                            # print("sth may be wrong with station occ while backtracking", len(station_occ), start_time, station_occ)
                                        best_time_arr = station_occ[0].start

                    # Now analogous case for runthroughs
                    # If we get a better time here, we go for the runthrough instead
                    if end_time - timedelta(seconds=from_r) >= free_space.first_end:
                        from_r_range = Interval(free_space.first_start, free_space.first_end)
                    elif free_space.first_start <= end_time - timedelta(seconds=from_r) <= free_space.first_end:
                        from_r_range = Interval(free_space.first_start, end_time - timedelta(seconds=from_r))
                    else:
                        from_r_range = 0

                    if from_r_range != 0 and trafikplats != train_route[0]:
                        for prev_track in infra.stations[trafikplats].tracks:
                            if (trafikplats, last_vertex, prev_track) not in infra.N_stations or segment_track not in infra.N_stations[(trafikplats, last_vertex, prev_track)]:
                                continue

                            track_options = [v for v in backtrack_after_runthrough[(trafikplats, prev_track)] if v.orig_start <= start_time <= v.orig_end]

                            new_times = interval_utils.intersect_one_interval(from_r_range, track_options)

                            if new_times == 0:
                                continue

                            corresponding_track_options = [v for v in track_options if v.start <= new_times.start <= new_times.end <= v.end]

                            if len(corresponding_track_options) > 1:
                                raise Exception("Multiple corresponding tracks found. Maybe take first one?")

                            corresponding_track_option = corresponding_track_options[0]

                            # Two options: one starting point as a goal, or a parallel range of paths
                            if corresponding_track_option.orig_end == corresponding_track_option.orig_start:
                                new_time_option = max(corresponding_track_option.start, new_times.start)
                                if new_time_option <= best_time:
                                    best_segment_track = segment_track
                                    best_arrival_track = prev_track
                                    best_time = new_time_option
                                    best_time_arr = 0
                            else:
                                time_diff_end = (start_time - corresponding_track_option.orig_start).total_seconds()
                                new_time_option = corresponding_track_option.start + timedelta(seconds = time_diff_end)
                                if new_times.start <= new_time_option <= new_times.end:
                                    best_segment_track = segment_track
                                    best_arrival_track = prev_track
                                    best_time = new_time_option
                                    best_time_arr = 0

            # print(best_time_arr, "/", best_time, trafikplats, best_arrival_track, last_vertex, best_segment_track)

            with open(output_file, 'a+', encoding='utf-8') as f:
                f.write(
                    f"{train_to_insert}999{train_id};"
                    f"{train_to_insert};"
                    f"{train_id};"
                    f"{trafikplats};"
                    f"{last_vertex};"
                    f"{best_segment_track};"
                    f"{datetime.strftime(best_time, '%Y-%m-%d %H:%M:%S')};"
                    f"{datetime.strftime(last_time[train_id], '%Y-%m-%d %H:%M:%S')};"
                    f"{datetime.strftime(best_time, '%Y-%m-%d')}\n")

                if trafikplats == train_route[-1]:
                    arr = best_time
                    dep = ""
                elif best_time_arr == 0:
                    arr = best_time
                    dep = best_time
                else:
                    arr = best_time_arr
                    dep = best_time
                last_time[train_id] = arr

                f.write(
                    f"{train_to_insert}999{train_id};"
                    f"{train_to_insert};"
                    f"{train_id};"
                    f"{trafikplats};"
                    f";"
                    f"{best_arrival_track};"
                    f"{datetime.strftime(arr, '%Y-%m-%d %H:%M:%S')};"
                    f"{datetime.strftime(dep, '%Y-%m-%d %H:%M:%S')};"
                    f"{datetime.strftime(arr, '%Y-%m-%d')}\n")

            if best_time_arr == 0:
                updated_options += [(best_arrival_track, best_time, start_time, "r", train_id)]
            else:
                updated_options += [(best_arrival_track, best_time_arr, start_time, "s", train_id)]

        last_vertex = trafikplats
        next_options = updated_options

    prev_vertex = 0

    for (current_vertex, station_track) in station_parked_occupations.keys():
        if prev_vertex != 0 and prev_vertex != current_vertex:
            print("rr", running_time[(prev_vertex, current_vertex, "r", "r")],
                  "rs", running_time[(prev_vertex, current_vertex, "r", "s")],
                  "sr", running_time[(prev_vertex, current_vertex, "s", "r")],
                  "ss", running_time[(prev_vertex, current_vertex, "s", "s")])
        prev_vertex = current_vertex
    #
       # print(current_vertex, station_track, [v for v in station_parked_occupations[(current_vertex, station_track)] if v.orig_start <= datetime.strptime("2021-01-20 10:40:18", "%Y-%m-%d %H:%M:%S") and datetime.strptime("2021-01-20 10:40:14", "%Y-%m-%d %H:%M:%S") <= v.orig_end])
       # print(current_vertex, station_track,  [v for v in station_runthrough_occupations[(current_vertex, station_track)] if v.orig_start <= datetime.strptime("2021-01-20 10:40:18", "%Y-%m-%d %H:%M:%S") and datetime.strptime("2021-01-20 10:40:14", "%Y-%m-%d %H:%M:%S") <= v.orig_end])
       #
        if current_vertex not in ["Söö", "Jn", "Msj"]:
            continue

        print(current_vertex, station_track, len(station_parked_occupations[(current_vertex, station_track)]) + len(station_runthrough_occupations[(current_vertex, station_track)]))
        print(current_vertex, station_track, "s", station_parked_occupations[(current_vertex, station_track)] )
        print(current_vertex, station_track, "r", station_runthrough_occupations[(current_vertex, station_track)] )
    # print(end - start)
    # with open('../out/running_times.txt', 'a+') as the_file:
    #     the_file.write(f"{end-start}\n")




if __name__ == '__main__':
    # m_infra = Infrastructure("../config/infrastructure-details-SE.txt", "../config/conflict_margins.txt")
    m_infra = Infrastructure("../config/infrastructure-details-RailDresden.txt", "../config/conflict_margins.txt")
    fullstart = time.time()
    running_time_source = "../data/generated_running_times.csv"
    # running_time_source = "../data/t21_technical_running_times.csv"

    # Time frame to be considered
    m_TIME_FROM = "2021-03-14 00:00"
    m_TIME_TO = "2021-03-15 06:00"
    m_TIME_FROM_DATETIME = datetime.strptime(m_TIME_FROM, "%Y-%m-%d %H:%M")
    m_TIME_TO_DATETIME = datetime.strptime(m_TIME_TO, "%Y-%m-%d %H:%M")

    # Other settings
    m_output_file = "../out/candidate_paths.csv"
    m_filter_close_paths = False

    # Hard-coded train route at the moment
    # Segments are derived from that
    # m_train_route = ["Fdf", "Brl", "Skbl", "Rås", "Bäf", "Ed", "Ko"]
    # m_train_route = ["Gbm", "Agb", "Sue", "Bhs", "Nöe", "Nol", "Än", "Alh", "Les", "Tbn", "Vpm", "Veas", "Thn", "Öx", "Bjh", "Fdf", "Brl", "Skbl", "Rås", "Bäf", "Ed", "Ko"]
    # m_train_route = ["Gsv", "Or1", "Or", "Gbm", "Agb", "Sue", "Bhs", "Nöe", "Nol", "Än", "Alh", "Les", "Tbn", "Vpm", "Veas", "Thn", "Öx", "Bjh", "Fdf", "Brl", "Skbl", "Rås", "Bäf", "Ed", "Ko"]
    # m_train_route = ["G", "Or", "Or1", "Gsv", "Säv", "Sel", "P", "Jv", "J", "Apn", "Asd", "Lr", "Sn", "Fd", "Ndv", "Ns", "Vbd", "Bgs", "A", "Agg", "Vgå", "Hr", "Kä", "Fby", "F", "Fn", "Ss", "Rmtp", "Sk", "Vä", "Mh", "T", "Sle", "Äl", "Gdö", "Fa", "Lå", "Lln", "Vt", "Öj", "Täl", "Hrbg"]
    m_train_route = ["G", "Or", "Or1", "Gsv", "Säv", "Sel", "P", "Jv", "J", "Apn", "Asd", "Lr", "Sn", "Fd", "Ndv", "Ns", "Vbd", "Bgs", "A", "Agg", "Vgå", "Hr", "Kä", "Fby", "F", "Fn", "Ss", "Rmtp", "Sk", "Vä", "Mh", "T", "Sle", "Äl", "Gdö", "Fa", "Lå", "Lln", "Vt", "Öj", "Täl", "Hrbg", "Hpbg", "På", "Km", "Hgö", "Vr", "Bt", "K", "Spn", "Sde", "Fle", "Skv", "Sp", "Nsj", "Sh", "B", "Koe", "Gn", "Mö", "Jn", "Söö", "Msj", "Bjn", "Flb", "Hu", "Sta", "Äs", "Åbe", "Sst", "Cst"]

    m_t21 = timetable_creation.get_timetable(m_TIME_FROM, m_TIME_TO, m_train_route)
    m_t21 = timetable_creation.remove_linjeplatser(m_t21, ["Drt", "Mon"])
    m_t21.to_csv("../data/filtered_t21.csv", sep=";")
    # m_t21 = pd.read_csv("../data/filtered_t21.csv", sep=";")
    # timetable_creation.detect_track_allocation_problems(t21, train_route, "../out/log.txt")

    m_train_to_insert = 45693
    m_speed_profile = "PX2-2000"  # X2000
    # m_speed_profile = "GB201010"  # Arbitrary freight profile, unused on Hm-Äh
    # m_speed_profile = "GB201610"
    m_running_time = timetable_creation.get_running_times(running_time_source, m_infra.linjeplatser, m_speed_profile)
    m_segments = [(m_train_route[i], m_train_route[i + 1]) for i in range(len(m_train_route) - 1)]

    print(m_infra.stations)
    print("Get station free spaces")
    free_space_dict_stations = free_space_detection.get_free_spaces_stations(m_t21, m_train_to_insert, m_TIME_FROM_DATETIME, m_TIME_TO_DATETIME, m_infra.stations)
    print(free_space_dict_stations)
    print("Get transition free spaces")
    free_space_dict_transitions = free_space_detection.get_free_spaces_transitions(m_t21, m_train_to_insert, m_TIME_FROM_DATETIME, m_TIME_TO_DATETIME, m_infra.transitions)
    print(free_space_dict_transitions)
    print("Get segment free spaces")
    free_space_dict_segments = free_space_detection.get_free_spaces_segments(m_t21, m_train_to_insert, m_TIME_FROM_DATETIME, m_TIME_TO_DATETIME, m_segments, m_infra)
    print(free_space_dict_segments)

    end_of_prep = time.time()
    print("Preparation time", end_of_prep - fullstart)

    generate_candidate_paths(m_infra, m_train_to_insert, m_speed_profile, m_running_time, m_t21, m_TIME_FROM_DATETIME, m_TIME_TO_DATETIME, m_train_route, m_output_file, m_filter_close_paths)
    end_of_alg = time.time()
    print("Running time", end_of_alg - end_of_prep)
