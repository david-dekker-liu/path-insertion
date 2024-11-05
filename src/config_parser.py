from datetime import datetime, timedelta
import pandas as pd
from src.path_algorithms import generate_candidate_paths


def read_config(config_file):
    config = {}

    with open(config_file, "r", encoding="utf-8") as f:
        for line in f.readlines():
            # Skip comments and empty lines
            line = line.strip()
            if line == "" or line[0] == "#":
                continue

            # Each line has the structure "[key]: [value]"
            # Split at most once (e.g. file names may contain colons)
            # Booleans are converted to booleans rather than strings
            # Dates/times are converted to datetime object
            key, value = line.split(": ", 1)
            if key in ["time_from", "time_to"] and value.count(":") == 1:
                config[key] = datetime.strptime(value, "%Y-%m-%d %H:%M")
            elif key in ["time_from", "time_to"] and value.count(":") == 2:
                config[key] = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            elif value.upper() not in ["TRUE", "FALSE"]:
                config[key] = value
            else:
                config[key] = (value.upper() == "TRUE")

    return config


def get_train_routes(train_route_file):
    train_routes = {}

    with open(train_route_file, "r", encoding="utf-8") as f:
        for line in f.readlines():
            # Skip comments and empty lines
            line = line.strip()
            if line == "" or line[0] == "#":
                continue

            # Each route has the structure:
            # "[orig]-[dest]: [orig], [value1], [value2], [...], [dest]"
            key, values = line.split(": ")
            train_routes[key] = values.split(", ")

        # We do not require to specify the reversed routes as well, so if they do not exist, we add those as well
        for key in list(train_routes):
            orig, dest = key.split("-")
            reversed_key = dest + "-" + orig

            if reversed_key not in train_routes:
                train_routes[reversed_key] = list(reversed(train_routes[key]))

    return train_routes


def generate_requested_times(affected_trains_file, affected_trains_file_with_requests, time_windows_request_generation, infra, config, running_times, t21, train_route_dict, free_space_dict_stations, free_space_dict_segments, free_space_dict_transitions):
    affected_trains = pd.read_csv(affected_trains_file, sep=";", encoding="utf-8")
    output = affected_trains_file_with_requests
    time_windows = pd.read_csv(time_windows_request_generation, sep=";", encoding="utf-8")

    first_date = datetime(1970, 1, 1)

    with open(output, "w+", encoding="utf-8") as f:
        f.write(f"trnr;profile;route;dep;arr\n")

    for index, row in affected_trains.iterrows():
        route = row["route"]
        # if route[0] != "Ä":
        #     continue

        orig, dest = route.split("-")

        time_orig = row["orig_dep"]
        time_dest = row["orig_arr"]
        diff_orig = row["date_diff_dep"]
        diff_dest = row["date_diff_arr"]

        trnr = int(row["train_id"])
        profile = row["profile"]
        time_period = row["time_period"]
        time_window = time_windows[time_windows["id"] == time_period].iloc[0]
        time_from = datetime.strptime(time_window["time_from"], "%Y-%m-%d %H:%M:%S")
        time_to = datetime.strptime(time_window["time_to"], "%Y-%m-%d %H:%M:%S")

        # Get fastest possible path in time window [time_from, time_to]
        path = generate_candidate_paths(infra, trnr, profile, running_times, t21, time_from, time_to, train_route_dict[route], "", False, free_space_dict_stations, free_space_dict_segments, free_space_dict_transitions, "", 0, 0, False, config, True)

        first_record = path.iloc[0]
        last_record = path.iloc[-1]

        # for index, row in path.iterrows():
        #     print(row["orig"], row["dest"], row["time_start"], row["time_end"])

        if first_record["train_ix"] != last_record["train_ix"]:
            raise Exception("Multiple train ixs were returned.")

        arrival = first_record["time_start"]
        departure = last_record["time_end"]
        runtime = (arrival - departure).total_seconds()
        print(arrival, departure, runtime, runtime/3600)

        # Split original dep/end times in hours + minutes (+ seconds if included)
        orig_split = time_orig.split(":")
        if len(orig_split) == 2:
            orig_h, orig_m = orig_split
            orig_s = 0
        else:
            orig_h, orig_m, orig_s = orig_split

        dest_split = time_dest.split(":")
        if len(dest_split) == 2:
            dest_h, dest_m = dest_split
            dest_s = 0
        else:
            dest_h, dest_m, dest_s = orig_split

        orig_datetime = datetime(2021, 3, 14, int(orig_h) % 24, int(orig_m), int(orig_s))
        dest_datetime = datetime(2021, 3, 14, int(dest_h) % 24, int(dest_m), int(dest_s))

        if int(orig_h) >= 24:
            orig_datetime += timedelta(days=1)
        if int(dest_h) >= 24:
            dest_datetime += timedelta(days=1)
        if diff_orig == -1:
            orig_datetime -= timedelta(days=1)
        if diff_dest == -1:
            dest_datetime -= timedelta(days=1)

        orig_stamp = int((orig_datetime - first_date).total_seconds())
        dest_stamp = int((dest_datetime - first_date).total_seconds())

        avg = int((orig_stamp + dest_stamp) / 2)
        avg_datetime = first_date + timedelta(seconds=avg)

        new_orig = first_date + timedelta(seconds=int(avg - runtime/2))
        new_dest = first_date + timedelta(seconds=int(avg + runtime/2))
        with open(output, "a", encoding="utf-8") as f:
            f.write(f"{trnr};{profile};{route};{new_orig};{new_dest}\n")
        print(trnr, orig_datetime, dest_datetime, avg_datetime, new_orig, new_dest)
