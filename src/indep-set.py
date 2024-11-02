import pandas as pd
from gurobipy import *
from random import *
from datetime import datetime, timedelta


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

def solve_indepset():
    train_dict = {("GB201210", "AFle"): [44100, 44150], ("GB201210", "AHrbg"): [44980], ("GB201610", "ACst"): [41406],
                  ("GB201610", "AG"): [46250], ("GB201610", "HrbgA"): [44723, 44725], ("GB201710", "AK"): [44906],
                  ("GB201710", "KA"): [44905], ("GB201810", "AAs"): [49340], ("GB202010", "AHrbg"): [44990],
                  ("GB221610", "HrbgA"): [44721], ("GB221610", "CstA"): [41755], ("GB401809", "AHrbg"): [40970, 40972],
                  ("GB402308", "HrbgA"): [40971, 40973], ("GB931510", "AHrbg"): [44420],
                  ("GEG02310", "AHrbg"): [44728, 44734, 44736], ("GR401410", "AHrbg"): [44200],
                  ("GR401410", "ACst"): [9400], ("GR401410", "FA"): [4903], ("GR401509", "AHrbg"): [5166],
                  ("GR401509", "AF"): [5134], ("GR401510", "ACst"): [4140],
                  ("GR401610", "AHrbg"): [4300, 4168, 4190, 4194], ("GR401610", "AAs"): [4240],
                  ("GR401610", "HrbgA"): [5711, 4191, 5611, 5617], ("GR422210", "HrbgA"): [4325],
                  ("GR4E2608", "HrbgA"): [45513], ("PB930516", "HrbgA"): [3911], ("PB930516", "CstA"): [3943],
                  ("PR600616", "CstA"): [9847], ("PR6A0414", "CstA"): [1, 345], ("PR6A0414", "ACst"): [2],
                  ("PX2-2000", "CstA"): [507, 511, 545], ("PX2-2000", "ACst"): [502, 504, 548]}

    req_times = pd.read_csv("../data/requested_departure_arrival.csv", sep=";", encoding="utf-8")

    trnrs = []

    forbidden = [1, 3911, 502, 507, 511, 504, 345, 3943, 548, 545, 2]
    good = [44990, 44725, 4190, 40970, 4903, 40973, 44734, 4194, 41755]
    # allowed_trnrs = [1, 3911, 502, 507, 511, 504, 345, 3943, 548, 545, 2, 9847]
    # trnrs = [44990, 44725, 4190, 40970, 4903, 40973, 44734, 4194, 41755, 44736, 5617, 5166, 5134, 45513, 4300, 5611, 40972, 4191, 40971, 4168, 46250, 5711, 49340, 44150, 9847, 44200, 9400, 41406, 4240, 44721, 44905, 44420, 44723, 44728, 44100, 4140, 4325, 44980, 44906]
    all_candidates = []

    candidates_of_trnr = {}
    cost = {}
    conflicts = []

    conflicts_df = pd.read_csv("../data/only_conflicts_freight.csv", sep=";", encoding="utf-8")
    for index, row in conflicts_df.iterrows():
        # if row["id1"] in allowed_trnrs and row["id2"] in allowed_trnrs:
        if row["id1"] in good and row["id2"] in good:
            conflicts += [(row["id1"], row["id2"])]

    for profile, route in train_dict.keys():
        for trnr in train_dict[(profile, route)]:
            # if trnr in forbidden:
            if trnr not in good:
                continue

            for index, row in req_times.iterrows():
                if row["trnr"] != trnr:
                    continue
                reqarr = datetime.strptime(row["arr"], "%Y-%m-%d %H:%M:%S")
                reqdep = datetime.strptime(row["dep"], "%Y-%m-%d %H:%M:%S")
                break
            # print(trnr, reqarr, reqdep)
            trnrs += [trnr]
            df = pd.read_csv(f'../data/candidate paths indep set only freight/candidate_paths_only_freight_{trnr}.csv', sep=";", encoding="utf-8")
            # df = pd.read_csv(f'../data/candidate paths indep set/candidate_paths_{trnr}.csv', sep=";", encoding="utf-8")
            trnr_candidates = df["train_ix"].drop_duplicates().tolist() + [trnr]
            candidates_of_trnr[trnr] = trnr_candidates
            all_candidates += trnr_candidates

            for candidate in trnr_candidates:
                if candidate == trnr:
                    cost[candidate] = 5.5
                    continue
                this_df = df[df["train_ix"] == candidate]
                start_times = this_df["time_start"].tolist()

                cost[candidate] = obj(datetime.strptime(min(start_times), "%Y-%m-%d %H:%M:%S"), datetime.strptime(max(start_times), "%Y-%m-%d %H:%M:%S"), reqdep, reqarr)

    # n_trains = 45 # Number of trains to reroute
    # n_paths = 45 # Number of paths per train to consider
    # paths =
    # allpaths = [*range(n_paths + 1)]
    # p = 0.15 # Probability of two paths conflicting each other
    max_cost = 100

    # cost = [[random() * max_cost for j in range(n_paths + 1)] for i in range(n_trains)]
    # for i in range(n_trains):
    #     cost[i][n_paths] = max_cost * n_trains

    m = Model()
    m.setParam('TimeLimit', 2 * 60)
    y = m.addVars(all_candidates, vtype=GRB.BINARY, name='usePath')
    m.update()

    no_conflicting_trains = m.addConstrs((y[i] + y[j] <= 1 for i, j in conflicts), name="no_conflicting_trains")
    one_path_per_train = m.addConstrs((quicksum(y[j] for j in candidates_of_trnr[i]) == 1 for i in trnrs), name='one_path_per_train' )

    m.setObjective(quicksum(cost[i] * y[i] for i in all_candidates), GRB.MINIMIZE)
    m.update()
    nrconstraints = len(m.getConstrs())
    print(nrconstraints)

    m.optimize()
    m.update()

    runningtime = m.Runtime
    integralitygap = m.MIPGap
    objval = m.objVal

    with open("../out/indep-set-results-small-problem.csv", "w+", encoding="utf-8") as f:
        f.write("trnr;id;cost\n")

    for p in all_candidates:
        curr_trnr = 0

        for trnr in trnrs:
            if p in candidates_of_trnr[trnr]:
                curr_trnr = trnr

        if y[p].X == 1:
            with open("../out/indep-set-results-small-problem.csv", "a", encoding="utf-8") as f:
                f.write(f"{curr_trnr};{p};{cost[p]}\n")


    return [runningtime, integralitygap, objval, nrconstraints]


