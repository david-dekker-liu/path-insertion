import numpy as np
import pandas as pd
from datetime import datetime
from datetime import timedelta
import src.free_space_detection as free_space_detection
import src.timetable_creation as timetable_creation
import src.interval_utils as intutils
from src.intervals import LinkedInterval, Interval

# TODO Test first if it is a predefined exception,
# TODO i.e., single-track line with smaller blocks.


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
    TIME_FROM = "2021-01-20 01:00"
    TIME_TO = "2021-01-20 23:00"
    TIME_FROM_DATETIME = datetime.strptime(TIME_FROM, "%Y-%m-%d %H:%M")
    TIME_TO_DATETIME = datetime.strptime(TIME_TO, "%Y-%m-%d %H:%M")

    # Manual list of vertices to be explored
    # Derive the filtered t21 timetable, export it and detect Parallelfahrts
    train_route = ["Gsv", "Or1", "Or", "Gbm", "Agb", "Sue", "Bhs", "Nöe", "Nol", "Än", "Alh", "Les", "Tbn", "Vpm", "Veas", "Thn", "Öx", "Bjh", "Fdf", "Brl", "Skbl", "Rås", "Drt", "Bäf", "Ed", "Mon", "Ko"]

    t21 = timetable_creation.get_timetable(TIME_FROM, TIME_TO, train_route)
    t21.to_csv("../data/filtered_t21.csv", sep=";")

    # timetable_creation.verify_timetable_consistency(t21)

    train_to_insert = 45693
    free_space_dict = free_space_detection.get_free_spaces(t21, train_to_insert, TIME_FROM_DATETIME, TIME_TO_DATETIME)

    technical_running_times = pd.read_csv("../data/t21_technical_running_times.csv")
    speed_profile = "GB201010"
    running_time = {}
    for index, row in technical_running_times[technical_running_times["train_type"] == speed_profile].iterrows():
        running_time[(row["stn_id_from"], row["stn_id_to"], "r", "r")] = row["rt_forw_pp"]
        running_time[(row["stn_id_from"], row["stn_id_to"], "r", "s")] = row["rt_forw_ps"]
        running_time[(row["stn_id_from"], row["stn_id_to"], "s", "r")] = row["rt_forw_sp"]
        running_time[(row["stn_id_from"], row["stn_id_to"], "s", "s")] = row["rt_forw_ss"]
        running_time[(row["stn_id_to"], row["stn_id_from"], "r", "r")] = row["rt_forw_pp"]
        running_time[(row["stn_id_to"], row["stn_id_from"], "r", "s")] = row["rt_forw_ps"]
        running_time[(row["stn_id_to"], row["stn_id_from"], "s", "r")] = row["rt_forw_sp"]
        running_time[(row["stn_id_to"], row["stn_id_from"], "s", "s")] = row["rt_forw_ss"]

    # Get minimum running time for the full path
    min_time = 0
    min_time += running_time[("Gsv", "Or1", "s", "r")]
    min_time += running_time[("Mon", "Ko", "r", "s")]
    for i in range(len(train_route) - 3):
        min_time += running_time[(train_route[i+1], train_route[i+2], "r", "r")]
    print(f"Minimum travel time for profile {speed_profile} on Gsv-Ko: {min_time}")

    # For each single-track segment, obtain the free-space list
    # The free_space_dict maps from segment keys to a list of free slots
    # In the single track case, these are rectangles indicated by their start- and endtime
    usable_tracks = {("Gsv", "Or1"): ["U"], ("Or1", "Or"): ["E"], ("Or", "Gbm"): ["A"], ("Gbm", "Agb"): ["U"], ("Agb", "Sue"): ["U"], ("Sue", "Bhs"): ["U"], ("Bhs", "Nöe"): ["U"], ("Nöe", "Nol"): ["U"], ("Nol", "Än"): ["U"], ("Än", "Alh"): ["U"], ("Alh", "Les"): ["U"], ("Les", "Tbn"): ["U"], ("Tbn", "Vpm"): ["U"], ("Vpm", "Veas"): ["U"], ("Veas", "Thn"): ["U"], ("Thn", "Öx"): ["U"], ("Öx", "Bjh"): ["E"], ("Bjh", "Fdf"): ["E"], ("Fdf", "Brl"): ["E"], ("Brl", "Skbl"): ["E"], ("Skbl", "Rås"): ["E"], ("Rås", "Drt"): ["E"], ("Drt", "Bäf"): ["E"], ("Bäf", "Ed"): ["E"], ("Ed", "Mon"): ["E"], ("Mon", "Ko"): ["E"]}

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
        station_parked_occupations[(first_loc, station_track)] = [LinkedInterval(x[0], x[1], x[0], x[1]) for x in free_space_dict[get_key(first_loc, None, station_track)]]
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
            print(current_vertex, station_track, allowed_next_tracks)

            for next_track in allowed_next_tracks:
                if next_track not in entering_main_segment_candidates_after_stop.keys():
                    entering_main_segment_candidates_after_stop[next_track] = []
                    entering_main_segment_candidates_after_runthrough[next_track] = []

                print(station_parked_occupations[(current_vertex, station_track)])
                entering_main_segment_candidates_after_stop[next_track] += [intutils.intersect_intervals(station_parked_occupations[(current_vertex, station_track)], free_space_dict[get_transition_key(current_vertex, next_vertex, station_track, next_track, False)])]

                entering_main_segment_candidates_after_runthrough[next_track] += [intutils.intersect_intervals(station_runthrough_occupations[(current_vertex, station_track)], free_space_dict[
                    get_transition_key(current_vertex, next_vertex, station_track, next_track, False)])]

        # Then, modify the dictionary entries by merging the list of interval lists to one interval list
        for next_track in entering_main_segment_candidates_after_stop.keys():
            entering_main_segment_candidates_after_stop[next_track] = intutils.merge_intervals(entering_main_segment_candidates_after_stop[next_track])

            entering_main_segment_candidates_after_runthrough[next_track] = intutils.merge_intervals(entering_main_segment_candidates_after_runthrough[next_track])

        # Now extend this for the segments
        # Start from the segment free spaces, and map each segment free space to a (possibly empty) list of time intervals to enter the segment
        # Perhaps (is this needed?) make sure that the corr starting times are strictly increasing, so remove any bit that is below two other values.
        # E.g.: if one interval is 8-11 and a later one has starting times 10-16, drop 10-11 of the second one, as you could also start at 11 and get there at that time

        # Now duplicate both to get such a mapping for all four stopping patterns
        # Then extrapolate each segment free space (i.e. add min running time)
        # If no interval is present after the segment, add a bonus "slow moving" segment with constant departure time.

        for next_track in entering_main_segment_candidates_after_stop.keys():
            # Determine interval lists for the next station by extending with the appropriate running time
            leaving_segment_list_ss = intutils.evaluate_running_times(entering_main_segment_candidates_after_stop, free_space_dict[get_key(current_vertex, next_vertex, next_track)], running_time[(current_vertex, next_vertex, "s", "s")])
            leaving_segment_list_sr = intutils.evaluate_running_times(entering_main_segment_candidates_after_stop, free_space_dict[get_key(current_vertex, next_vertex, next_track)], running_time[(current_vertex, next_vertex, "s", "r")])
            leaving_segment_list_rs = intutils.evaluate_running_times(entering_main_segment_candidates_after_runthrough, free_space_dict[get_key(current_vertex, next_vertex, next_track)], running_time[(current_vertex, next_vertex, "r", "s")])
            leaving_segment_list_rr = intutils.evaluate_running_times(entering_main_segment_candidates_after_runthrough, free_space_dict[get_key(current_vertex, next_vertex, next_track)], running_time[(current_vertex, next_vertex, "r", "r")])

            leaving_segment_towards_stop = intutils.merge_intervals([leaving_segment_list_rs, leaving_segment_list_ss])
            leaving_segment_towards_runthrough = intutils.merge_intervals([leaving_segment_list_rr, leaving_segment_list_sr])

            for entering_track in allowed_movements_at_arrival[(current_vertex, next_vertex, next_vertex, None, next_track)]:
                if entering_track not in entering_station_candidates_towards_stop.keys():
                    entering_station_candidates_towards_stop[entering_track] = []
                    entering_station_candidates_towards_runthrough[entering_track] = []

                entering_station_candidates_towards_stop[entering_track] += [intutils.intersect_intervals(leaving_segment_towards_stop, free_space_dict[get_transition_key(current_vertex, next_vertex, next_track, entering_track, True)])]

                entering_station_candidates_towards_runthrough[entering_track] += [intutils.intersect_intervals(leaving_segment_towards_runthrough, free_space_dict[get_transition_key(current_vertex, next_vertex, next_track, entering_track, True)])]

        for entering_track in entering_station_candidates_towards_stop.keys():
            entering_station_candidates_towards_stop[entering_track] = intutils.merge_intervals(
                entering_station_candidates_towards_stop[entering_track])

            entering_station_candidates_towards_runthrough[entering_track] = intutils.merge_intervals(
                entering_station_candidates_towards_runthrough[entering_track])

        for station_track in entering_station_candidates_towards_stop.keys():
            station_parked_occupations[(next_vertex, station_track)] = intutils.extend_parked_times(entering_station_candidates_towards_stop[station_track], free_space_dict[next_vertex + "/" + station_track])

            station_runthrough_occupations[(next_vertex, station_track)] = entering_station_candidates_towards_runthrough[station_track]