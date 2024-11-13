import os
import time
import pandas as pd
from gurobipy import *
from datetime import timedelta, datetime
from src.path_insertion import generate_candidate_paths
from src.general_utils import obj, print_runtime


def single_train_insertion(config, infra, overall_train_route, t21, running_times, free_space_dict_stations, free_space_dict_segments, free_space_dict_transitions):
    if os.path.exists(config["path_output_file"]):
        os.remove(config["path_output_file"])

    generate_candidate_paths(infra, config["train_id"], config["speed_profile"], running_times, t21, config["time_from"], config["time_to"], overall_train_route, config["path_output_file"], config["filter_close_paths"], free_space_dict_stations, free_space_dict_segments, free_space_dict_transitions, config["log_file"], req_dep=0, req_arr=0, add_to_t21=False, config=config)


def conflict(d1, d2):
    for key in d1.keys():
        if key not in d2.keys():
            continue

        # print(key)

        range1 = d1[key]
        range2 = d2[key]

        # print(range1, range2)

        if len(key) == 3 and key[2] == "E" and conflict_vb(range1, range2):
            return True
        elif len(key) == 3 and conflict_segment(range1, range2):
            return True
        elif len(key) == 2 and conflict_station(range1, range2):
            return True

    return False


def conflict_segment(r1, r2):
    s1, e1 = r1
    s2, e2 = r2

    if s1 == e1:
        raise Exception("Start and end time at segment equal", s1, e1)

    if s2 == e2:
        raise Exception("Start and end time at segment equal", s2, e2)

    if -180 <= (s2 - s1).total_seconds() <= 180:
        # print("rit1", r1, "rit2", r2)
        # print("segment conflict at start times")
        return True
    if -180 <= (e2 - e1).total_seconds() <= 180:
        # print("rit1", r1, "rit2", r2)
        # print("segment conflict at end times")
        return True
    if s1 < s2 < e2 < e1:
        # print("rit1", r1, "rit2", r2)
        # print("illegal overtaking, rit2 is faster")
        return True
    if s2 < s1 < e1 < e2:
        # print("rit1", r1, "rit2", r2)
        # print("illegal overtaking, rit1 is faster")
        return True

    return False


def conflict_station(r1, r2):
    s1, e1 = r1
    s2, e2 = r2

    if -180 <= (s2 - e1).total_seconds() <= 180:
        return True
    if -180 <= (e2 - s1).total_seconds() <= 180:
        return True
    if s1 < s2 < e1:
        return True
    if s2 < s1 < e2:
        return True

    return False


def conflict_vb(r1, r2):
    s1, e1 = r1
    s2, e2 = r2

    if -60 <= (s2 - e1).total_seconds() <= 60:
        return True
    if -60 <= (s1 - e2).total_seconds() <= 60:
        return True
    if s1 < s2 < e1:
        return True
    if s2 < s1 < e2:
        return True

    return False


def conflict_detection(trnr_to_df_of_candidates_dict, config):
    # Input is a dictionary from trnr to a dataframe with all candidate paths
    # Create a new dict from train_ix (i.e., candidate path id) to a dictionary containing the path

    candidate_trainix_to_path_dict = {}
    current_time = time.time()

    for trnr in trnr_to_df_of_candidates_dict:
        paths = trnr_to_df_of_candidates_dict[trnr]
        train_ix_list = paths["train_ix"].drop_duplicates().tolist()

        for train_ix in train_ix_list:
            path = paths[paths["train_ix"] == train_ix]
            new_dict = {}
            for index, row in path.iterrows():
                if pd.isna(row["time_start"]):
                    row["time_start"] = row["time_end"]
                if pd.isna(row["time_end"]):
                    row["time_end"] = row["time_start"]

                # print(row["orig"], row["dest"])

                if row["dest"] == "":
                    # print("no destination")
                    new_dict[(row["orig"], row["track_id"])] = (row["time_start"],row["time_end"])
                else:
                    new_dict[(row["orig"], row["dest"], row["track_id"])] = (row["time_start"], row["time_end"])
                    # print("key", (row["orig"], row["dest"], row["track_id"]), pd.isnull(row["dest"]), pd.isna(row["dest"]))
                    if (row["orig"] == "Vb" and row["dest"] == "Haa") or (row["orig"] == "Haa" and row["dest"] == "Vb"):
                        new_dict[(row["dest"], row["orig"], row["track_id"])] = (row["time_start"], row["time_end"])
            candidate_trainix_to_path_dict[train_ix] = new_dict

    current_time = print_runtime("Dictionary setup for conflicts", current_time, config)

    obtained_conflict_list = []

    for trnr1 in trnr_to_df_of_candidates_dict:
        for trnr2 in trnr_to_df_of_candidates_dict:
            if trnr1 >= trnr2:
                continue

            train_ix_list1 = trnr_to_df_of_candidates_dict[trnr1]["train_ix"].drop_duplicates().tolist()
            train_ix_list2 = trnr_to_df_of_candidates_dict[trnr2]["train_ix"].drop_duplicates().tolist()

            for train_ix1 in train_ix_list1:
                for train_ix2 in train_ix_list2:
                    path1 = candidate_trainix_to_path_dict[train_ix1]
                    path2 = candidate_trainix_to_path_dict[train_ix2]
                    # print(path1, path2)

                    if conflict(path1, path2):
                        obtained_conflict_list.append(
                            (train_ix1, train_ix2)
                        )

    current_time = print_runtime("Determining conflicts among candidates", current_time, config)

    return obtained_conflict_list


