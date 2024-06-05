import os
from datetime import datetime

class Drgl:
    # Contains all drgl properties such as train type, number, operator, route and starting date.
    # And most importantly, a list of doorkomsten
    # When parsing doorkomsten, we set installt to True when data is missing (i.e. train is cancelled)
    def __init__(self, zuggattung, trnr, ru, route, start_date):
        self.zuggattung = zuggattung
        self.trnr = trnr
        self.ru = ru
        self.route = route
        self.doorkomsten = []
        self.start_date = start_date

        # A train is typically also cancelled when the trnr is not numeric, i.e. LTPxxxx or xxxx*01
        if trnr.isnumeric():
            self.installt = False
        else:
            self.installt = True

    # Add doorkomst to list of doorkomsten and detect missing information (i.e. train is cancelled)
    def add_doorkomst(self, doorkomst):
        self.doorkomsten += [doorkomst]
        if doorkomst.dep == "" or doorkomst.arr == "":
            self.installt = True

class Doorkomst:

    # Simple class containing information on each (trafikplats, arr-time, dep-time) triple
    def __init__(self, trafikplats, arr, dep, day):
        self.trafikplats = trafikplats
        self.arr = arr
        self.dep = dep
        self.depday = day


class Timetable:
    # Just a dict
    def __init__(self):
        self.table = {}

    # Verify whether a drgl was already generated
    def contains_trnr(self, trnr, day):
        return (trnr, day) in self.table.keys()

    # Create new drgl in timetable
    def add_drgl(self, drgl, day):
        if self.contains_trnr(drgl.trnr, day):
            raise Exception("Drgl already included in timetable")
        self.table[(drgl.trnr, day)] = drgl

    # Extend drgl of some train with additional doorkomst
    def add_doorkomst(self, trnr, day, Doorkomst):
        current_drgl = self.table[(trnr, day)]
        current_drgl.add_doorkomst(Doorkomst)
        self.table[(trnr, day)] = current_drgl

    # Merge two timetables, e.g. of different days
    def merge_timetable(self, other):
        self.table = self.table | other.table

def create_timetable(directory, day):
    # Create a new timetable based on doorkomststaten in directory/day
    timetable = Timetable()
    day_dir = os.path.join(directory, day)

    # Get all trafikplats doorkomststaten
    for filename in os.listdir(day_dir):
        current_time = ""
        f = os.path.join(day_dir, filename)
        trafikplats, ext = filename.split(".")

        with open(f, "r", encoding="utf-8") as railitoutput:
            # Verify when we passed the header
            passed_header = False

            for line in railitoutput:
                # Keep track of current day, i.e. when 00:00:00 passes as railit doesnt...
                current_day = day

                # Remove railit noise
                line = line.replace("\n", "").replace("SupportIconm\t", "").replace("SupportIcon", "")

                # Last and one-but-last line of header
                # Skip all lines until Båda riktningarna and the (next) line with Tåg
                # åbyg does not have any doorkomsten on one day, hence the check for empty lines
                if "Båda riktningarna" in line:
                    passed_header = True
                    continue
                elif not passed_header:
                    continue
                elif "Tåg" in line:
                    continue
                elif line == "":
                    continue

                zuggattung, trnr, arr, dash, dep, ru, route = line.split("\t")

                trnr_not_instlt_map = {"LTP19917": "230", "LTP19914": "226", "LTP19930": "248"}
                main_drgl_map = {"70465": "14127", "4941": "3941", "21301": "20301", "10002": "2", "70204": "36409",
                                 "70217": "36408", "70214": "36443", "70215": "36418", "59812": "59808",
                                 "35641": "35640", "35643": "35642", "35467": "35466", "35463": "35462",
                                 "36423": "36422", "36421": "36420", "63321": "63320", "81100": "42701"}
                if trafikplats == "Nk" and trnr in trnr_not_instlt_map:
                    trnr = trnr_not_instlt_map[trnr]
                elif trnr in main_drgl_map:
                    trnr = main_drgl_map[trnr]

                # Save reference for time step and update, to make sure we (most likely) notice a decreasing time stamp
                if current_time == "":
                    current_time = dep
                elif dep != "" and datetime.strptime(dep, "%H:%M:%S") < datetime.strptime(current_time, "%H:%M:%S"):
                    # Very hacky day increment
                    current_day = str(int(day) + 1)
                else:
                    current_time = dep

                # Add doorkomst to timetable
                if timetable.contains_trnr(trnr, day):
                    timetable.add_doorkomst(trnr, day, Doorkomst(trafikplats, arr, dep, current_day))
                else:
                    timetable.add_drgl(Drgl(zuggattung, trnr, ru, route, day), day)
                    timetable.add_doorkomst(trnr, day, Doorkomst(trafikplats, arr, dep, current_day))
    return timetable

def construct_complete_timetable():
    directory = "C:\\Users\\davde78\\Documents\\sos-project\\data\\"
    day19 = "20230919"
    day20 = "20230920"

    timetable = create_timetable(directory, day19)
    timetable_20 = create_timetable(directory, day20)

    timetable.merge_timetable(timetable_20)

    # Sort each drgl by day and time
    # If cancelled, remove from timetable
    for trnr, day in list(timetable.table.keys()):
        drgl = timetable.table[(trnr, day)]
        if not drgl.installt:
            drgl.doorkomsten.sort(key=lambda x: (x.depday, datetime.strptime(x.dep, "%H:%M:%S")))
        else:
            del timetable.table[(trnr, day)]

    return timetable


if __name__ == "__main__":
    timetable = construct_complete_timetable()
    count = 0

    for trnr, day in timetable.table.keys():
        drgl = timetable.table[(trnr, day)]


        logical_boundaries = ["Åbyg", "Oxd", "Jn", "Gn", "Nr", "Lp", "Mlö", "Bt", "Tn", "Vsd", "Nk", "K"]

        start = drgl.doorkomsten[0].trafikplats
        end = drgl.doorkomsten[-1].trafikplats

        if start not in logical_boundaries or end not in logical_boundaries:
            # if trnr in main_drgl_map or trnr in main_drgl_map.values():
            #     continue

            print("\n", trnr, day, drgl.installt)
            print(start, end)

            count += 1
            print(count)
            for doorkomst in drgl.doorkomsten:
                print(doorkomst.trafikplats, doorkomst.arr, doorkomst.dep, doorkomst.depday)



