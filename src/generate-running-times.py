import pandas as pd

if __name__ == "__main__":
    train_routes = [["M", "Mgb", "MGB1", "Al", "Ali", "Lma", "Fl", "Sie", "Fud", "Kg", "Tp", "Sal", "Kd", "Bih", "Åp", "Ä", "Baa", "Vip", "För", "Bån", "Laov", "Ea", "Kst", "Hdr", "Hd", "Fur", "Btp", "Bp", "He", "Fab", "Teo", "Tye", "Haa", "Vb", "Vrö", "Få", "Åsa", "Lek", "Kb", "Khe", "Lgd", "Ag", "Ldo", "Krd", "Mdn", "Am", "Lis", "Gro", "G", "Or", "Or1", "Gsv", "Säv", "Sel", "P", "Jv", "J", "Apn", "Asd", "Lr", "Sn", "Fd", "Ndv", "Ns", "Vbd", "Bgs", "A", "Agg", "Vgå", "Hr", "Kä", "Fby", "F", "Fn", "Ss", "Rmtp", "Sk", "Vä", "Mh", "T", "Sle", "Äl", "Gdö", "Fa", "Lå", "Lln", "Vt", "Öj", "Täl", "Hrbg", "Hpbg", "På", "Km", "Hgö", "Vr", "Bt", "K", "Spn", "Sde", "Fle", "Skv", "Sp", "Nsj", "Sh", "B", "Koe", "Gn", "Mö", "Jn", "Söö", "Msj", "Bjn", "Flb", "Hu", "Sta", "Äs", "Åbe", "Sst", "Cst"], ["Al", "Lma"], ["Sie", "Kg"]]

    all_profiles = {"GR401610", "GB201210", "GB201610", "GB201710", "GB201810", "GB202010", "GB221610", "GB401809", "GB402308", "GB930511", "GB931510", "GEG02310", "GR400910", "GR401410", "GR401509", "GR401510", "GR401610", "GR422210", "GR4E2608", "PB930516", "PR600616", "PR6A0414", "PX2-2000"}

    t21 = pd.read_csv("../data/t21.csv")
    t21_relevant_route = t21[((t21["orig"] == "Hm") & (t21["dest"] == "Bl")) | ((t21["orig"] == "Bl") & (t21["dest"] == "Hm"))]

    running_dates = pd.read_csv("../data/t21_running_days.csv")
    relevant_train_ixs = running_dates[running_dates["date"].isin(["2021-03-14"])]["train_ix"].tolist()
    print(relevant_train_ixs)

    completely_filtered_train_ixs = t21_relevant_route[t21_relevant_route["train_ix"].isin(relevant_train_ixs)]["train_ix"]

    t21[t21["train_ix"].isin(completely_filtered_train_ixs)].to_csv("../data/to_be_rerouted_idk.csv")

    distance_matrix = pd.read_csv("../data/t21_station_distance.csv")

    existing_running_times = pd.read_csv("../data/t21_technical_running_times.csv")

    with open("../data/generated_running_times.csv", "w", encoding="utf-8") as f:
        f.write("train_type,stn_id_from,stn_id_to,rt_forw_pp,rt_forw_ps,rt_forw_sp,rt_forw_ss,rt_back_pp,rt_back_ps,rt_back_sp,rt_back_ss\n")

    for train_route in train_routes:
        adjacent_pairs = [(train_route[i], train_route[i+1]) for i in range(len(train_route) - 1)]
        for pair in adjacent_pairs:
            if (pair[0] == "Al" and pair[1] == "Lma") or (pair[0] == "Lma" and pair[1] == "Al"):
                dist = 1070 + 3628
            elif (pair[0] == "Sie" and pair[1] == "Kg") or (pair[0] == "Kg" and pair[1] == "Sie"):
                dist = 3509 + 2527
            else:
                relevant_rows = distance_matrix[((distance_matrix["stn_id_from"] == pair[0]) & (distance_matrix["stn_id_to"] == pair[1])) | ((distance_matrix["stn_id_from"] == pair[1]) & (distance_matrix["stn_id_to"] == pair[0]))]

                if relevant_rows.shape[0] != 1:
                    for index, row in relevant_rows.iterrows():
                        print(pair, row["distance"])
                    raise Exception(pair)

                dist = int(relevant_rows["distance"].iloc[0])

            if dist <= 3704:
                ref0 = "Nöe"
                ref1 = "Nol"
                refdist = 3009
            elif dist <= 5060:
                ref0 = "Rås"
                ref1 = "Skbl"
                refdist = 4400
            elif dist <= 6865:
                ref0 = "Nol"
                ref1 = "Än"
                refdist = 5720
            elif dist <= 8413:
                ref0 = "Veas"
                ref1 = "Thn"
                refdist = 8010
            elif dist <= 9349:
                ref0 = "Thn"
                ref1 = "Öx"
                refdist = 8817
            elif dist <= 11008:
                ref0 = "Vpm"
                ref1 = "Veas"
                refdist = 9882
            elif dist <= 15062:
                ref0 = "Ed"
                ref1 = "Mon"
                refdist = 12135
            else:
                ref0 = "Drt"
                ref1 = "Bäf"
                refdist = 17989

            for profile in all_profiles:
                rel_rows = existing_running_times[(existing_running_times["train_type"] == profile) & (existing_running_times["stn_id_from"] == ref0) & (existing_running_times["stn_id_to"] == ref1)]

                if rel_rows.shape[0] != 1:
                    raise Exception(profile, ref0, ref1)

                row = rel_rows.iloc[0]

                f_pp = round(int(row["rt_forw_pp"]) * dist / refdist)
                f_ps = round(int(row["rt_forw_ps"]) * dist / refdist)
                f_sp = round(int(row["rt_forw_sp"]) * dist / refdist)
                f_ss = round(int(row["rt_forw_ss"]) * dist / refdist)
                b_pp = round(int(row["rt_back_pp"]) * dist / refdist)
                b_ps = round(int(row["rt_back_ps"]) * dist / refdist)
                b_sp = round(int(row["rt_back_sp"]) * dist / refdist)
                b_ss = round(int(row["rt_back_ss"]) * dist / refdist)

                with open("../data/generated_running_times.csv", "a", encoding="utf-8") as f:
                    f.write(
                        f"{profile},{pair[0]},{pair[1]},{f_pp},{f_ps},{f_sp},{f_ss},{b_pp},{b_ps},{b_sp},{b_ss},{b_pp}\n")


            # Now multiply the running times on ref0-ref1 by dist/refdist
            print(pair, dist)
