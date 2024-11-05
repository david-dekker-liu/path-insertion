import shutil
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


def obj(t1, t2, req1, req2):
    result = 0
    alpha2 = 0.00000003
    alpha3 = 0.00000003
    alpha1 = 1 - alpha2 - alpha3

    if t1 < req1:
        result += alpha2 * ((req1 - t1).total_seconds()) * ((req1 - t1).total_seconds())

    if t2 > req2:
        result += alpha3 * ((t2 - req2).total_seconds()) * ((t2 - req2).total_seconds())

    result += alpha1 * (t2 - t1).total_seconds() / (req2 - req1).total_seconds()

    return result

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


def generate_candidate_paths(infra, train_to_insert, speed_profile, running_time_all_profiles, t21, time_from, time_to, train_route, output_file, filter_close_paths, free_space_dict_stations, free_space_dict_segments, free_space_dict_transitions, log_file="../out/log.csv", req_dep=0, req_arr=0, add_to_t21=False, config={}, only_fastest=False):

    print("")
    time_start = time.time()
    output_paths = []
    running_time = running_time_all_profiles[speed_profile]

    segments = [(train_route[i], train_route[i+1]) for i in range(len(train_route) - 1)]

    # Get all station tracks for which we need precomputations
    # These are derived from the infra neighborhood dicts,
    # i.e., for each segment, get the tracks that it can use and the tracks where it can depart from
    # For the last station, there might be no departures, so all possible tracks are used there
    relevant_station_tracks_keys = [key for key in infra.N_stations if (key[0], key[1]) in segments]
    relevant_station_tracks = {}
    for station in train_route:
        relevant_station_tracks[station] = [v[2] for v in relevant_station_tracks_keys if v[0] == station]
    # At some point decided that at arrival you can use all tracks, giving some issues in the path generation oops...
    relevant_station_tracks[train_route[-1]] = infra.stations[train_route[-1]].tracks

    # last_tracks = infra.segments[(train_route[-2], train_route[-1])].tracks
    # if "U" in last_tracks:
    #     relevant_station_tracks[train_route[-1]] = infra.N_segments[(train_route[-2], train_route[-1], "U")]
    # else:
    #     relevant_station_tracks[train_route[-1]] = infra.N_segments[(train_route[-2], train_route[-1], last_tracks[0])]

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
        station_parked_occupations[(first_loc, station_track)] = interval_utils.intersect_intervals([LinkedInterval(x.start, x.end, x.start, x.end) for x in free_space_dict_stations[(first_loc, station_track)]], [Interval(time_from, time_to)])
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
            if entering_track in entering_station_candidates_towards_runthrough:
                entering_station_candidates_towards_stop[entering_track] = intutils.merge_intervals(
                    entering_station_candidates_towards_stop[entering_track])

            if entering_track in entering_station_candidates_towards_runthrough:
                entering_station_candidates_towards_runthrough[entering_track] = intutils.merge_intervals(
                    entering_station_candidates_towards_runthrough[entering_track])

        station_parked_occupations_temp = {}
        station_runthrough_occupations_temp = {}

        for station_track in relevant_station_tracks[next_vertex]:
            if station_track in entering_station_candidates_towards_stop:
                station_parked_occupations_temp[(next_vertex, station_track)] = intutils.extend_parked_times(entering_station_candidates_towards_stop[station_track], free_space_dict_stations[(next_vertex, station_track)])

                interm = [lint for lint in station_parked_occupations_temp[(next_vertex, station_track)] if lint.start != lint.end]

                station_parked_occupations[(next_vertex, station_track)] = intutils.intersect_intervals(intutils.merge_intervals([interm]), [Interval(time_from, time_to)])

            if station_track in entering_station_candidates_towards_runthrough:
                station_runthrough_occupations_temp[(next_vertex, station_track)] = intutils.intersect_intervals(entering_station_candidates_towards_runthrough[station_track], free_space_dict_stations[(next_vertex, station_track)])

                interm = [lint for lint in station_runthrough_occupations_temp[(next_vertex, station_track)] if lint.start != lint.end]

                station_runthrough_occupations[(next_vertex, station_track)] = intutils.intersect_intervals(intutils.merge_intervals([interm]), [Interval(time_from, time_to)])

    if config["print_runtime"]:
        print("Filling dynamic programming tables:", time.time() - time_start)
    current_time = time.time()

    last_vertex = train_route[-1]
    options = []

    alg_finish = time.time()
    if log_file != "":
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{train_to_insert};algorithm;{alg_finish - time_start}\n")

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

    # Filter out too expensive paths, if requested times are provided
    if req_arr != 0:
        next_options = [v for v in filtered_filtered_options if obj(v[2], v[1], req_dep, req_arr) <= 5.5]
    else:
        next_options = filtered_filtered_options

    # Only get the fastest path
    if only_fastest:
        best_option = next_options[0]
        best_time = (best_option[1] - best_option[2]).total_seconds()

        for v in next_options:
            if (v[1] - v[2]).total_seconds() < best_time:
                best_option = v
                best_time = (v[1] - v[2]).total_seconds()

            next_options = [best_option]

    # Only get the min-cost path
    if add_to_t21:
        best_option = next_options[0]

        for v in next_options:
            if obj(v[2], v[1], req_dep, req_arr) < obj(best_option[2], best_option[1], req_dep, req_arr):
                best_option = v

        next_options = [best_option]
        # Target time is necessary to get date differences
        target_time = best_option[2]

    # print("next")
    # for k in next_options:
    #     print(k[2], k[1], req_dep, req_arr, obj(k[2], k[1], req_dep, req_arr))

    if config["print_runtime"]:
        print("Preprocessed path options:", time.time() - current_time)
        print("#paths for backtracking:", len(next_options))
    current_time = time.time()

    ###########################
    ### ACTUAL BACKTRACKING ###
    ###########################

    # Write header, arrivals at destination and store those times for segment descriptions
    last_time = {}
    # if output_file != "":
    #     with open(output_file, 'w+', encoding='utf-8') as f:
    #         f.write("train_ix;train_id;variant;orig;dest;track_id;time_start;time_end;date\n")
    #         for opt in next_options:
    #             f.write(f"{train_to_insert}999{opt[4]};{train_to_insert};{opt[4]};{train_route[-1]};;{opt[0]};{datetime.strftime(opt[1], '%Y-%m-%d %H:%M:%S')};;{datetime.strftime(opt[1], '%Y-%m-%d')}\n")
    for opt in next_options:
        output_paths.append(
            {
                "train_ix": f"{train_to_insert}option{opt[4]}",
                "train_id": train_to_insert,
                "variant": opt[4],
                "orig": train_route[-1],
                "dest": "",
                "track_id": opt[0],
                "time_start": opt[1],
                "time_end": opt[1],
                "date": datetime.strftime(opt[1], '%Y-%m-%d')
            }
        )
        last_time[opt[4]] = opt[1]

    if add_to_t21:
        with open("C:/Users/davde78/Documents/sos-project/out/log_incr_insertion.csv", 'a+', encoding='utf-8') as f:
            f.write(f"{train_to_insert}999{opt[4]};{train_to_insert};{obj(best_option[2], best_option[1], req_dep, req_arr)}\n")
        with open("C:/Users/davde78/Documents/sos-project/data/t21_temp.csv", 'a', encoding='utf-8') as f:
            for opt in next_options:
                f.write(
                    f"0,{train_to_insert}999{opt[4]},{train_to_insert},{opt[4]},0,{train_route[-1]},,{get_time(opt[1], target_time)},,0,{opt[0]},0\n")
                last_time[opt[4]] = opt[1]
        with open("C:/Users/davde78/Documents/sos-project/data/t21_running_days_temp.csv", 'a', encoding='utf-8') as f:
            f.write(f"{train_to_insert}999{opt[4]},{target_time.strftime('%Y-%m-%d')}\n")


    for trafikplats in reversed(train_route[:-1]):
        updated_options = []
        # Iterate over each of the candidate paths
        for track_id, end_time, start_time, startstop, train_id in next_options:
            # At the start, we want the latest time, otherwise the earliest
            # best_time keeps track of the earliest (or latest) departure time,
            # best_time_arr keeps track of an arrival time if different
            # and the tracks keep track of the corresponding tracks at the segment and station
            if trafikplats != train_route[0]:
                best_time = time_to
            else:
                best_time = time_from
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
            # if output_file != "":
            #     with open(output_file, 'a+', encoding='utf-8') as f:
            #         f.write(
            #             f"{train_to_insert}999{train_id};"
            #             f"{train_to_insert};"
            #             f"{train_id};"
            #             f"{trafikplats};"
            #             f"{last_vertex};"
            #             f"{best_segment_track};"
            #             f"{datetime.strftime(best_time, '%Y-%m-%d %H:%M:%S')};"
            #             f"{datetime.strftime(last_time[train_id], '%Y-%m-%d %H:%M:%S')};"
            #             f"{datetime.strftime(best_time, '%Y-%m-%d')}\n")

            output_paths.append(
                {
                    "train_ix": f"{train_to_insert}option{train_id}",
                    "train_id": train_to_insert,
                    "variant": train_id,
                    "orig": trafikplats,
                    "dest": last_vertex,
                    "track_id": best_segment_track,
                    "time_start": best_time,
                    "time_end": last_time[train_id],
                    "date": datetime.strftime(best_time, '%Y-%m-%d')
                }
            )

            if trafikplats == train_route[-1]:
                arr = best_time
                dep = ""
            elif best_time_arr == 0:
                arr = best_time
                dep = best_time
            else:
                arr = best_time_arr
                dep = best_time

            if not add_to_t21:
                last_time[train_id] = arr

            # if output_file != "":
            #     with open(output_file, 'a+', encoding='utf-8') as f:
            #         f.write(
            #             f"{train_to_insert}999{train_id};"
            #             f"{train_to_insert};"
            #             f"{train_id};"
            #             f"{trafikplats};"
            #             f";"
            #             f"{best_arrival_track};"
            #             f"{datetime.strftime(arr, '%Y-%m-%d %H:%M:%S')};"
            #             f"{datetime.strftime(dep, '%Y-%m-%d %H:%M:%S')};"
            #             f"{datetime.strftime(arr, '%Y-%m-%d')}\n")

            output_paths.append(
                {
                    "train_ix": f"{train_to_insert}option{train_id}",
                    "train_id": train_to_insert,
                    "variant": train_id,
                    "orig": trafikplats,
                    "dest": "",
                    "track_id": best_arrival_track,
                    "time_start": arr,
                    "time_end": dep,
                    "date": datetime.strftime(arr, '%Y-%m-%d')
                }
            )

            if add_to_t21:
                with open("C:/Users/davde78/Documents/sos-project/data/t21_temp.csv", 'a', encoding='utf-8') as f:
                    f.write(
                        f"0,{train_to_insert}999{train_id},"
                        f"{train_to_insert},"
                        f"{train_id},0,"
                        f"{trafikplats},"
                        f"{last_vertex},"
                        f"{get_time(best_time, target_time)},"
                        f"{get_time(last_time[train_id], target_time)},0,"
                        f"{best_segment_track},0\n")

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
                        f"0,{train_to_insert}999{train_id},"
                        f"{train_to_insert},"
                        f"{train_id},0,"
                        f"{trafikplats},"
                        f","
                        f"{get_time(arr, target_time)},"
                        f"{get_time(dep, target_time)},0,"
                        f"{best_segment_track},0\n")


            """
            ordinal,train_ix,train_id,variant,stn_ix,orig,dest,time_start,time_end,activity,track_id,stop_is_possible
            19,11965,6222,1,467,Hyl,,09:53:00,09:56:00,,3,f
            """

            if best_time_arr == 0:
                updated_options += [(best_arrival_track, best_time, start_time, "r", train_id)]
            else:
                updated_options += [(best_arrival_track, best_time_arr, start_time, "s", train_id)]

        last_vertex = trafikplats
        next_options = updated_options

    prev_vertex = 0

    total_finish = time.time()
    if log_file != "":
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{train_to_insert};backtracking;{total_finish - alg_finish}\n")

    if config["print_runtime"]:
        print("Backtracking:", time.time() - current_time)

    output_df = pd.DataFrame(output_paths)

    if output_file != "":
        output_df.to_csv(output_file, encoding="utf-8", sep=";")

    return output_df

    # for (current_vertex, station_track) in station_parked_occupations.keys():
    #     if prev_vertex != 0 and prev_vertex != current_vertex:
    #         print("rr", running_time[(prev_vertex, current_vertex, "r", "r")],
    #               "rs", running_time[(prev_vertex, current_vertex, "r", "s")],
    #               "sr", running_time[(prev_vertex, current_vertex, "s", "r")],
    #               "ss", running_time[(prev_vertex, current_vertex, "s", "s")])
    #     prev_vertex = current_vertex
    #
       # print(current_vertex, station_track, [v for v in station_parked_occupations[(current_vertex, station_track)] if v.orig_start <= datetime.strptime("2021-01-20 10:40:18", "%Y-%m-%d %H:%M:%S") and datetime.strptime("2021-01-20 10:40:14", "%Y-%m-%d %H:%M:%S") <= v.orig_end])
       # print(current_vertex, station_track,  [v for v in station_runthrough_occupations[(current_vertex, station_track)] if v.orig_start <= datetime.strptime("2021-01-20 10:40:18", "%Y-%m-%d %H:%M:%S") and datetime.strptime("2021-01-20 10:40:14", "%Y-%m-%d %H:%M:%S") <= v.orig_end])
       #
        ##### DEBUG OPTIONS FOR SHOWING ALL OPTIONS AT A STATION #####

        # if current_vertex not in ["Söö", "Jn", "Msj"]:
        #     continue

        # print(current_vertex, station_track, len(station_parked_occupations[(current_vertex, station_track)]) + len(station_runthrough_occupations[(current_vertex, station_track)]))
        # print(current_vertex, station_track, "s", station_parked_occupations[(current_vertex, station_track)] )
        # print(current_vertex, station_track, "r", station_runthrough_occupations[(current_vertex, station_track)] )
    # print(end - start)
    # with open('../out/running_times.txt', 'a+') as the_file:
    #     the_file.write(f"{end-start}\n")


