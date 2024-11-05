import pandas as pd

import interval_utils

pd.options.mode.chained_assignment = None  # default='warn'
import headway_functions
import numpy as np
from intervals import Interval, IntervalPair


def get_free_spaces_stations(t21, train_to_insert, TIME_FROM_DATETIME, TIME_TO_DATETIME, relevant_stations):
    free_space_dict = {}

    for station in relevant_stations:
        for track_id in relevant_stations[station].tracks:
            relevant_timetable = t21[(t21["orig"] == station) & (t21["dest"].isnull()) & (t21["track_id"] == track_id)]

            # Again, get consecutive occupations
            relevant_timetable = relevant_timetable.sort_values(["time_start_corrected"])
            relevant_timetable_merged = pd.concat(
                [relevant_timetable, relevant_timetable.shift(-1).add_prefix("next_")], axis=1)

            # Headways wrt the train to be inserted
            min_headway_before = headway_functions.get_min_block_diff_at_station_before(train_to_insert, station, track_id)
            min_headway_after = headway_functions.get_min_block_diff_at_station_after(train_to_insert, station, track_id)

            # The previous train leaves the segment at time_end_corrected
            # It then cannot be used for min_headway_after of that train,
            # but also not for the min headway before the train to be added
            relevant_timetable_merged["free_space_start"] = relevant_timetable_merged[
                                                                "time_end_corrected"] + pd.to_timedelta(
                np.maximum(min_headway_before, relevant_timetable_merged['min_headway_after']), 's')
            relevant_timetable_merged["free_space_end"] = relevant_timetable_merged[
                                                              "next_time_start_corrected"] - pd.to_timedelta(
                np.maximum(min_headway_after, relevant_timetable_merged['next_min_headway_before']), 's')
            relevant_timetable_merged = relevant_timetable_merged[
                relevant_timetable_merged["free_space_start"] <= relevant_timetable_merged["free_space_end"]]

            free_space_start = relevant_timetable_merged["free_space_start"].tolist()
            free_space_end = relevant_timetable_merged["free_space_end"].tolist()

            if relevant_timetable.shape[0] == 0:
                free_space_dict[(station, track_id)] = [
                    Interval(pd.to_datetime(TIME_FROM_DATETIME), pd.to_datetime(TIME_TO_DATETIME))]
            elif relevant_timetable.shape[0] == 1:
                row = relevant_timetable.iloc[0]
                free_space_dict[(station, track_id)] = [
                    Interval(pd.to_datetime(TIME_FROM_DATETIME), row["time_start_corrected"]),
                    Interval(row["time_end_corrected"], pd.to_datetime(TIME_TO_DATETIME))
                    ]
            else:
                first_blockage_start = relevant_timetable_merged.iloc[0][
                                           "time_start_corrected"] - pd.to_timedelta(
                    np.maximum(min_headway_after, relevant_timetable_merged.iloc[0]['min_headway_before']), 's')
                last_blockage_end = relevant_timetable_merged.iloc[-1][
                                        "next_time_end_corrected"] + pd.to_timedelta(
                    np.maximum(min_headway_after, relevant_timetable_merged.iloc[-1]['next_min_headway_after']), 's')

                if first_blockage_start > TIME_FROM_DATETIME:
                    free_space_start = [pd.to_datetime(TIME_FROM_DATETIME)] + free_space_start
                    free_space_end = [first_blockage_start] + free_space_end

                if last_blockage_end < TIME_TO_DATETIME:
                    free_space_start = free_space_start + [last_blockage_end]
                    free_space_end = free_space_end + [pd.to_datetime(TIME_TO_DATETIME)]

                free_space_dict[(station, track_id)] = [Interval(x, y) for x, y in list(zip(free_space_start, free_space_end))]
    return free_space_dict


