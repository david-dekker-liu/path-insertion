# Returns list of all segments in conflict with current segment
def get_segment_conflicts(seg_key):
    return [seg_key]


# Returns the headway before some train at some segment
# Used for adding headways in the T21-dataframe
def headway_before(row):
    if row["segment_type"] == "station":
        return get_min_block_diff_at_station_before(row["train_id"], row["orig"], row["track_id"])

    if row["segment_type"] == "single_block_segment":
        return get_min_block_diff_at_station_before(row["train_id"], row["orig"], row["dest"])

    if row["segment_type"] == "multiple_block_segments":
        return get_headway_before(row["train_id"], row["orig"], row["dest"])


# Returns the headway after some train at some segment
# Used for adding headways in the T21-dataframe
def headway_after(row):
    if row["segment_type"] == "station":
        return get_min_block_diff_at_station_after(row["train_id"], row["orig"], row["track_id"])

    if row["segment_type"] == "single_block_segment":
        return get_min_block_diff_at_station_after(row["train_id"], row["orig"], row["dest"])

    if row["segment_type"] == "multiple_block_segments":
        return get_headway_after(row["train_id"], row["orig"], row["dest"])


# Headway at double track segment
def get_headway_before(train_id, orig, dest):
    return 180


# Headway at double tracks segment
def get_headway_after(train_id, orig, dest):
    return 180


# Returns the minimum time after the train has left the segment at dest
def get_min_block_diff_at_single_track_after(train_id, orig, dest):
    return 60


# Returns the minimum time before the train can enter the segment at origin
def get_min_block_diff_at_single_track_before(train_id, orig, dest):
    return 60


# Headway between station track occupation
def get_min_block_diff_at_station_after(train_id, station, track_id):
    return 180


# Headway between station track occupation
def get_min_block_diff_at_station_before(train_id, station, track_id):
    return 180


def get_min_block_diff_at_transition_before(train_id, main_loc, towards_loc, main_track_id, towards_track_id, arriving_boolean):
    if arriving_boolean:
        return 180
    else:
        return 60


def get_min_block_diff_at_transition_after(train_id, main_loc, towards_loc, main_track_id, towards_track_id, arriving_boolean):
    if arriving_boolean:
        return 60
    else:
        return 180