def path_selection(config, infra, train_route_dict, overall_train_route, t21, running_times, free_space_dict_stations, free_space_dict_segments, free_space_dict_transitions):
    if os.path.exists(config["path_output_file"]):
        os.remove(config["path_output_file"])

    if os.path.exists(config["candidate_paths_file"]):
        os.remove(config["candidate_paths_file"])

    affected_trains = pd.read_csv(config["affected_trains_with_requests_file"], sep=";", encoding="utf-8")
    priorities = affected_trains["priority"].drop_duplicates().sort_values(ascending=False).tolist()

    if not config["partition_on_priority"]:
        priorities = [1]

    for priority in priorities:
        all_current_paths = {}
        all_train_ix = []
        train_ix_per_trnr = {}
        requested_times = {}

        if config["partition_on_priority"]:
            current_trains = affected_trains[affected_trains["priority"] == priority]
        else:
            current_trains = affected_trains

        current_trains.sort_values(by=["dep"])
        all_trnrs = current_trains["trnr"].tolist()

        for index, train in current_trains.iterrows():
            requested_departure = datetime.strptime(train["dep"], "%Y-%m-%d %H:%M:%S")
            requested_arrival = datetime.strptime(train["arr"], "%Y-%m-%d %H:%M:%S")

            time_from = requested_departure - timedelta(minutes=210)
            time_to = requested_arrival + timedelta(minutes=210)

            print(time_from, time_to)
            route = train_route_dict[train["route"]]
            profile = train["profile"]
            print(route)

            all_current_paths[train["trnr"]] = generate_candidate_paths(infra, train["trnr"], profile, running_times, t21, time_from, time_to, route, config["candidate_paths_file"], config["filter_close_paths"], free_space_dict_stations, free_space_dict_segments, free_space_dict_transitions, config["log_file"], req_dep=requested_departure, req_arr=requested_arrival, add_to_t21=False, config=config, only_fastest=False)

            train_ix_per_trnr[train["trnr"]] = all_current_paths[train["trnr"]]["train_ix"].drop_duplicates().tolist()
            requested_times[train["trnr"]] = (requested_departure, requested_arrival)

            all_train_ix += all_current_paths[train["trnr"]]["train_ix"].drop_duplicates().tolist()

        # Get a list of all tuples of train_ix ids that cannot both be added,
        # i.e., induce a conflict
        conflicts = conflict_detection(all_current_paths, config)
        print(len(conflicts), conflicts)

        # Add cancellation paths
        all_train_ix += [str(trnr) + "cancellation" for trnr in all_current_paths]
        for trnr in train_ix_per_trnr:
            train_ix_per_trnr[trnr] = train_ix_per_trnr[trnr] + [str(trnr) + "cancellation"]

        # Set up independent set problem
        cost = {}

        for trnr in all_trnrs:
            for train_ix in train_ix_per_trnr[trnr]:
                if "cancellation" in train_ix:
                    cost[train_ix] = 5.5
                else:
                    all_paths = all_current_paths[trnr]
                    path = all_paths[all_paths["train_ix"] == train_ix]
                    start_times = path["time_start"].tolist()
                    cost[train_ix] = obj(min(start_times),max(start_times), requested_times[trnr][0], requested_times[trnr][1])

        # print("alltrainix", all_train_ix)
        # print("alltrnrs", all_trnrs)
        # for i in all_trnrs:
        #     print("trainix_per_trnr", train_ix_per_trnr[i])

        m = Model()
        m.setParam('TimeLimit', 2 * 60)
        y = m.addVars(all_train_ix, vtype=GRB.BINARY, name='usePath')
        m.update()

        no_conflicting_trains = m.addConstrs((y[i] + y[j] <= 1 for i, j in conflicts), name="no_conflicting_trains")
        one_path_per_train = m.addConstrs((quicksum(y[j] for j in train_ix_per_trnr[i]) == 1 for i in all_trnrs), name='one_path_per_train')

        m.setObjective(quicksum(cost[i] * y[i] for i in all_train_ix), GRB.MINIMIZE)
        m.update()
        nrconstraints = len(m.getConstrs())
        print(nrconstraints)

        m.optimize()
        m.update()

        runningtime = m.Runtime
        integralitygap = m.MIPGap
        objval = m.objVal

        for trnr in all_trnrs:
            for p in train_ix_per_trnr[trnr]:
                if y[p].X == 1:
                    print("selected", p, cost[p])


def greedy_train_insertion():
    return 0