def get_time(t1, target_time):
    if target_time.strftime('%Y-%m-%d') != t1.strftime('%Y-%m-%d'):
        hours = str(int(t1.strftime('%H')) + 24)
        return hours + t1.strftime(':%H:%S')
    else:
        return t1.strftime('%H:%M:%S')

def generate_many_paths():
    infra = Infrastructure("../config_RailDresden.txt/infrastructure-details-RailDresden.txt", "../config_RailDresden.txt/conflict_margins.txt")
    fullstart = time.time()
    running_time_source = "../data/generated_running_times.csv"

    TIME_FROM = "2021-03-13 23:00"
    TIME_TO = "2021-03-15 07:00"
    TIME_FROM_DATETIME = datetime.strptime(TIME_FROM, "%Y-%m-%d %H:%M")
    TIME_TO_DATETIME = datetime.strptime(TIME_TO, "%Y-%m-%d %H:%M")

    # Other settings
    filter_close_paths = False

    AG = ["Ä", "Baa", "Vip", "För", "Bån", "Laov", "Ea", "Kst", "Hdr", "Hd", "Fur", "Btp", "Bp", "He", "Fab", "Teo", "Tye", "Haa", "Vb", "Vrö", "Få", "Åsa", "Lek", "Kb", "Khe", "Lgd", "Ag", "Ldo", "Krd", "Mdn", "Am", "Lis", "Gro", "G"]
    AF = AG + ["Or", "Or1", "Gsv", "Säv", "Sel", "P", "Jv", "J", "Apn", "Asd", "Lr", "Sn", "Fd", "Ndv", "Ns", "Vbd", "Bgs", "A", "Agg", "Vgå", "Hr", "Kä", "Fby", "F"]
    AHrbg = AF + ["Fn", "Ss", "Rmtp", "Sk", "Vä", "Mh", "T", "Sle", "Äl", "Gdö", "Fa", "Lå", "Lln", "Vt", "Öj", "Täl", "Hrbg"]
    AK = AHrbg + ["Hpbg", "På", "Km", "Hgö", "Vr", "Bt", "K"]
    AFle = AK + ["Spn", "Sde", "Fle"]
    AAs = AFle + ["Skv", "Sp", "Nsj", "Sh", "B", "Koe", "Gn", "Mö", "Jn", "Söö", "Msj", "Bjn", "Flb", "Hu", "Sta", "Äs"]
    ACst = AAs + ["Åbe", "Sst", "Cst"]

    # length = 0
    # for i in range(len(ACst) - 1):
    #     length += infra.segments[(ACst[i], ACst[i+1])].length
    # print(length)
    # raise Exception

    HrbgA = list(reversed(AHrbg))
    KA = list(reversed(AK))
    CstA = list(reversed(ACst))
    FA = list(reversed(AF))

    route_dict = {"AG": AG, "AF": AF, "AHrbg": AHrbg, "AK": AK, "AFle": AFle, "AAs": AAs, "ACst": ACst, "HrbgA": HrbgA, "KA": KA, "CstA": CstA, "FA": FA}

    train_dict = {("GB201210", "AFle"): [44100, 44150], ("GB201210", "AHrbg"): [44980], ("GB201610", "ACst"): [41406], ("GB201610", "AG"): [46250], ("GB201610", "HrbgA"): [44723, 44725], ("GB201710", "AK"): [44906], ("GB201710", "KA"): [44905], ("GB201810", "AAs"): [49340], ("GB202010", "AHrbg"): [44990], ("GB221610", "HrbgA"): [44721], ("GB221610", "CstA"): [41755], ("GB401809", "AHrbg"): [40970, 40972], ("GB402308", "HrbgA"): [40971, 40973], ("GB931510", "AHrbg"): [44420], ("GEG02310", "AHrbg"): [44728, 44734, 44736], ("GR401410", "AHrbg"): [44200], ("GR401410", "ACst"): [9400], ("GR401410", "FA"): [4903], ("GR401509", "AHrbg"): [5166], ("GR401509", "AF"): [5134], ("GR401510", "ACst"): [4140], ("GR401610", "AHrbg"): [4300, 4168, 4190, 4194], ("GR401610", "AAs"): [4240], ("GR401610", "HrbgA"): [5711, 4191, 5611, 5617], ("GR422210", "HrbgA"): [4325], ("GR4E2608", "HrbgA"): [45513], ("PB930516", "HrbgA"): [3911], ("PB930516", "CstA"): [3943], ("PR600616", "CstA"): [9847], ("PR6A0414", "CstA"): [1, 345], ("PR6A0414", "ACst"): [2], ("PX2-2000", "CstA"): [507, 511, 545], ("PX2-2000", "ACst"): [502, 504, 548]}

    passenger_trains = [1, 3911, 502, 507, 511, 504, 345, 3943, 548, 545, 2, 9847]
    ordering = [1, 3911, 502, 507, 511, 504, 345, 3943, 548, 545, 2] + [44990, 44725, 4190, 40970, 4903, 40973, 44734, 4194, 41755, 44736, 5617, 5166, 5134, 45513, 4300, 5611, 40972, 4191, 40971, 4168, 46250, 5711, 49340, 44150, 9847, 44200, 9400, 41406, 4240, 44721, 44905, 44420, 44723, 44728, 44100, 4140, 4325, 44980, 44906]
    # bad_ordering = [44990, 44725, 4190, 40970, 4903, 40973, 44734, 4194, 41755, 44736, 5617, 5166, 5134, 45513, 4300, 5611, 40972, 4191, 40971, 4168, 46250, 5711, 49340, 44150, 9847, 44200, 9400, 41406, 4240, 44721, 44905, 44420, 44723, 44728, 44100, 4140, 4325, 44980, 44906] + [1, 3911, 502, 507, 511, 504, 345, 3943, 548, 545, 2]
    # ordering = bad_ordering

    shutil.copyfile("C:/Users/davde78/Documents/sos-project/data/t21.csv",
                    "C:/Users/davde78/Documents/sos-project/data/t21_temp.csv")
    shutil.copyfile("C:/Users/davde78/Documents/sos-project/data/t21_running_days.csv",
                    "C:/Users/davde78/Documents/sos-project/data/t21_running_days_temp.csv")

    # passenger_added = pd.read_csv("../out/indep-set-results-first-half-9847.csv", sep=";", encoding="utf-8")
    # for index, row in passenger_added.iterrows():
    #     id = row["id"]
    #     trnr = int(row["trnr"])
    #
    #     trnr_df = pd.read_csv(f"../data/candidate paths indep set/candidate_paths_{trnr}.csv", sep=";", encoding="utf-8")
    #     trnr_df = trnr_df[trnr_df["train_ix"] == id]
    #     target_time = datetime.strptime(trnr_df.iloc[-1]["time_start"], "%Y-%m-%d %H:%M:%S")
    #
    #     with open("C:/Users/davde78/Documents/sos-project/data/t21_running_days_temp.csv", "a", encoding="utf-8") as f:
    #         f.write(
    #             f"{id},{target_time.strftime('%Y-%m-%d')}\n")
    #
    #     for index, row in trnr_df.iterrows():
    #         with open("C:/Users/davde78/Documents/sos-project/data/t21_temp.csv", "a",
    #          encoding="utf-8") as f:
    #             if pd.isna(row["time_end"]):
    #                 f.write(f"0,{row['train_ix']},{row['train_id']},{row['variant']},0,{row['orig']},{row['dest']},{get_time(datetime.strptime(row['time_start'], '%Y-%m-%d %H:%M:%S'), target_time)},,0,{row['track_id']},0\n")
    #             else:
    #                 f.write(
    #                     f"0,{row['train_ix']},{row['train_id']},{row['variant']},0,{row['orig']},{row['dest']},{get_time(datetime.strptime(row['time_start'], '%Y-%m-%d %H:%M:%S'), target_time)},{get_time(datetime.strptime(row['time_end'], '%Y-%m-%d %H:%M:%S'), target_time)},0,{row['track_id']},0\n")
    requested_times = pd.read_csv("../data/requested_departure_arrival.csv", sep=";", encoding="utf-8")
    log_file = "../out/log.csv"
    # with open(log_file, "w+", encoding="utf-8") as f:
    #     f.write("New iteration loop;;;\n")

    # for trnr in ordering:
    #     for speed_profile, route in train_dict.keys():
    #         if trnr not in train_dict[(speed_profile, route)]:
    #             continue

    for speed_profile, route in train_dict.keys():
        for trnr in train_dict[(speed_profile, route)]:
            # if trnr in passenger_trains:
            #     continue

            for index, row in requested_times.iterrows():
                if row["trnr"] != trnr:
                    continue
                else:
                    req_departure = datetime.strptime(row["dep"], "%Y-%m-%d %H:%M:%S")
                    req_arrival = datetime.strptime(row["arr"], "%Y-%m-%d %H:%M:%S")
                    TIME_FROM_DATETIME = req_departure - timedelta(minutes=210)
                    TIME_TO_DATETIME = req_arrival + timedelta(minutes=210)
                    break

            output_file = f"../out/candidate_paths_only_freight_{trnr}.csv"
            start_time = time.time()

            train_route = route_dict[route]
            # train_to_insert = train_dict[(speed_profile, route)][0]

            source_file = "C:/Users/davde78/Documents/sos-project/data/t21_temp.csv"
            t21 = timetable_creation.get_timetable(TIME_FROM, TIME_TO, train_route, source_file)
            t21 = timetable_creation.remove_linjeplatser(t21, ["Drt", "Mon"])
            t21.to_csv("../data/filtered_t21.csv", sep=";")

            print("time until timetable reading complete", time.time() - start_time)

            running_time = timetable_creation.get_running_times(running_time_source, infra.linjeplatser, speed_profile)
            segments = [(train_route[i], train_route[i + 1]) for i in range(len(train_route) - 1)]

            print("time until running time reading complete", time.time() - start_time)

            # print(infra.stations)
            free_space_dict_stations = free_space_detection.get_free_spaces_stations(t21, trnr, TIME_FROM_DATETIME, TIME_TO_DATETIME, infra.stations)
            # print(free_space_dict_stations)
            print("time until station free spaces complete", time.time() - start_time)
            free_space_dict_transitions = free_space_detection.get_free_spaces_transitions(t21, trnr, TIME_FROM_DATETIME, TIME_TO_DATETIME, infra.transitions)
            # print(free_space_dict_transitions)
            print("time until transition free spaces complete", time.time() - start_time)
            free_space_dict_segments = free_space_detection.get_free_spaces_segments(t21, trnr, TIME_FROM_DATETIME, TIME_TO_DATETIME, segments, infra)
            # print(free_space_dict_segments)
            print("time until segment free spaces complete", time.time() - start_time)

            end_of_prep = time.time()

            if log_file != "":
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"{trnr};precomputations;{end_of_prep - start_time}\n")

            print("Preparation time", end_of_prep - start_time)

            generate_candidate_paths(infra, trnr, speed_profile, running_time, t21, TIME_FROM_DATETIME, TIME_TO_DATETIME, train_route, output_file, filter_close_paths, free_space_dict_stations, free_space_dict_segments, free_space_dict_transitions, log_file, req_departure, req_arrival, True)
            end_of_alg = time.time()
            print("Running time", end_of_alg - end_of_prep)


