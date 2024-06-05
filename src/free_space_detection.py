import pandas as pd
import headway_functions
import numpy as np


def get_free_spaces(t21, train_to_insert, TIME_FROM_DATETIME, TIME_TO_DATETIME):
    free_space_dict = {}
    # Get all keys that belong to double track / single track / stations
    double_track_segments = t21[t21["segment_type"] == "multiple_block_segments"][
        "segment_key"].drop_duplicates().tolist()
    single_track_segments = t21[t21["segment_type"] == "single_block_segment"]["segment_key"].drop_duplicates().tolist()
    station_segments = t21[t21["segment_type"] == "station"]["segment_key"].drop_duplicates().tolist()

    for seg_k in single_track_segments:
        curr_orig, curr_dest = seg_k.split("_")[0].split("-")
        relevant_timetable = t21[t21["segment_key"].isin(headway_functions.get_segment_conflicts(seg_k))]

        # Get all pairs of consecutive trains
        relevant_timetable = relevant_timetable.sort_values(["time_start_corrected"])
        relevant_timetable_merged = pd.concat([relevant_timetable,  relevant_timetable.shift(-1).add_prefix("next_")], axis=1)

        # Determine the minimum headway before and after the train to be inserted here
        min_headway_before = headway_functions.get_min_block_diff_at_single_track_before(train_to_insert, curr_orig, curr_dest)
        min_headway_after = headway_functions.get_min_block_diff_at_single_track_after(train_to_insert, curr_orig, curr_dest)

        # The previous train leaves the segment at time_end_corrected
        # It then cannot be used for min_headway_after of that train,
        # but also not for the min headway before the train to be added
        relevant_timetable_merged["free_space_start"] = relevant_timetable_merged["time_end_corrected"] + pd.to_timedelta(np.maximum(min_headway_before, relevant_timetable_merged['min_headway_after']), 's')
        relevant_timetable_merged["free_space_end"] = relevant_timetable_merged[
                                                            "next_time_start_corrected"] - pd.to_timedelta(
            np.maximum(min_headway_after, relevant_timetable_merged['next_min_headway_before']), 's')
        relevant_timetable_merged = relevant_timetable_merged[relevant_timetable_merged["free_space_start"] <= relevant_timetable_merged["free_space_end"]]

        # Obtain list of start- and end times of free spaces
        free_space_start = relevant_timetable_merged["free_space_start"].tolist()
        free_space_end = relevant_timetable_merged["free_space_end"].tolist()

        # A few corner cases need to be addressed
        # When no other trains are using the segment, one additional free space must be added
        # for the complete time window
        # Furthermore, any free space intersecting only one of the endpoints is also missed,
        # so these are included as well
        if len(free_space_start) == 0:
            free_space_dict[seg_k] = [(pd.to_datetime(TIME_FROM_DATETIME), pd.to_datetime(TIME_TO_DATETIME))]
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

            free_space_dict[seg_k] = list(zip(free_space_start, free_space_end))
        print(seg_k, free_space_dict[seg_k])

    # The largely analogous case of stations
    for seg_k in station_segments:
        station, track_id = seg_k.split("/")
        relevant_timetable = t21[t21["segment_key"].isin(headway_functions.get_segment_conflicts(seg_k))]

        # Again, get consecutive occupations
        relevant_timetable = relevant_timetable.sort_values(["time_start_corrected"])
        relevant_timetable_merged = pd.concat([relevant_timetable,  relevant_timetable.shift(-1).add_prefix("next_")], axis=1)

        # Headways wrt the train to be inserted
        min_headway_before = headway_functions.get_min_block_diff_at_station_before(train_to_insert, station, track_id)
        min_headway_after = headway_functions.get_min_block_diff_at_station_after(train_to_insert, station, track_id)

        # The previous train leaves the segment at time_end_corrected
        # It then cannot be used for min_headway_after of that train,
        # but also not for the min headway before the train to be added
        relevant_timetable_merged["free_space_start"] = relevant_timetable_merged["time_end_corrected"] + pd.to_timedelta(np.maximum(min_headway_before, relevant_timetable_merged['min_headway_after']), 's')
        relevant_timetable_merged["free_space_end"] = relevant_timetable_merged[
                                                            "next_time_start_corrected"] - pd.to_timedelta(
            np.maximum(min_headway_after, relevant_timetable_merged['next_min_headway_before']), 's')
        relevant_timetable_merged = relevant_timetable_merged[relevant_timetable_merged["free_space_start"] <= relevant_timetable_merged["free_space_end"]]

        free_space_start = relevant_timetable_merged["free_space_start"].tolist()
        free_space_end = relevant_timetable_merged["free_space_end"].tolist()

        if len(free_space_start) == 0:
            free_space_dict[seg_k] = [(pd.to_datetime(TIME_FROM_DATETIME), pd.to_datetime(TIME_TO_DATETIME))]
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

            free_space_dict[seg_k] = list(zip(free_space_start, free_space_end))
        # print(seg_k, free_space_dict[seg_k])

    # The double track case is a bit more tedious,
    # as the free spaces no longer are rectangles but trapezoids.
    for seg_k in double_track_segments:
        curr_orig, curr_dest = seg_k.split("_")[0].split("-")
        relevant_timetable = t21[t21["segment_key"] == seg_k]

        relevant_timetable = relevant_timetable.sort_values(["time_start_corrected"])
        relevant_timetable_merged = pd.concat([relevant_timetable,  relevant_timetable.shift(-1).add_prefix("next_")], axis=1)

        min_headway_before = headway_functions.get_headway_before(train_to_insert, curr_orig, curr_dest)
        min_headway_after = headway_functions.get_headway_after(train_to_insert, curr_orig, curr_dest)

        # The previous train leaves the segment at time_end_corrected
        # It then cannot be used for min_headway_after of that train,
        # but also not for the min headway before the train to be added

        relevant_timetable_merged["free_space_start_orig"] = relevant_timetable_merged["time_start_corrected"] + pd.to_timedelta(np.maximum(min_headway_before, relevant_timetable_merged['min_headway_after']), 's')
        relevant_timetable_merged["free_space_end_orig"] = relevant_timetable_merged[
                                                            "next_time_start_corrected"] - pd.to_timedelta(
            np.maximum(min_headway_after, relevant_timetable_merged['next_min_headway_before']), 's')

        relevant_timetable_merged["free_space_start_dest"] = relevant_timetable_merged[
                                                                 "time_end_corrected"] + pd.to_timedelta(
            np.maximum(min_headway_before, relevant_timetable_merged['min_headway_after']), 's')
        relevant_timetable_merged["free_space_end_dest"] = relevant_timetable_merged[
                                                               "next_time_end_corrected"] - pd.to_timedelta(
            np.maximum(min_headway_after, relevant_timetable_merged['next_min_headway_before']), 's')

        # print(relevant_timetable_merged["free_space_start_orig"].tolist())
        # for index, row in relevant_timetable_merged.iterrows():
        #     print(row["free_space_start_orig"], row["free_space_end_orig"], row["free_space_start_dest"], row['free_space_end_dest'])

        relevant_timetable_merged = relevant_timetable_merged[(relevant_timetable_merged["free_space_start_orig"] <= relevant_timetable_merged["free_space_end_orig"]) & (relevant_timetable_merged["free_space_start_dest"] <= relevant_timetable_merged["free_space_end_dest"])
        ]

        free_space_start_orig = relevant_timetable_merged["free_space_start_orig"].tolist()
        free_space_end_orig = relevant_timetable_merged["free_space_end_orig"].tolist()

        free_space_start_dest = relevant_timetable_merged["free_space_start_dest"].tolist()
        free_space_end_dest = relevant_timetable_merged["free_space_end_dest"].tolist()

        if len(free_space_start_orig) == 0:
            free_space_dict[seg_k] = [((pd.to_datetime(TIME_FROM_DATETIME), pd.to_datetime(TIME_TO_DATETIME)), (pd.to_datetime(TIME_FROM_DATETIME), pd.to_datetime(TIME_TO_DATETIME)))]
        else:
            first_blockage_start_orig = relevant_timetable_merged.iloc[0][
                                                                "time_start_corrected"] - pd.to_timedelta(
                np.maximum(min_headway_after, relevant_timetable_merged.iloc[0]['min_headway_before']), 's')
            first_blockage_start_dest = relevant_timetable_merged.iloc[0][
                                            "time_end_corrected"] - pd.to_timedelta(
                np.maximum(min_headway_after, relevant_timetable_merged.iloc[0]['min_headway_before']), 's')

            last_blockage_end_orig = relevant_timetable_merged.iloc[-1][
                                       "next_time_end_corrected"] + pd.to_timedelta(
                np.maximum(min_headway_after, relevant_timetable_merged.iloc[-1]['next_min_headway_after']), 's')
            last_blockage_end_dest = relevant_timetable_merged.iloc[-1][
                                    "next_time_end_corrected"] + pd.to_timedelta(
                np.maximum(min_headway_after, relevant_timetable_merged.iloc[-1]['next_min_headway_after']), 's')

            if first_blockage_start_orig > TIME_FROM_DATETIME and first_blockage_start_dest > TIME_FROM_DATETIME:
                free_space_start_orig = [pd.to_datetime(TIME_FROM_DATETIME)] + free_space_start_orig
                free_space_end_orig = [first_blockage_start_orig] + free_space_end_orig
                free_space_start_dest = [pd.to_datetime(TIME_FROM_DATETIME)] + free_space_start_dest
                free_space_end_dest = [first_blockage_start_dest] + free_space_end_dest

            if last_blockage_end_orig < TIME_TO_DATETIME and last_blockage_end_dest < TIME_TO_DATETIME:
                free_space_start_orig = free_space_start_orig + [last_blockage_end_orig]
                free_space_end_orig = free_space_end_orig + [pd.to_datetime(TIME_TO_DATETIME)]
                free_space_start_dest = free_space_start_dest + [last_blockage_end_dest]
                free_space_end_dest = free_space_end_dest + [pd.to_datetime(TIME_TO_DATETIME)]

            free_space_dict[seg_k] = list(zip(zip(free_space_start_orig, free_space_end_orig), zip(free_space_start_dest, free_space_end_dest)))
        # print(seg_k, free_space_dict[seg_k])

    t21["train_key"] = t21.apply(lambda x: x["date"] + "_" + str(x["train_ix"]), axis=1)
    t21_sorted = t21.sort_values(["train_key", "time_end"])
    t21_transitions = pd.concat([t21_sorted, t21_sorted.shift(-1).add_prefix("next_")], axis=1)
    t21_transitions = t21_transitions[t21_transitions["train_key"] == t21_transitions["next_train_key"]]

    t21_transitions["is_arriving"] = t21_transitions.apply(lambda row: pd.isnull(row["next_dest"]), axis=1)
    t21_transitions["station"] = t21_transitions.apply(lambda row: row["orig"] if pd.isnull(row["dest"]) else row["next_orig"], axis=1)
    t21_transitions["station_track_id"] = t21_transitions.apply(
        lambda row: row["track_id"] if pd.isnull(row["dest"]) else row["next_track_id"], axis=1)
    t21_transitions["towards_station"] = t21_transitions.apply(
        lambda row: row["next_dest"] if pd.isnull(row["dest"]) else row["orig"], axis=1)
    t21_transitions["towards_station_track_id"] = t21_transitions.apply(
        lambda row: row["next_track_id"] if pd.isnull(row["dest"]) else row["track_id"], axis=1)
    t21_transitions["transition_key"] = t21_transitions.apply(
        lambda row: str(row["station"]) + "=" + str(row["towards_station"]) + "+" + str(row["station_track_id"]) + "=" + str(row["towards_station_track_id"]), axis=1)
    t21_transitions["transition_min_headway_before"] = t21_transitions.apply(lambda row: headway_functions.get_min_block_diff_at_transition_before(row["train_id"], row["station"], row["towards_station"], row["station_track_id"], row["towards_station_track_id"], row["is_arriving"]), axis=1)
    t21_transitions["transition_min_headway_after"] = t21_transitions.apply(
        lambda row: headway_functions.get_min_block_diff_at_transition_after(row["train_id"], row["station"], row["towards_station"],
                                                            row["station_track_id"], row["towards_station_track_id"],
                                                            row["is_arriving"]), axis=1)

    t21_transitions["transition_timestamp"] = t21_transitions.apply(
        lambda row: row["time_end_corrected"] if pd.isnull(row["dest"]) else row["next_time_end_corrected"], axis=1
    )

    transition_segments = t21_transitions["transition_key"].drop_duplicates().tolist()

    for seg_k in transition_segments:
        for is_arriving in [True, False]:
            seg_k_expanded = seg_k + "&" + str(is_arriving)
            print(seg_k_expanded)
            stations, tracks = seg_k.split("+")
            main_station, towards_station = stations.split("=")
            main_track, towards_track = tracks.split("=")

            relevant_timetable = t21_transitions[t21_transitions["transition_key"].isin(headway_functions.get_segment_conflicts(seg_k))]

            # Again, get consecutive occupations
            relevant_timetable = relevant_timetable.sort_values(["transition_timestamp"])
            relevant_timetable_merged = pd.concat([relevant_timetable, relevant_timetable.shift(-1).add_prefix("next_")],
                                                  axis=1)

            # for index, row in relevant_timetable_merged.iterrows():
            #     print(row["transition_min_headway_before"], row["next_transition_min_headway_before"], row["is_arriving"]),
            #
            # tm.sleep(5)

            # Headways wrt the train to be inserted
            # Notice that this depends on whether the train departs or arrives here,
            # which is why we keep track of two free space lists
            min_headway_before = headway_functions.get_min_block_diff_at_transition_before(train_to_insert, main_station, towards_station, main_track, towards_track, is_arriving)
            min_headway_after = headway_functions.get_min_block_diff_at_transition_after(train_to_insert, main_station, towards_station, main_track, towards_track, is_arriving)

            # The previous train leaves the segment at time_end_corrected
            # It then cannot be used for min_headway_after of that train,
            # but also not for the min headway before the train to be added
            relevant_timetable_merged["free_space_start"] = relevant_timetable_merged[
                                                                "transition_timestamp"] + pd.to_timedelta(
                np.maximum(min_headway_before, relevant_timetable_merged['transition_min_headway_after']), 's')

            # for index, row in relevant_timetable_merged.iterrows():
            #     print(np.maximum(min_headway_after, row['next_min_headway_before']))
            #     print("hm?")

            relevant_timetable_merged["free_space_end"] = relevant_timetable_merged[
                                                              "next_transition_timestamp"] - pd.to_timedelta(
                np.maximum(min_headway_after, relevant_timetable_merged['next_transition_min_headway_before']), 's')

            relevant_timetable_merged = relevant_timetable_merged[
                relevant_timetable_merged["free_space_start"] <= relevant_timetable_merged["free_space_end"]]

            free_space_start = relevant_timetable_merged["free_space_start"].tolist()
            free_space_end = relevant_timetable_merged["free_space_end"].tolist()

            if len(free_space_start) == 0:
                free_space_dict[seg_k_expanded] = [(pd.to_datetime(TIME_FROM_DATETIME), pd.to_datetime(TIME_TO_DATETIME))]
            else:
                first_blockage_start = relevant_timetable_merged.iloc[0][
                                           "transition_timestamp"] - pd.to_timedelta(
                    np.maximum(min_headway_after, relevant_timetable_merged.iloc[0]['transition_min_headway_before']), 's')
                last_blockage_end = relevant_timetable_merged.iloc[-1][
                                        "next_transition_timestamp"] + pd.to_timedelta(
                    np.maximum(min_headway_after, relevant_timetable_merged.iloc[-1]['next_transition_min_headway_after']), 's')

                if first_blockage_start > TIME_FROM_DATETIME:
                    free_space_start = [pd.to_datetime(TIME_FROM_DATETIME)] + free_space_start
                    free_space_end = [first_blockage_start] + free_space_end

                if last_blockage_end < TIME_TO_DATETIME:
                    free_space_start = free_space_start + [last_blockage_end]
                    free_space_end = free_space_end + [pd.to_datetime(TIME_TO_DATETIME)]

                free_space_dict[seg_k_expanded] = list(zip(free_space_start, free_space_end))
    return free_space_dict