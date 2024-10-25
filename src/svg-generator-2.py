import pandas as pd
import time
from src.infrastructure import Infrastructure, Station, Segment
from datetime import datetime
from datetime import timedelta
# def get_y():

if __name__ == "__main__":
    dark_mode = True
    train_route = ["Ä", "Baa", "Vip", "För", "Bån", "Laov", "Ea", "Kst", "Hdr", "Hd", "Fur", "Btp", "Bp", "He", "Fab", "Teo", "Tye", "Haa", "Vb", "Vrö", "Få", "Åsa", "Lek", "Kb", "Khe", "Lgd", "Ag", "Ldo", "Krd", "Mdn", "Am", "Lis", "Gro", "G", "Or", "Or1", "Gsv", "Säv", "Sel", "P", "Jv", "J", "Apn", "Asd", "Lr", "Sn", "Fd", "Ndv", "Ns", "Vbd", "Bgs", "A", "Agg", "Vgå", "Hr", "Kä", "Fby", "F", "Fn", "Ss", "Rmtp", "Sk", "Vä", "Mh", "T", "Sle", "Äl", "Gdö", "Fa", "Lå", "Lln", "Vt", "Öj", "Täl", "Hrbg", "Hpbg", "På", "Km", "Hgö", "Vr", "Bt", "K", "Spn", "Sde", "Fle", "Skv", "Sp", "Nsj", "Sh", "B", "Koe", "Gn", "Mö", "Jn", "Söö", "Msj", "Bjn", "Flb", "Hu", "Sta", "Äs", "Åbe", "Sst", "Cst"]
    # train_route = ["G", "Or", "Or1", "Gsv", "Säv", "Sel", "P", "Jv", "J", "Apn", "Asd", "Lr", "Sn", "Fd", "Ndv", "Ns", "Vbd", "Bgs", "A", "Agg", "Vgå", "Hr", "Kä", "Fby", "F", "Fn", "Ss", "Rmtp", "Sk", "Vä", "Mh", "T", "Sle", "Äl", "Gdö", "Fa", "Lå", "Lln", "Vt", "Öj", "Täl", "Hrbg", "Hpbg", "På", "Km", "Hgö", "Vr", "Bt", "K", "Spn", "Sde", "Fle", "Skv", "Sp", "Nsj", "Sh", "B", "Koe", "Gn", "Mö", "Jn", "Söö", "Msj", "Bjn", "Flb", "Hu", "Sta", "Äs", "Åbe", "Sst", "Cst"]

    train_route = list(reversed(train_route))
    adj_pairs = [(train_route[i], train_route[i+1]) for i in range(len(train_route) - 1)]

    locations_to_label = ["F", "Sk", "Hrbg", "K", "A", "Hr", "Söö", "Gdö"]
    TIME_FROM = "2021-03-14 00:00"
    TIME_TO = "2021-03-15 06:00"
    TIME_FROM_DATETIME = datetime.strptime(TIME_FROM, "%Y-%m-%d %H:%M")
    TIME_TO_DATETIME = datetime.strptime(TIME_TO, "%Y-%m-%d %H:%M")
    time_window = (TIME_TO_DATETIME - TIME_FROM_DATETIME).total_seconds()

    infra = Infrastructure("../config/infrastructure-details-RailDresden.txt", "../config/conflict_margins.txt")

    last_loc = ""
    to_dist_dict = {}
    to_name_dict = {}

    for loc in train_route:
        if loc == train_route[0]:
            to_dist_dict[loc] = 0
        else:
            to_dist_dict[loc] = to_dist_dict[last_loc] + infra.segments[(last_loc, loc)].length

        last_loc = loc

    output_file = "../out/timetable.svg"
    df = pd.read_csv("../data/filtered_t21.csv", sep=";")
    # df = df[(df["orig"].isin(to_dist_dict.keys())) & (df["dest"].isin(to_dist_dict.keys())) & df["track_id"].isin(["U", "E", "A", "U1", "U1S", "N2S", "1"])]
    df = df[(df["orig"].isin(to_dist_dict.keys())) & (df["dest"].isin(to_dist_dict.keys())) & df["track_id"].isin(["N", "E", "A", "N1", "N1S", "4"])]

    df = df.sort_values(['train_id', 'time_start_corrected'], ascending=[True, True])

    y_scale = 3.3333
    y_offset = 50
    y_offset_below = 10

    x_scale = 0.05333
    x_offset = 350
    x_offset_right = 10

    max_y = y_offset + to_dist_dict[train_route[-1]] * y_scale + y_offset
    max_x = x_offset + time_window * x_scale + x_offset

    # print(max_x, max_y)

    last_trnr = 0
    last_x = 0
    last_dest = 0
    path_commands = []
    current_path_command = ""

    for index, row in df.iterrows():
        trnr = row["train_ix"]

        start_datetime = datetime.strptime(row["time_start_corrected"], '%Y-%m-%d %H:%M:%S')
        end_datetime = datetime.strptime(row["time_end_corrected"], '%Y-%m-%d %H:%M:%S')

        if end_datetime < TIME_FROM_DATETIME or start_datetime > TIME_TO_DATETIME:
            continue
        elif TIME_FROM_DATETIME <= start_datetime:
            start_seconds = (start_datetime - TIME_FROM_DATETIME).total_seconds()
            end_seconds = (end_datetime - TIME_FROM_DATETIME).total_seconds()
        else:
            start_seconds = -(TIME_FROM_DATETIME - start_datetime).total_seconds()
            end_seconds = (end_datetime - TIME_FROM_DATETIME).total_seconds()

        x1 = round(start_seconds * x_scale + x_offset, 2)
        x2 = round(end_seconds * x_scale + x_offset, 2)

        y1 = round(to_dist_dict[row["orig"]] * y_scale + y_offset, 2)
        y2 = round(to_dist_dict[row["dest"]] * y_scale + y_offset, 2)

        # print(last_dest, row["orig"])
        if last_trnr == trnr and last_dest == row["orig"] and -150 <= x1 - x2 <= 150:
            if last_x == x1:
                current_path_command += f" L {x2} {y2}"
            else:
                current_path_command += f" L {x1} {y1} L {x2} {y2}"
            last_x = x2
            last_dest = row["dest"]
        else:
            if last_trnr != 0 and dark_mode:
                path_commands += [current_path_command + "' style='fill:none;stroke:white;stroke-width:1'/>"]
            elif last_trnr != 0:
                path_commands += [current_path_command + "' style='fill:none;stroke:black;stroke-width:2.5'/>"]
            current_path_command = f"<path d='M {x1} {y1} L {x2} {y2}"
            last_x = x2
            last_dest = row["dest"]
            last_trnr = trnr

    if dark_mode:
        path_commands += [current_path_command + "' style='fill:none;stroke:white;stroke-width:1'/>"]
    else:
        path_commands += [current_path_command + "' style='fill:none;stroke:black;stroke-width:2.5'/>"]

    # df = pd.read_csv("../out/temp_obtained_paths.csv", sep=";")
    df = pd.read_csv("../out/candidate_paths.csv", sep=";")
    df = df[(df["orig"].isin(to_dist_dict.keys())) & (df["dest"].isin(to_dist_dict.keys()))]
    df = df.sort_values(by=["train_ix", "time_start"])

    last_trnr = 0
    last_x = 0
    current_path_command = ""

    for index, row in df.iterrows():
        trnr = row["train_ix"]

        start_datetime = datetime.strptime(row["time_start"], '%Y-%m-%d %H:%M:%S')
        end_datetime = datetime.strptime(row["time_end"], '%Y-%m-%d %H:%M:%S')

        start_seconds = (start_datetime - TIME_FROM_DATETIME).total_seconds()
        end_seconds = (end_datetime - TIME_FROM_DATETIME).total_seconds()

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
                path_commands += [current_path_command + "' style='fill:none;stroke:blue;stroke-width:4'/>"]
            current_path_command = f"<path d='M {x1} {y1} L {x2} {y2}"
            last_x = x2
            last_trnr = trnr

    if dark_mode:
        path_commands += [current_path_command + "' style='fill:none;stroke:#3282F6;stroke-width:2'/>"]
    else:
        path_commands += [current_path_command + "' style='fill:none;stroke:blue;stroke-width:4'/>"]

    with open(output_file, "w+", encoding="utf-8") as f:
        f.write("<svg height='7000' width='17403' xmlns='http://www.w3.org/2000/svg'>\n")
        if dark_mode:
            f.write("<rect width='100%' height='100%' fill='#0A1335'/>\n")
        else:
            f.write("<rect width='100%' height='100%' fill='#CDDEFF'/>\n")

        hours = int(divmod(time_window, 3600)[0])

        for i in locations_to_label:
            xs = round(x_offset,2)
            xe = round(x_offset + hours * 3600 * x_scale,2)
            y = round(y_offset + y_scale * to_dist_dict[i],2)
            f.write(f"<path d='M {xs} {y} L {xe} {y}' style='fill:none;stroke:#666666;stroke-width:1'/>\n")

        for i in range(hours-1):
            x = round(x_offset + x_scale * ( 3600 + i * 3600), 2)
            ys = round(y_offset, 2)
            ye = round(y_offset + y_scale * to_dist_dict[train_route[-1]], 2)
            f.write(f"<path d='M {x} {ys} L {x} {ye}' style='fill:none;stroke:#666666;stroke-width:1'/>\n")

        for path in path_commands:
            f.write(path + "\n")

        xmax = round(x_offset + hours * 3600 * x_scale,2)
        ymax = round(y_offset + y_scale * to_dist_dict[train_route[-1]], 2)

        if dark_mode:
            f.write(f"<rect width='{x_offset}' height='{ymax}' x='0' y='0' fill='#0A1335'/>\n")
            f.write(f"<rect width='{x_offset}' height='{ymax}' x='{xmax}' y='0' fill='#0A1335'/>\n")
        else:
            f.write(f"<rect width='{x_offset}' height='{ymax}' x='0' y='0' fill='#CDDEFF'/>\n")
            f.write(f"<rect width='{x_offset}' height='{ymax}' x='{xmax}' y='0' fill='#CDDEFF'/>\n")

        for i in locations_to_label:
            bonus_y = 0
            # if i == "Gsv":
            #     bonus_y = 6
            # if i == "Gbm":
            #     bonus_y = 15
            # if i == "Ko":
            #     bonus_y = -5

            if dark_mode:
                f.write(f"<text font-size='2.1em' text-anchor='end' x='{x_offset-12}' y='{round(bonus_y + y_offset + 4 + y_scale * to_dist_dict[i],2)}' fill='white'>{i}</text>\n")
            else:
                f.write(
                    f"<text font-size='2.1em' text-anchor='end' x='{x_offset - 12}' y='{round(bonus_y + y_offset + 4 + y_scale * to_dist_dict[i], 2)}' fill='black'>{i}</text>\n")

        for i in range(8):
            if i < 3:
                hour = "0" + str(i+7)
            else:
                hour = str(i+7)
            x = round(x_offset + x_scale * (i * 3600), 2)
            y = round(y_offset + y_scale * to_dist_dict[train_route[-1]], 2) + 35
            if dark_mode:
                f.write(f"<text font-size='2.1em' text-anchor='middle' x='{x}' y='{y}' fill='white'>{hour}:00</text>\n")
            else:
                f.write(f"<text font-size='2.1em' text-anchor='middle' font-weight='bold' x='{x}' y='{y}' fill='black'>{hour}:00</text>\n")

        if dark_mode:
            f.write(f"<path d='M {x_offset} {y_offset} L {x_offset} {ymax} L {xmax} {ymax} L {xmax} {y_offset} L {x_offset} {y_offset}' style='fill:none;stroke:white;stroke-width:1'/>\n")
        else:
            f.write(f"<path d='M {x_offset} {y_offset} L {x_offset} {ymax} L {xmax} {ymax} L {xmax} {y_offset} L {x_offset} {y_offset}' style='fill:none;stroke:black;stroke-width:2'/>\n")

        f.write("</svg>\n")
    # print(df)