def get_free_spaces_transitions(t21, train_to_insert, TIME_FROM_DATETIME, TIME_TO_DATETIME, relevant_transitions):
    free_space_dict = {}
    # Get consecutive pairs (with same train id) in t21, as they all indicate a transition,
    # and derive its 'key', i.e., the quadruple
    # TODO may go wrong when segment track ids and station track ids coincide!
    # for index, row in t21.iterrows():
    #     print(row["train_ix"], row["time_start_corrected"], row["orig"], row["dest"])
    t21_merged = pd.concat([t21, t21.shift(-1).add_prefix("next_")], axis=1)
    t21_merged["transition"] = t21_merged.apply(lambda row: (row["orig"], row["track_id"], row["next_orig"], row["next_track_id"]) if pd.isnull(row["next_dest"]) else (row["orig"], row["track_id"], row["next_dest"], row["next_track_id"]), axis=1)
    t21_merged = t21_merged[t21_merged["train_ix"] == t21_merged["next_train_ix"]]

    # Pre-process the transitions
    for transition in relevant_transitions:
        # print("curr trans", transition)
        # All conflicting ones
        conflicting_transitions = relevant_transitions[transition]
        conflicts = [x[0] for x in conflicting_transitions]
        conflicting_transitions_dict_before = {}
        conflicting_transitions_dict_after = {}

        # A transition can give multiple conflicts (i.e., block some time before and after it)
        # We merge those here, and transform them to a dict

        # Iterate over all conflicts that we may need to merge
        for conf in set(conflicts):
            # print(conf)
            conf_to_merge = [v for v in conflicting_transitions if v[0] == conf]

            # We don't expect more than two, otherwise, look into it
            if len(conf_to_merge) > 2:
                raise Exception("Problems with merging", conf_to_merge)
            # If only 1 match, nothing needs to happen
            elif len(conf_to_merge) == 1:
                transition_to_merge = conf_to_merge[0]
                conflicting_transitions_dict_before[conf] = transition_to_merge[1]
                conflicting_transitions_dict_after[conf] = transition_to_merge[2]
            # If no matches we messed something up
            elif len(conf_to_merge) == 0:
                raise Exception("Messed this up, nothing to merge.")
            else:
                # In this case, exactly two matches.
                # We maintain the largest margin before and after the conflict
                # and insert that as a new transition instead of the two diff ones
                min_time = 0
                max_time = 0
                for merge_conf in conf_to_merge:
                    min_time = max(min_time, merge_conf[1])
                    max_time = max(max_time, merge_conf[2])
                conflicting_transitions_dict_before[conf] = min_time
                conflicting_transitions_dict_after[conf] = max_time

        relevant_timetable = t21_merged[t21_merged["transition"].isin(conflicts)]
        # print(relevant_timetable.shape[0])
        relevant_timetable["transition_time_before"] = relevant_timetable["transition"].map(conflicting_transitions_dict_before)
        relevant_timetable["transition_time_after"] = relevant_timetable["transition"].map(
            conflicting_transitions_dict_after)

        if relevant_timetable.shape[0] == 0:
            free_space_dict[transition] = [Interval(TIME_FROM_DATETIME, TIME_TO_DATETIME)]
            continue

        relevant_timetable["transition_start"] = relevant_timetable["time_end_corrected"] - pd.to_timedelta(relevant_timetable["transition_time_before"], 's')
        relevant_timetable["transition_end"] = relevant_timetable["time_end_corrected"] + pd.to_timedelta(relevant_timetable["transition_time_after"], 's')

        intervals = [Interval(x, y) for x, y in list(zip(relevant_timetable["transition_start"].tolist(), relevant_timetable["transition_end"].tolist()))]

        merged_intervals = interval_utils.merge_normal_lists(intervals)
        free_space_dict[transition] = interval_utils.interval_complement(merged_intervals, TIME_FROM_DATETIME, TIME_TO_DATETIME)

    return free_space_dict


