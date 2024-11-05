from src.path_insertion import generate_candidate_paths


def single_train_insertion(config, infra, overall_train_route, t21, running_times, free_space_dict_stations, free_space_dict_segments, free_space_dict_transitions):
    generate_candidate_paths(infra, config["train_id"], config["speed_profile"], running_times, t21, config["time_from"], config["time_to"], overall_train_route, "", config["filter_close_paths"], free_space_dict_stations, free_space_dict_segments, free_space_dict_transitions, log_file="../out/log.csv", req_dep=0, req_arr=0, add_to_t21=False, config=config)


def greedy_train_insertion():
    return 0