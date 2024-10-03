import pandas as pd
import datetime
import time

to_name_dict = {
    "Gsv": "Göteborg Sävenäs",
    "Gbm": "Göteborg Marieholm",
    "Bhs": "Bohus",
    "Alh": "Alvhem",
    "Veas": "Velanda södra",
    "Öx": "Öxnered",
    "Fdf": "Frändefors",
    "Brl": "Brålanda",
    "Rås": "Råskogen",
    "Bäf": "Bäckefors",
    "Ed": "Ed",
    "Ko": "Kornsjö gränsen"}

to_dist_dict = {
    "Gsv": 0,
    "Or1": 1,
    "Or": 2,
    "Gbm": 5,
    "Agb": 9,
    "Sue": 14,
    "Bhs": 19,
    "Nöe": 22,
    "Nol": 25,
    "Än": 31,
    "Alh": 38,
    "Les": 39,
    "Tbn": 47,
    "Vpm": 55,
    "Veas": 65,
    "Thn": 73,
    "Öx": 82,
    "Bjh": 90,
    "Fdf": 97,
    "Brl": 106,
    "Skbl": 112,
    "Rås": 116,
    "Drt": 124,
    "Bäf": 142,
    "Ed": 160,
    "Mon": 173,
    "Ko": 180}

# def get_y():

