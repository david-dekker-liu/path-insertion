class Infrastructure:
    def __init__(self, infra_config, headway_config):
        # The infrastructure object contains a bunch of dictionaries
        # * headway_dict: mapping from transition-type key to min number of seconds (int) between two transitions
        # * stations: mapping from trafikplats shorthand to a tuple (again shorthand, full name, tracks)
        # * segments: mapping from a tuple of adjacent trafikplatser to the pair of trafikplatser, the distance between them and the segment tracks
        # * linjeplatser: mapping from linjeplats shorthand to the main segment containing this (and possibly other) linjeplatser
        # * complex_segments: a list of tuples. First tuple contains a list of all trafikplatser that should be merged together, then a tuple with the present block separations between first and last trafikplats (floats), then the largest fraction of the distance between block separations (float)
        # * transitions: a dict giving a list of all transitions conflicting a given one. These lists contain tuples with a transition-quadruple (from, from_track, to, to_track), the nr of seconds that should be blocked before this transition-quadruple (not the key), and after (both as ints).
        # * N_stations: neighborhood at stations. Dict from (from, to, station_track) to all segment tracks in between
        # * N_segments: neighborhood at segments. Dict from (from, to, segment_track) to all station tracks at to

        self.headway_dict = {}
        self.stations = {}
        self.segments = {}
        self.linjeplatser = {}
        self.complex_segments = {}
        self.transitions = {}
        self.N_stations = {}
        self.N_segments = {}


        with open(headway_config, encoding="utf-8") as file:
            for line in file:
                key, value = line.strip().split(":")
                self.headway_dict[key] = int(value)

        print(self.headway_dict)
        with open(infra_config, encoding="utf-8") as file:
            line = file.readline().strip()

            # Create dictionary of stations
            while line != "":
                afk, full, track_str = line.split(";")
                self.stations[afk] = Station(afk, full, [str(track) for track in track_str.split(" ")])
                line = file.readline().strip()

            print(self.stations)
            line = file.readline().strip()

            # Create dictionary of segments
            last_station = ""
            last_segment_tracks = ""
            km_start = ""

            while line != "":
                if line == "&":
                    last_station = ""
                    last_segment_tracks = ""
                elif last_station == "":
                    last_station, km_start = line.split(";")
                elif last_segment_tracks == "":
                    last_segment_tracks = line.split(" ")
                else:
                    next_station, km_end = line.split(";")
                    self.segments[(last_station, next_station)] = Segment({last_station, next_station}, abs(float(km_end) - float(km_start)), last_segment_tracks)
                    self.segments[(next_station, last_station)] = Segment({last_station, next_station}, abs(float(km_end) - float(km_start)), last_segment_tracks)
                    last_station = next_station
                    last_segment_tracks = ""
                    km_start = km_end
                line = file.readline().strip()
            print(self.segments)
            line = file.readline().strip()

            while line != "":
                linjeplats, segment_str = line.split(";")
                segments = segment_str.split(",")
                self.linjeplatser[linjeplats] = segments
                line = file.readline().strip()

            print(self.linjeplatser)
            line = file.readline().strip()

            # Parse complex segments
            while line != "":
                segments, rel_block_separation = line.split(";")
                km_marks = [float(km) for km in rel_block_separation.split("-")]
                length = abs(km_marks[-1] - km_marks[0])
                # print(abs(km_marks[i+1]) - abs(km_marks[i])/length)
                largest_block_frac = max((abs(km_marks[i+1] - km_marks[i]))/length for i in range(len(km_marks) - 1))
                orig, dest = segments.split(",")
                self.complex_segments[(orig, dest)] = (km_marks, largest_block_frac)
                self.complex_segments[(dest, orig)] = (km_marks, largest_block_frac)
                line = file.readline().strip()

            print(self.complex_segments)
            line = file.readline().strip()

            # Parse transitions
            # Each transition key maps to all conflicting transition keys,
            # together with the margin before and after that image transition  wrt the key
            # (note: one of the margins is always 0)

            # The first step is to replace the shorthands (e.g. parallel and non-parallel) by actual transition descriptions, these end up in the raw transitions
            generated_raw_transition_conflicts = []

            # Then all shorthands for multiple tracks (including *) are extended
            generated_transition_conflicts = []

            # First, extending the parallel and non-parallel shorthands
            while line != "":
                trafikplats, delay_code, movement1, movement2 = line.split(";")
                if delay_code == "parallel":
                    generated_raw_transition_conflicts += [f"{trafikplats};block-diff;{movement1},*,{trafikplats},*;{trafikplats},*,{movement1},*"]
                    generated_raw_transition_conflicts += [f"{trafikplats};block-diff;{movement2},*,{trafikplats},*;{trafikplats},*,{movement2},*"]
                elif delay_code == "non-parallel":
                    generated_raw_transition_conflicts += [f"{trafikplats};block-diff;{movement1},*,{trafikplats},*;{trafikplats},*,{movement1},*"]
                    generated_raw_transition_conflicts += [f"{trafikplats};block-diff;{movement2},*,{trafikplats},*;{trafikplats},*,{movement2},*"]
                    generated_raw_transition_conflicts += [f"{trafikplats};non-parallel-diff;{movement1},*,{trafikplats},*;{movement2},*,{trafikplats},*"]
                    generated_raw_transition_conflicts += [f"{trafikplats};non-parallel-diff;{movement2},*,{trafikplats},*;{movement1},*,{trafikplats},*"]
                else:
                    generated_raw_transition_conflicts += [line]
                line = file.readline().strip()

            # Now get a transition for every track combination with some shitty code
            # (including some very very very ugly code to take care of the * wildcards)
            for transition_raw in generated_raw_transition_conflicts:
                trafikplats, delay_code, movement1, movement2 = transition_raw.split(";")
                left_key = movement1.split(",")
                right_key = movement2.split(",")

                # Create the lists of tracks (or * still)
                left_key[1], left_key[3], right_key[1], right_key[3] = left_key[1].split(" "), left_key[3].split(" "), right_key[1].split(" "), right_key[3].split(" ")

                # Replace * by actual tracks at that location
                # (but it might be a segment)
                if left_key[1] == ["*"] and left_key[0] == trafikplats:
                    left_key[1] = self.stations[trafikplats].tracks
                elif left_key[1] == ["*"]:
                    left_key[1] = self.segments[(left_key[0], left_key[2])].tracks

                if left_key[3] == ["*"] and left_key[2] == trafikplats:
                    left_key[3] = self.stations[trafikplats].tracks
                elif left_key[3] == ["*"]:
                    left_key[3] = self.segments[(left_key[0], left_key[2])].tracks

                if right_key[1] == ["*"] and right_key[0] == trafikplats:
                    right_key[1] = self.stations[trafikplats].tracks
                elif right_key[1] == ["*"]:
                    right_key[1] = self.segments[(right_key[0], right_key[2])].tracks

                if right_key[3] == ["*"] and right_key[2] == trafikplats:
                    right_key[3] = self.stations[trafikplats].tracks
                elif right_key[3] == ["*"]:
                    right_key[3] = self.segments[(right_key[0], right_key[2])].tracks

                # All combinations of tracks :/
                # We ignore two cases:
                # - Two trains arriving at the same track at the same station
                # - One train arriving at a track at a station, and next train departing there
                # Both cases will be avoided anyway as it conflicts at the track.
                for l1 in left_key[1]:
                    for l3 in left_key[3]:
                        for r1 in right_key[1]:
                            for r3 in right_key[3]:

                                if left_key[2] == trafikplats and right_key[2] == trafikplats and l3 == r3:
                                    continue
                                if left_key[2] == trafikplats and right_key[0] == trafikplats and l3 == r1:
                                    continue

                                generated_transition_conflicts += [(trafikplats, delay_code, (left_key[0], str(l1), left_key[2], str(l3)), (right_key[0], str(r1), right_key[2], str(r3)))]

            print(generated_transition_conflicts)

            # Create the desired dictionary with all movements that conflict a given movement
            for transition in generated_transition_conflicts:
                trafikplats, delay_code, left_key, right_key = transition
                if left_key in self.transitions:
                    self.transitions[left_key] = self.transitions[left_key] + [(right_key, self.headway_dict[delay_code], 0)]
                else:
                    self.transitions[left_key] = [(right_key, self.headway_dict[delay_code], 0)]

                if right_key in self.transitions:
                    self.transitions[right_key] = self.transitions[right_key] + [(left_key, 0, self.headway_dict[delay_code])]
                else:
                    self.transitions[right_key] = [(left_key, 0, self.headway_dict[delay_code])]

            print(self.transitions)
            line = file.readline().strip()

            last_station = ""
            last_segment_tracks = ""

            while line != "":
                if line == "&":
                    last_station = ""
                    last_segment_tracks = ""
                elif last_station == "":
                    last_station, last_station_tracks_str = line.split(";")
                    last_station_tracks = last_station_tracks_str.split(" ")
                elif last_segment_tracks == "":
                    last_segment_tracks = line.split(" ")
                else:
                    next_station, tracks = line.split(";")
                    next_station_tracks = tracks.split(" ")
                    for segment_track in last_segment_tracks:
                        if (last_station, next_station, segment_track) not in self.N_segments:
                            self.N_segments[(last_station, next_station, segment_track)] = next_station_tracks
                        else:
                            self.N_segments[(last_station, next_station, segment_track)] = list(set(self.N_segments[(last_station, next_station, segment_track)] + next_station_tracks))

                    for track in last_station_tracks:
                        if (last_station, next_station, track) not in self.N_stations:
                            self.N_stations[(last_station, next_station, track)] = last_segment_tracks
                        else:
                            self.N_stations[(last_station, next_station, track)] = list(set(self.N_stations[(last_station, track, next_station)] + last_segment_tracks))
                    last_station = next_station
                    last_station_tracks = next_station_tracks
                    last_segment_tracks = ""
                line = file.readline().strip()

            print(self.N_stations)
            print(self.N_segments)
            print(self.segments)


class Station:
    def __init__(self, station, name, tracks):
        self.station = station
        self.name = name
        self.tracks = tracks

    def __repr__(self):
        return f"({self.station}, {self.name}, {self.tracks})"

    def __str__(self):
        return f"({self.station}, {self.name}, {self.tracks})"


class Segment:
    def __init__(self, locations, length, tracks):
        self.locations = set(locations)
        self.length = length
        self.tracks = tracks

    def __repr__(self):
        return f"({self.locations}, {self.length}, {self.tracks})"

    def __str__(self):
        return f"({self.locations}, {self.length}, {self.tracks})"
