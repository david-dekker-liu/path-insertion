import pandas as pd
from datetime import timedelta, time
from datetime import datetime
import numpy as np
import time as tm
import src.headway_functions as headway_functions
import src.path_insertion as path_insertion


def get_timetable(time_from, time_to, locations):
    # The database contains two types of records:
    # * Arrival/Departure at trafikplats
    # * Entrance/Leaving at a segment between two adjacent trafikplatser
    # We will use both

    # First, all days between FROM.date - 2 and TO.date are included,
    # to get all potential relevant times (no train departs 3 days before passing some location)
    # To make sure that headways with just out-of-window trains are ok,
    # we use a slightly larger time frame
    time_from_datetime = datetime.strptime(time_from, "%Y-%m-%d %H:%M")
    time_from_datetime_floored = datetime.combine(time_from_datetime.date(), time(0, 0, 0)) - timedelta(days=2)
    time_from_datetime_min10 = time_from_datetime - timedelta(minutes=10)
    time_to_datetime = datetime.strptime(time_to, "%Y-%m-%d %H:%M")
    time_to_datetime_ceiled = datetime.combine(time_to_datetime.date(), time(23, 59, 59))
    time_to_datetime_plus10 = time_to_datetime + timedelta(minutes=10)

    # Read timetable databases, select possibly relevant days and join them
    df_input = pd.read_csv("../data/t21.csv", sep=",")
    df = df_input[df_input["orig"].isin(locations) | df_input["dest"].isin(locations)]

    df_running_specs = pd.read_csv("../data/t21_running_days.csv", sep=",")
    df_running_specs["date_datetime"] = pd.to_datetime(df_running_specs['date'], format='%Y-%m-%d')
    df_running_specs = df_running_specs[(df_running_specs["date_datetime"] >= time_from_datetime_floored) & (df_running_specs["date_datetime"] <= time_to_datetime_ceiled)]

    df = pd.merge(df, df_running_specs, on="train_ix")

    print("Finished joining input tables")

    # All "start at station" and "terminate at station" events are hereby removed
    # Without known uppehållstid, those events will not be used while they cause NaN-value issues
    # It would be preferable to use the uppehållstid to fill the NaN-values,
    # then each train blocks the departure/arrival track for at least uppehållstid
    df = df.dropna(subset=['time_start', 'time_end'])

    # Now on our way to select the precise relevant times
    df["time_end_hour"] = df["time_end"].str[0:2]
    df["time_end_hour"] = df["time_end_hour"].astype('int')
    df["time_end_hour_modulo"] = df["time_end_hour"] % 24
    df["time_end_plus_days"] = df["time_end_hour"] // 24
    df["time_end_reformat"] = df["time_end_hour_modulo"].astype('str') + df["time_end"].str[2:]
    df["time_end_date_and_time"] = df["date"] + " " + df["time_end_reformat"]
    df["time_end_datetime"] = pd.to_datetime(df['time_end_date_and_time'], format='%Y-%m-%d %H:%M:%S')
    df["time_end_corrected"] = pd.to_datetime(df['time_end_datetime']) + pd.to_timedelta(df['time_end_plus_days'], 'd')
    df['time_end_corrected_time_str'] = df["time_end_corrected"].dt.strftime("%H:%M:%S")
    df['time_end_corrected_date_str'] = df["time_end_corrected"].dt.strftime("%Y-%m-%d")

    print("Finished adjusting end times")

    df["time_start_hour"] = df["time_start"].str[0:2]
    df["time_start_hour"] = df["time_start_hour"].astype('int')
    df["time_start_hour_modulo"] = df["time_start_hour"] % 24
    df["time_start_plus_days"] = df["time_start_hour"] // 24
    df["time_start_reformat"] = df["time_start_hour_modulo"].astype('str') + df["time_start"].str[2:]
    df["time_start_date_and_time"] = df["date"] + " " + df["time_start_reformat"]
    df["time_start_datetime"] = pd.to_datetime(df['time_start_date_and_time'], format='%Y-%m-%d %H:%M:%S')
    df["time_start_corrected"] = pd.to_datetime(df['time_start_datetime']) + pd.to_timedelta(df['time_start_plus_days'], 'd')
    df['time_start_corrected_time_str'] = df["time_start_corrected"].dt.strftime("%H:%M:%S")
    df['time_start_corrected_date_str'] = df["time_start_corrected"].dt.strftime("%Y-%m-%d")

    print("Finished adjusting start times")

    # TODO removed segment keys, improve this part
    df["segment_key"] = df.apply(lambda row: path_insertion.get_key(row["orig"], row["dest"], row["track_id"]), axis=1)
    df["segment_type"] = df.apply(lambda row: path_insertion.get_segment_type_from_row(row), axis=1)
    df["min_headway_before"] = df.apply(lambda row: headway_functions.headway_before(row), axis=1)
    df["min_headway_after"] = df.apply(lambda row: headway_functions.headway_after(row), axis=1)

    df_filtered = df[((df["time_start_corrected"] >= time_from_datetime_min10) & (
                df["time_start_corrected"] <= time_to_datetime_plus10))
            | ((df["time_end_corrected"] >= time_from_datetime_min10) & (
                df["time_end_corrected"] <= time_to_datetime_plus10))
            | ((df["time_start_corrected"] <= time_from_datetime_min10) & (
                df["time_end_corrected"] >= time_to_datetime_plus10))]

    print("Completed preprocessing of T21\n")

    return df_filtered.drop(columns=["stn_ix", "activity", "stop_is_possible", "date_datetime", "time_end_hour", "time_end_hour_modulo", "time_end_plus_days", "time_end_reformat", "time_end_date_and_time", "time_end_datetime", "time_end_corrected_time_str", "time_end_corrected_date_str", "time_start_hour", "time_start_hour_modulo", "time_start_plus_days", "time_start_reformat", "time_start_date_and_time", "time_start_datetime", "time_start_corrected_time_str", "time_start_corrected_date_str"])