if __name__ == "__main__":
    dark_mode = False

    output_file = "../out/timetable.svg"
    df = pd.read_csv("../data/filtered_t21.csv", sep=";")
    df = df[(df["orig"].isin(to_dist_dict.keys())) & (df["dest"].isin(to_dist_dict.keys())) & df["track_id"].isin(["U", "E", "A"])]

    # df = df.sort_values(['train_id', 'time_start'], ascending=[True, True])

    y_scale = 3.3333
    y_offset = 50
    y_offset_below = 10

    x_scale = 0.05333
    x_offset = 350
    x_offset_right = 10

    max_y = y_offset + to_dist_dict["Ko"] * y_scale + y_offset
    max_x = x_offset + 7 * 3600 * x_scale + x_offset

    # print(max_x, max_y)

    last_trnr = 0
    last_x = 0
    path_commands = []
    current_path_command = ""

    for index, row in df.iterrows():
        trnr = row["train_id"]
        # print(trnr, row["train_ix"])
        start_str = row["time_start"]
        end_str = row["time_end"]
        if int(start_str.split(":")[0]) >= 24 or int(end_str.split(":")[0]) >= 24:
            continue
        # if trnr == 6504:
        #     print(row["orig"], row["dest"], start_str, end_str)

        x = time.strptime(start_str, "%H:%M:%S")
        start_seconds = datetime.timedelta(hours=x.tm_hour, minutes=x.tm_min, seconds=x.tm_sec).total_seconds() - 25200
        x = time.strptime(end_str, "%H:%M:%S")
        end_seconds = datetime.timedelta(hours=x.tm_hour, minutes=x.tm_min, seconds=x.tm_sec).total_seconds() - 25200

        x1 = round(start_seconds * x_scale + x_offset, 2)
        x2 = round(end_seconds * x_scale + x_offset, 2)

        y1 = round(to_dist_dict[row["orig"]] * y_scale + y_offset, 2)
        y2 = round(to_dist_dict[row["dest"]] * y_scale + y_offset, 2)

        if last_trnr == trnr:
            if last_x == x1:
                current_path_command += f" L {x2} {y2}"
            else:
                current_path_command += f" L {x1} {y1} L {x2} {y2}"
            last_x = x2
        else:
            if last_trnr != 0 and dark_mode:
                path_commands += [current_path_command + "' style='fill:none;stroke:white;stroke-width:1'/>"]
            elif last_trnr != 0:
                path_commands += [current_path_command + "' style='fill:none;stroke:black;stroke-width:1'/>"]
            current_path_command = f"<path d='M {x1} {y1} L {x2} {y2}"
            last_x = x2
            last_trnr = trnr

    if dark_mode:
        path_commands += [current_path_command + "' style='fill:none;stroke:white;stroke-width:1'/>"]
    else:
        path_commands += [current_path_command + "' style='fill:none;stroke:black;stroke-width:1'/>"]

    # df = pd.read_csv("../out/temp_obtained_paths.csv", sep=";")
    df = pd.read_csv("../out/candidate_paths.csv", sep=";")
    df = df[(df["orig"].isin(to_dist_dict.keys())) & (df["dest"].isin(to_dist_dict.keys())) ]
    df = df.sort_values(by=["train_ix", "time_start"])

    last_trnr = 0
    last_x = 0
    current_path_command = ""

    for index, row in df.iterrows():
        trnr = row["train_ix"]
        start_str = row["time_start"]
        end_str = row["time_end"]
        print(trnr, start_str, end_str, row["orig"], row["dest"])

        if int(start_str.split(":")[0]) >= 24 or int(end_str.split(":")[0]) >= 24:
            continue
        # print(start_str, end_str)
        x = time.strptime(start_str, "%H:%M:%S")
        start_seconds = datetime.timedelta(hours=x.tm_hour, minutes=x.tm_min, seconds=x.tm_sec).total_seconds() - 25200
        x = time.strptime(end_str, "%H:%M:%S")
        end_seconds = datetime.timedelta(hours=x.tm_hour, minutes=x.tm_min, seconds=x.tm_sec).total_seconds() - 25200

        x1 = round(start_seconds * x_scale + x_offset, 2)
        x2 = round(end_seconds * x_scale + x_offset, 2)

        y1 = round(to_dist_dict[row["orig"]] * y_scale + y_offset, 2)
        y2 = round(to_dist_dict[row["dest"]] * y_scale + y_offset, 2)

        if last_trnr == trnr:
            if last_x == x1:
                current_path_command += f" L {x2} {y2}"
            else:
                current_path_command += f" L {x1} {y1} L {x2} {y2}"
            last_x = x2
        else:
            if last_trnr != 0 and dark_mode:
                path_commands += [current_path_command + "' style='fill:none;stroke:#3282F6;stroke-width:2'/>"]
            elif last_trnr != 0:
                path_commands += [current_path_command + "' style='fill:none;stroke:blue;stroke-width:2'/>"]
            current_path_command = f"<path d='M {x1} {y1} L {x2} {y2}"
            last_x = x2
            last_trnr = trnr

    if dark_mode:
        path_commands += [current_path_command + "' style='fill:none;stroke:#3282F6;stroke-width:2'/>"]
    else:
        path_commands += [current_path_command + "' style='fill:none;stroke:blue;stroke-width:2'/>"]

    with open(output_file, "w+", encoding="utf-8") as f:
        f.write("<svg height='700' width='1743' xmlns='http://www.w3.org/2000/svg'>\n")
        if dark_mode:
            f.write("<rect width='100%' height='100%' fill='#0A1335'/>\n")
        else:
            f.write("<rect width='100%' height='100%' fill='#FFFFFF'/>\n")

        for i in ["Gbm", "Bhs", "Alh", "Öx", "Fdf", "Brl", "Rås", "Bäf", "Ed"]:
            xs = round(x_offset,2)
            xe = round(x_offset + 7 * 3600 * x_scale,2)
            y = round(y_offset + y_scale * to_dist_dict[i],2)
            f.write(f"<path d='M {xs} {y} L {xe} {y}' style='fill:none;stroke:#666666;stroke-width:1'/>\n")

        for i in range(6):
            x = round(x_offset + x_scale * ( 3600 + i * 3600), 2)
            ys = round(y_offset, 2)
            ye = round(y_offset + y_scale * to_dist_dict["Ko"], 2)
            f.write(f"<path d='M {x} {ys} L {x} {ye}' style='fill:none;stroke:#666666;stroke-width:1'/>\n")

        for path in path_commands:
            f.write(path + "\n")

        xmax = round(x_offset + 7 * 3600 * x_scale,2)
        ymax = round(y_offset + y_scale * to_dist_dict["Ko"], 2)

        if dark_mode:
            f.write(f"<rect width='{x_offset}' height='{ymax}' x='0' y='0' fill='#0A1335'/>\n")
            f.write(f"<rect width='{x_offset}' height='{ymax}' x='{xmax}' y='0' fill='#0A1335'/>\n")
        else:
            f.write(f"<rect width='{x_offset}' height='{ymax}' x='0' y='0' fill='#FFFFFF'/>\n")
            f.write(f"<rect width='{x_offset}' height='{ymax}' x='{xmax}' y='0' fill='#FFFFFF'/>\n")

        for i in ["Gsv", "Gbm", "Bhs", "Alh", "Öx", "Fdf", "Brl", "Rås", "Bäf", "Ed", "Ko"]:
            bonus_y = 0
            if i == "Gsv":
                bonus_y = 6
            if i == "Gbm":
                bonus_y = 15
            if i == "Ko":
                bonus_y = -5
            if dark_mode:
                f.write(f"<text font-size='2.1em' text-anchor='end' x='{x_offset-12}' y='{round(bonus_y + y_offset + 4 + y_scale * to_dist_dict[i],2)}' fill='white'>{to_name_dict[i]}</text>\n")
            else:
                f.write(
                    f"<text font-size='2.1em' text-anchor='end' x='{x_offset - 12}' y='{round(bonus_y + y_offset + 4 + y_scale * to_dist_dict[i], 2)}' fill='black'>{to_name_dict[i]}</text>\n")

        for i in range(8):
            if i < 3:
                hour = "0" + str(i+7)
            else:
                hour = str(i+7)
            x = round(x_offset + x_scale * (i * 3600), 2)
            y = round(y_offset + y_scale * to_dist_dict["Ko"], 2) + 35
            if dark_mode:
                f.write(f"<text font-size='2.1em' text-anchor='middle' x='{x}' y='{y}' fill='white'>{hour}:00</text>\n")
            else:
                f.write(f"<text font-size='2.1em' text-anchor='middle' x='{x}' y='{y}' fill='black'>{hour}:00</text>\n")

        if dark_mode:
            f.write(f"<path d='M {x_offset} {y_offset} L {x_offset} {ymax} L {xmax} {ymax} L {xmax} {y_offset} L {x_offset} {y_offset}' style='fill:none;stroke:white;stroke-width:1'/>\n")
        else:
            f.write(f"<path d='M {x_offset} {y_offset} L {x_offset} {ymax} L {xmax} {ymax} L {xmax} {y_offset} L {x_offset} {y_offset}' style='fill:none;stroke:black;stroke-width:1'/>\n")

        f.write("</svg>\n")
    # print(df)