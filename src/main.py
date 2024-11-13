import time

import pandas as pd

from src.infrastructure import Infrastructure
from src.config_parser import read_config, get_train_routes, generate_requested_times
from src.timetable_creation import get_timetable, remove_linjeplatser, detect_track_allocation_problems, get_running_times
from src.path_algorithms import single_train_insertion, path_selection
from src.free_space_detection import get_free_spaces_stations, get_free_spaces_segments, get_free_spaces_transitions
from src.general_utils import print_runtime


def single_train_workflow(config, infra, overall_train_route, t21, running_times, free_space_dict_stations, free_space_dict_segments, free_space_dict_transitions):
    single_train_insertion(config, infra, overall_train_route, t21, running_times, free_space_dict_stations, free_space_dict_segments, free_space_dict_transitions)


def path_selection_workflow(config, infra, train_route_dict, overall_train_route, t21, running_times, free_space_dict_stations, free_space_dict_segments, free_space_dict_transitions):
    path_selection(config, infra, train_route_dict, overall_train_route, t21, running_times, free_space_dict_stations, free_space_dict_segments, free_space_dict_transitions)


def greedy_workflow(config, infra, overall_train_route, t21, running_times, free_space_dict_stations, free_space_dict_segments, free_space_dict_transitions, rerouted_trains):
    return 0


def main():
    # Assumes config file at location ../config/config_[project].txt
    # project = "motional"
    project = "RailDresden"

    # Get main config, infra, train routes
    time_start = time.time()
    config = read_config(f"../config/config_{project}.txt")
    infra = Infrastructure(config["infra_file"], config["conflicts_file"])

    all_linjeplatser = []
    print(infra.linjeplatser)
    for linjeplats in infra.linjeplatser:
        all_linjeplatser += infra.linjeplatser[linjeplats][1:-1]
    print(all_linjeplatser)

    train_route_dict = get_train_routes(config["train_route_file"])

    print(train_route_dict)
    for key in train_route_dict:
        train_route_dict[key] = [v for v in train_route_dict[key] if v not in all_linjeplatser]
    print(train_route_dict)

    overall_train_route = train_route_dict[config["overall_train_route"]]
    log_file = config["log_file"]

    with open(log_file, "w+", encoding="utf-8") as f:
        f.write("title;time\n")

    current_time = print_runtime("Config initialization", time_start, config)

    # Process the complete timetable (filter for relevant day and route, and ensure the runthrough dates are appropriately mapped to proper datetimes)
    if config["process_full_timetable"]:
        t21 = get_timetable(config["time_from"], config["time_to"], overall_train_route)

        current_time = print_runtime("Preprocessing timetable", current_time, config)

        t21 = remove_linjeplatser(t21, infra.linjeplatser)

        current_time = print_runtime("Removing linjeplatser", current_time, config)

        t21.to_csv("../data/filtered_t21.csv", sep=";")

        current_time = print_runtime("Exporting timetable", current_time, config)

    # noinspection PyTypeChecker
    t21 = pd.read_csv("../data/filtered_t21.csv", sep=";", parse_dates=['time_start_corrected', 'time_end_corrected'], date_format={'time_start_corrected': '%Y-%m-%d %H:%M:%S', 'time_end_corrected': '%Y-%m-%d %H:%M:%S'})

    current_time = print_runtime("Importing timetable", current_time, config)

    if config["print_track_problems"]:
        detect_track_allocation_problems(t21, overall_train_route, "../out/log.txt")
        current_time = print_runtime("Printing track problems", current_time, config)

    # Determine all speed profiles that may be relevant (i.e., those corresponding to trains to reroute, or corresponding to a general train to insert)
    affected_trains_profiles = pd.read_csv(config["affected_trains_file"], sep=";", encoding="utf-8")["profile"].drop_duplicates().tolist()
    if config["speed_profile"] not in affected_trains_profiles:
        affected_trains_profiles += [config["speed_profile"]]

    running_times = get_running_times(config["running_times_file"], infra.linjeplatser, affected_trains_profiles)

    current_time = print_runtime("Read running times", current_time, config)

    segments = [(overall_train_route[i], overall_train_route[i + 1]) for i in range(len(overall_train_route) - 1)]

    current_time = print_runtime("Get segment list", current_time, config)

    free_space_dict_stations = get_free_spaces_stations(t21, config["train_id"], config["time_from"], config["time_to"], infra.stations)

    current_time = print_runtime("Get station free spaces", current_time, config)

    # This one needs both segments and complex segments, hence the entire infra object
    free_space_dict_segments = get_free_spaces_segments(t21, config["train_id"], config["time_from"], config["time_to"], infra.segments, infra)

    current_time = print_runtime("Get segment free spaces", current_time, config)

    free_space_dict_transitions = get_free_spaces_transitions(t21, config["train_id"], config["time_from"], config["time_to"], infra.transitions)

    current_time = print_runtime("Get transition free spaces", current_time, config)

    if config["generate_requested_times"]:
        generate_requested_times(config["affected_trains_file"], config["affected_trains_with_requests_file"], config["time_windows_request_generation"], infra, config, running_times, t21, train_route_dict, free_space_dict_stations, free_space_dict_segments, free_space_dict_transitions)

    # single_train_workflow(config, infra, overall_train_route, t21, running_times, free_space_dict_stations, free_space_dict_segments, free_space_dict_transitions)

    path_selection_workflow(config, infra, train_route_dict, overall_train_route, t21, running_times, free_space_dict_stations, free_space_dict_segments, free_space_dict_transitions)


if __name__ == "__main__":
    main()