def get_free_spaces_segments(t21, train_to_insert, TIME_FROM_DATETIME, TIME_TO_DATETIME, relevant_segments, infra):
    free_space_dict = {}
    for segment in relevant_segments.keys():
        orig = segment[0]
        dest = segment[1]
        corresponding_segment = infra.segments[(orig, dest)]

        for track in corresponding_segment.tracks:
            infra_segment = infra.segments[segment]
            if len(infra_segment.tracks) > 1:
                min_headway_before = headway_functions.get_headway_before(train_to_insert, orig, dest)
                min_headway_after = headway_functions.get_headway_after(train_to_insert, orig, dest)

                relevant_timetable = t21[(t21["orig"] == orig) & (t21["dest"] == dest) & (t21["track_id"] == track)]

                relevant_timetable["blocks_from_orig"] = relevant_timetable["time_start_corrected"] - pd.to_timedelta( np.maximum(min_headway_after, relevant_timetable["min_headway_before"]), 's')
                relevant_timetable["blocks_until_orig"] = relevant_timetable["time_start_corrected"] + pd.to_timedelta(np.maximum(min_headway_before, relevant_timetable['min_headway_after']), 's')
                relevant_timetable["blocks_from_dest"] = relevant_timetable["time_end_corrected"] - pd.to_timedelta(np.maximum(min_headway_after, relevant_timetable["min_headway_before"]), 's')
                relevant_timetable["blocks_until_dest"] = relevant_timetable["time_end_corrected"] + pd.to_timedelta(np.maximum(min_headway_before, relevant_timetable['min_headway_after']), 's')

            elif len(infra_segment.tracks) == 1:
                relevant_timetable = t21[((t21["orig"] == orig) & (t21["dest"] == dest) | (t21["orig"] == dest) & (t21["dest"] == orig)) & (t21["track_id"] == track)]

                relevant_timetable["blocks_from_orig"] = relevant_timetable["time_start_corrected"] - pd.to_timedelta(60, 's')
                relevant_timetable["blocks_until_orig"] = relevant_timetable["time_end_corrected"] + pd.to_timedelta(60, 's')
                relevant_timetable["blocks_from_dest"] = relevant_timetable["time_start_corrected"] - pd.to_timedelta(60, 's')
                relevant_timetable["blocks_until_dest"] = relevant_timetable["time_end_corrected"] + pd.to_timedelta(60, 's')

            # elif len(infra_segment.tracks) == 1:
            #     relevant_timetable = t21[((t21["orig"] == orig) & (t21["dest"] == dest) | (t21["orig"] == dest) & (t21["dest"] == orig)) & (t21["track_id"] == track)]
            #
            #     largest_block_fraction = infra.complex_segments[(orig, dest)][1]
            #     relevant_timetable["block_occupation_length"] = (relevant_timetable["time_end_corrected"] - relevant_timetable["time_start_corrected"]).dt.seconds * largest_block_fraction
            #
            #     relevant_timetable["blocks_from_orig"] = relevant_timetable.apply(lambda x: x["time_start_corrected"] - pd.to_timedelta(60, 's') if x["orig"] == dest else x["time_start_corrected"] - pd.to_timedelta(x["block_occupation_length"], 's'), axis=1)
            #
            #     relevant_timetable["blocks_until_orig"] = relevant_timetable.apply(lambda x: x["time_end_corrected"] + pd.to_timedelta(60, 's') if x["orig"] == dest else x["time_start_corrected"] + pd.to_timedelta(x["block_occupation_length"], 's'), axis=1)
            #
            #     relevant_timetable["blocks_from_dest"] = relevant_timetable.apply(lambda x: x["time_start_corrected"] - pd.to_timedelta(60, 's') if x["orig"] == dest else x["time_end_corrected"] - pd.to_timedelta(x["block_occupation_length"], 's'), axis=1)
            #
            #     relevant_timetable["blocks_until_dest"] = relevant_timetable.apply(lambda x: x["time_end_corrected"] + pd.to_timedelta(60, 's') if x["orig"] == dest else x["time_end_corrected"] + pd.to_timedelta(x["block_occupation_length"], 's'), axis=1)
            #
            else:
                raise Exception("No tracks found at segment")

            relevant_timetable = relevant_timetable.sort_values(by=["time_start_corrected"])

            blocks_from_orig = relevant_timetable["blocks_from_orig"].tolist() + [TIME_TO_DATETIME]
            blocks_until_orig = [TIME_FROM_DATETIME] + relevant_timetable["blocks_until_orig"].tolist()
            blocks_from_dest = relevant_timetable["blocks_from_dest"].tolist() + [TIME_TO_DATETIME]
            blocks_to_dest = [TIME_FROM_DATETIME] + relevant_timetable["blocks_until_dest"].tolist()

            free_spaces = list(zip(blocks_until_orig, blocks_from_orig, blocks_to_dest, blocks_from_dest))
            free_space_dict[(orig, dest, track)] = [IntervalPair(first_start, first_end, second_start, second_end) for first_start, first_end, second_start, second_end in free_spaces if first_start < first_end and second_start < second_end]

    return free_space_dict