if __name__ == '__main__':
    solve_indepset()
    repeat = 15
    thresh = 2
    #prob = 0.2

    if not os.path.exists("out/results_constant_npaths.csv"):
        with open("out/results_constant_npaths.csv", 'w') as creating_new_csv_file:
            pass
    if not os.path.exists("out/mainresults_constant_npaths.csv"):
        with open("out/mainresults_constant_npaths.csv", 'w') as creating_new_csv_file:
            pass

    #ntrains = 40
    npaths = 20

    for p in [0.6]:
        for ntrains in range(33, 40):
            timeout_count = 0
            for k in range(repeat):
                if ntrains == 33 and k <= 5:
                    continue
                runningtime, integralitygap, objval, nrconstraints = solve_indepset(ntrains, npaths, p)
                with open("out/results_constant_npaths.csv", 'a') as the_file:
                    the_file.write(
                        #f"{prob};{ntrains};{npaths};{k+5};{nrconstraints};{runningtime};{integralitygap};{objval}\n")
                        f"{p};{ntrains};{npaths};{k};{nrconstraints};{runningtime};{integralitygap};{objval}\n")
                if runningtime > 120:
                    timeout_count += 1

            with open("out/mainresults_constant_npaths.csv", 'a') as the_file:
                the_file.write(f"{p};{ntrains};{npaths};{timeout_count}\n")


    """
    if not os.path.exists("out/results.csv"):
        with open("out/results.csv", 'w') as creating_new_csv_file:
            pass
    if not os.path.exists("out/mainresults.csv"):
        with open("out/mainresults.csv", 'w') as creating_new_csv_file:
            pass

    for ntrains in range(20, 61):
        for npaths in range(20, 61):
            timeout_count = 0
            for k in range(repeat):
                runningtime, integralitygap, objval, nrconstraints = solve_indepset(ntrains, npaths, 0.2)
                with open("out/results.csv", 'a') as the_file:
                    the_file.write(f"{prob};{ntrains};{npaths};{k};{nrconstraints};{runningtime};{integralitygap};{objval}\n")
                if runningtime > 120:
                    timeout_count += 1

            with open("out/mainresults.csv", 'a') as the_file:
                the_file.write(f"{prob};{ntrains};{npaths};{timeout_count}\n")"""