# Example of conflicting track numbers:
# Location  start       end         track   train_id
# Åba       10:58:45    10:58:45    2       228
# Åba       10:59:00    11:00:00    2       227
# (and: not exactly conflict-free even with different track numbers)

# Linköping contains some duplicates:
# orig  dest    start       end         track   train_id
# Lp    nan     21:35:00    21:38:00    2       3934
# Lp    Lp      21:38:00    21:39:48    U       3934
# Lp    nan     21:39:48    21:39:48    2       3934

# Detected Parallelfahrten:
# Nr -> Fi at time 10:22:21 to time 10:28:08 on 2021-01-10. Train_ix 10774, train_id 47213
# Nr -> Fi at time 10:24:00 to time 10:27:25 on 2021-01-10. Train_ix 17156, train_id 2115
# Gi -> Nh at time 25:54:54 to time 25:58:54 on 2021-01-10. Train_ix 12001, train_id 4240
# Gi -> Nh at time 01:55:29 to time 01:57:32 on 2021-01-11. Train_ix 19934, train_id 8784
# Unfortunately, the parallel trains use the same track_id in the data
# Otherwise, grouping by track_id might work very nicely
# The current situation gives problems when determining the free spaces based on two consecutive
# trains, since they might no longer be consecutive at the end trafikplats
# (on the other hand, these problems are probably not as bad as the completely missing train
#  in opposite direction lol)
def verify_timetable_consistency(timetable):
    all_keys = timetable["segment_key"].drop_duplicates().tolist()
    print(all_keys)

    for segment_key in all_keys:
        # Station key
        if "/" in segment_key:
            continue

        filtered_t21 = timetable[timetable["segment_key"] == segment_key].sort_values(by=["time_start_corrected"])

        prev_end_time = datetime.min
        curr_descr = ""

        for m_index, row in filtered_t21.iterrows():
            current_end_time = row["time_end_corrected"]

            if current_end_time <= prev_end_time:
                print("Problems encountered with the following pair of trains.")
                print(curr_descr)
                curr_descr = f"Current record: {segment_key} at time {row['time_start']} to time {row['time_end']} on {row['date']}. Train_ix {row['train_ix']}, train_id {row['train_id']}."
                print(curr_descr + "\n")

            curr_descr = f"Current record: {segment_key} at time {row['time_start']} to time {row['time_end']} on {row['date']}. Train_ix {row['train_ix']}, train_id {row['train_id']}."
            prev_end_time = current_end_time


# Takes a timetable dataframe, a list of stations to consider and the name of a log file
def detect_track_allocation_problems(t21, stations, log_file):
    for station in stations:
        print(station)
        df = t21[(t21["orig"] == station) & (t21["dest"].isnull())].sort_values("time_start_corrected")
        events = []
        for index, row in df.iterrows():
            events += [("start", row["time_start_corrected"] - timedelta(0, 70), row["track_id"], row["train_id"], row["train_ix"])]
            events += [("end", row["time_end_corrected"] + timedelta(0, 70), row["track_id"], row["train_id"], row["train_ix"])]
        events.sort(key=lambda x: x[1])

        track_dict = {}
        for event in events:
            # print(event)
            if event[0] == "start" and event[2] in track_dict:
                print("problems between", track_dict[event[2]], "and", (event[3], event[4]), "at track", event[2])
            elif event[0] == "start":
                track_dict[event[2]] = (event[3], event[4])
            else:
                track_dict.pop(event[2], None)
        print("")


# Replaces linjeplatser one by one
# The first occurrence of the linjeplats is replaced by the last dest-value with that linjeplats
# All other rows with the linjeplats are removed
# TODO first split train numbers into different ids, this function collapses under back-and-forth behavior
# TODO verify that no trains start and end in the linjeplats, the function also collapses then
def remove_linjeplatser(t21, linjeplatser):
    for linjeplats in linjeplatser:
        t21_to_change = t21[(t21["orig"] == linjeplats) | (t21["dest"] == linjeplats)]
        train_ixs = t21_to_change["train_ix"].drop_duplicates().tolist()

        for train_ix in train_ixs:
            relevant_df = t21_to_change[t21_to_change["train_ix"] == train_ix]
            first_index = None
            other_indices = []
            last_dest = ""
            last_time = ""
            last_time_corr = ""

            for index, row in relevant_df.iterrows():
                if first_index is None:
                    first_index = index
                else:
                    other_indices += [index]

                last_dest = row["dest"]
                last_time = row["time_end"]
                last_time_corr = row["time_end_corrected"]
            t21.loc[first_index, ["dest", "time_end", "time_end_corrected"]] = [last_dest, last_time, last_time_corr]
            t21.drop(other_indices, inplace=True)

    return t21


def get_running_times(running_times_file, lineplatser, speed_profile):
    technical_running_times = pd.read_csv(running_times_file)

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

    for linjeplats in lineplatser:
        segment = lineplatser[linjeplats]
        for route in segment, list(reversed(segment)):
            for rs_start in ["r", "s"]:
                for rs_end in ["r", "s"]:
                    runtime = 0
                    runtime += running_time[(route[0], route[1], rs_start, "r")]
                    runtime += running_time[(route[-2], route[-1], "r", rs_end)]
                    for i in range(len(lineplatser) - 2):
                        runtime += running_time[(route[i+1], route[i+2], "r", "r")]
                    running_time[(route[0], route[-1], rs_start, rs_end)] = runtime

    print(running_time)
    return running_time
