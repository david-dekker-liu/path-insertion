import time


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


# Print the time difference spent on this subject (if print_runtime) and return current time
def print_runtime(title, start_time, config):
    log_file = config["log_file"]

    if config["print_runtime"]:
        print(f"{title}: {time.time() - start_time}")

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{title};{time.time() - start_time}\n")

    return time.time()