if __name__ == '__main__':
    generate_many_paths()
    raise Exception

    """
    # m_infra = Infrastructure("../config_RailDresden.txt/infrastructure-details-motional.txt", "../config_RailDresden.txt/conflict_margins.txt")
    m_infra = Infrastructure("../config_RailDresden.txt/infrastructure-details-RailDresden.txt", "../config_RailDresden.txt/conflict_margins.txt")
    fullstart = time.time()
    running_time_source = "../data/generated_running_times.csv"
    # running_time_source = "../data/t21_technical_running_times.csv"

    # Time frame to be considered
    m_TIME_FROM = "2021-03-13 23:00"
    m_TIME_TO = "2021-03-15 07:00"
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
    # m_train_route = ["G", "Or", "Or1", "Gsv", "Säv", "Sel", "P", "Jv", "J", "Apn", "Asd", "Lr", "Sn", "Fd", "Ndv", "Ns", "Vbd", "Bgs", "A", "Agg", "Vgå", "Hr", "Kä", "Fby", "F", "Fn", "Ss", "Rmtp", "Sk", "Vä", "Mh", "T", "Sle", "Äl", "Gdö"]
    # m_train_route = ["G", "Or", "Or1", "Gsv", "Säv", "Sel", "P", "Jv", "J", "Apn", "Asd", "Lr", "Sn", "Fd", "Ndv", "Ns", "Vbd", "Bgs", "A", "Agg", "Vgå", "Hr", "Kä", "Fby", "F", "Fn", "Ss", "Rmtp", "Sk", "Vä", "Mh", "T", "Sle", "Äl", "Gdö", "Fa", "Lå", "Lln", "Vt", "Öj", "Täl", "Hrbg", "Hpbg", "På", "Km", "Hgö", "Vr", "Bt", "K", "Spn", "Sde", "Fle", "Skv", "Sp", "Nsj", "Sh", "B", "Koe", "Gn", "Mö", "Jn", "Söö", "Msj", "Bjn", "Flb", "Hu", "Sta", "Äs", "Åbe", "Sst", "Cst"]
    m_train_route = ["Ä", "Baa", "Vip", "För", "Bån", "Laov", "Ea", "Kst", "Hdr", "Hd", "Fur", "Btp", "Bp", "He", "Fab", "Teo", "Tye", "Haa", "Vb", "Vrö", "Få", "Åsa", "Lek", "Kb", "Khe", "Lgd", "Ag", "Ldo", "Krd", "Mdn", "Am", "Lis", "Gro", "G", "Or", "Or1", "Gsv", "Säv", "Sel", "P", "Jv", "J", "Apn", "Asd", "Lr", "Sn", "Fd", "Ndv", "Ns", "Vbd", "Bgs", "A", "Agg", "Vgå", "Hr", "Kä", "Fby", "F", "Fn", "Ss", "Rmtp", "Sk", "Vä", "Mh", "T", "Sle", "Äl", "Gdö", "Fa", "Lå", "Lln", "Vt", "Öj", "Täl", "Hrbg", "Hpbg", "På", "Km", "Hgö", "Vr", "Bt", "K", "Spn", "Sde", "Fle", "Skv", "Sp", "Nsj", "Sh", "B", "Koe", "Gn", "Mö", "Jn", "Söö", "Msj", "Bjn", "Flb", "Hu", "Sta", "Äs", "Åbe", "Sst", "Cst"]
    m_train_route = list(reversed(m_train_route))

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
    """