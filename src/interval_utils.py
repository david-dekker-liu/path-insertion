from src.intervals import LinkedInterval, Interval, IntervalPair
from datetime import timedelta


# Interpolate one time ... guess I did need it after all
def interpolate_single_time(lint, new_time):
    return lint.orig_start + ((new_time - lint.start).seconds / (lint.end - lint.start).seconds) * (lint.orig_end - lint.orig_start)


# Linearly interpolate the start_range at the origin when the interval is shortened
def update_time_range(lint, new_start, new_end):
    if new_start < lint.start or new_end < lint.start or new_end > lint.end or new_start > lint.end or new_end < new_start:
        raise Exception("The new time window is not contained in the old one.", new_start, new_end, lint.start, lint.end)

    new_orig_start = interpolate_single_time(lint, new_start)
    new_orig_end = interpolate_single_time(lint, new_end)

    return LinkedInterval(new_start, new_end, new_orig_start, new_orig_end)


# Plainly intersects an interval list with a set of free spaces
# Returns the modified interval list
def intersect_intervals(linked_interval_list, interval_list):
    output = []

    for linked_interval in linked_interval_list:
        if linked_interval.start == linked_interval.end:
            print("Found bad linked input during intersection.")
            continue
        # Continue splitting this interval as long as to-be-intersected is not completely after it
        while len(interval_list) > 0 and interval_list[0].start < linked_interval.end:
            interval_for_intersection = interval_list[0]

            if interval_for_intersection.start == interval_for_intersection.end:
                interval_list = interval_list[1:]
                continue

            # If the linked interval is completely before the first interval in the second list, we discard it
            if interval_for_intersection.end < linked_interval.start:
                interval_list = interval_list[1:]
                continue

            #
            if interval_for_intersection.start <= linked_interval.start and interval_for_intersection.end <= linked_interval.end:
                output += [update_time_range(linked_interval, linked_interval.start, interval_for_intersection.end)]
                interval_list = interval_list[1:]

            elif interval_for_intersection.start <= linked_interval.start and interval_for_intersection.end > linked_interval.end:

                output += [linked_interval]
                interval_list = [Interval(linked_interval.end, interval_for_intersection.end)] + interval_list[1:]

            elif interval_for_intersection.end <= linked_interval.end:
                output += [update_time_range(linked_interval, interval_for_intersection.start, interval_for_intersection.end)]
                interval_list = interval_list[1:]

            else:
                output += [update_time_range(linked_interval, interval_for_intersection.start, linked_interval.end)]
                interval_list = [Interval(linked_interval.end, interval_for_intersection.end)] + interval_list[1:]

    return output


# Merge intervals when obtaining a list of all 'candidate interval lists' arriving from different tracks
# Returns one interval list
def merge_intervals(lint_lists_to_merge):
    # Input is a list of lists of quadruples, i.e., start-end-orig_start-orig_end
    # We will again return such a list of tuples

    # Get all event time stamps and the interval where they belong to
    all_start_times = [(lint.start, i) for i, lint_list in enumerate(lint_lists_to_merge) for lint in lint_list]
    all_end_times = [(lint.end, i) for i, lint_list in enumerate(lint_lists_to_merge) for lint in lint_list]

    # Get events and sort them
    events = all_start_times + all_end_times
    events.sort(key=lambda x: x[0])
    # Keep track of which intervals are active (when iterating over time) and a pointer to the current one
    active_merge_lists = []
    active_interval_pointer = dict(list(enumerate([0] * len(lint_lists_to_merge))))

    # Iterate over all events. If we progress in time, then we have some interval where we want to determine the latest departure times.
    # Add this interval to the output
    last_event = 0
    output = []

    for event, list_id in events:
        # If we reach a new event time point, we find the relevant max dep times over the last interval
        if event != last_event and len(active_merge_lists) > 0:
            active_intervals = []
            # Determine all active intervals in actual_intervals
            for j in active_merge_lists:
                active_intervals += [lint_lists_to_merge[j][active_interval_pointer[j]]]
            # Determine the intervals when restricted to the current time window
            active_aligned_intervals = [update_time_range(lint, last_event, event) for lint in active_intervals]

            # Find min and max departure time
            max_lint_at_start = max(active_aligned_intervals, key=lambda lint: lint.orig_start)
            max_lint_at_end = max(active_aligned_intervals, key=lambda lint: lint.orig_end)

            # We may need to split up the interval if there are two different maxima at this interval

            if max_lint_at_start.orig_end <= max_lint_at_end.orig_end and max_lint_at_start.orig_start <= max_lint_at_end.orig_start:
                max_lint_at_start = max_lint_at_end
            elif max_lint_at_start.orig_end >= max_lint_at_end.orig_end and max_lint_at_start.orig_start >= max_lint_at_end.orig_start:
                max_lint_at_end = max_lint_at_start
            else:
                # if max_lint_at_start.orig_start != max_lint_at_end.orig_start or max_lint_at_start.orig_end != max_lint_at_start.orig_end:
                print(active_aligned_intervals)
                print(max_lint_at_start.orig_start, max_lint_at_end.orig_start)
                print(max_lint_at_start.orig_end, max_lint_at_end.orig_end)
                # raise Exception("Need to fix this case lol", max_lint_at_start, max_lint_at_end)

            # Add the obtained interval to the output (both should be equal)
            output += [max_lint_at_start]

        # Update last event, the active intervals and the pointers to the actual active ones within those
        last_event = event

        if list_id not in active_merge_lists:
            active_merge_lists += [list_id]
        else:
            active_interval_pointer[list_id] = active_interval_pointer[list_id] + 1
            active_merge_lists.remove(list_id)

    ### Output is kind of finished now. But: we would like to merge consecutive ones if possible ###

    # Last interval. We need to keep track in case two consecutive ones should be merged
    last_start = 0
    last_end = 0
    last_orig_start = 0
    last_orig_end = 0
    last_ratio = 0
    combined_output = []

    for lint in output:
        # No single value intervals
        if lint.start == lint.end:
            raise Exception("No single value intervals allowed.")

        # Ignore initial interval
        if last_start == 0:
            last_start = lint.start
            last_end = lint.end
            last_orig_start = lint.orig_start
            last_orig_end = lint.orig_end
            last_ratio = (lint.orig_end - lint.orig_start).seconds / (lint.end - lint.start).seconds
            continue

        ratio = (lint.orig_end - lint.orig_start).seconds / (lint.end - lint.start).seconds

        # If two intervals should be merged, merge them by changing the last remembered interval
        if last_end == lint.start and last_orig_end == lint.orig_start and close(ratio, last_ratio):
            last_end = lint.end
            last_orig_end = lint.orig_end
        # Otherwise, add last interval to the output
        else:
            combined_output += [LinkedInterval(last_start, last_end, last_orig_start, last_orig_end)]
            last_start = lint.start
            last_end = lint.end
            last_orig_start = lint.orig_start
            last_orig_end = lint.orig_end
            last_ratio = (lint.orig_end - lint.orig_start).seconds / (lint.end - lint.start).seconds

    if len(output) > 0:
        combined_output += [LinkedInterval(last_start, last_end, last_orig_start, last_orig_end)]

    #  [       ]      [               ]
    #    [   ]     []
    #      [             ]
    # ==> List of all 'events'. Between each pair of events, take all relevant intervals
    # ( == the first intervals of those opened)

    # Maintain which sources are 'active' while scanning the events: e.g. 1 True, 2 False, etc.
    # At each event, toggle the (possible multiple) rows
    # Get all (projected!) orig-ranges, find the max start and max end time (hopefully corresponding to same interval...)
    # if not... find intersection (aargh) and ignore a possible 3rd optimal segment in the middle
    # Notice: and that is perfectly fine, as the slope is either constant, or has a nice one-to-one correspondence

    return combined_output


def close(x, y):
    return -0.1 <= x - y <= 0.1


# List of intervals is a list of LinkedIntervals
# Free spaces is a list of pairs of pairs... Good design choices lol
def evaluate_running_times(list_of_intervals, free_spaces, d):
    free_spaces_first_column = [Interval(x.first_start, x.first_end) for x in free_spaces]
    intersected_intervals = intersect_intervals(list_of_intervals, free_spaces_first_column)
    output = []

    # Because of this intersection, we have a few nice properties:
    # * We don't need to worry anymore about the start/end at the current location of the interval
    # * There is exactly one free space that corresponds to each lint
    for i in range(len(intersected_intervals)):
        lint = intersected_intervals[i]

        if lint.start == lint.end:
            continue

        # ... kansloos ...
        while free_spaces[0].first_end <= lint.start:
            free_spaces = free_spaces[1:]

        free_space = free_spaces[0]

        if free_space.first_start == free_space.first_end:
            print("Found bad input in runtime extension free spaces.")
            continue

        ideal_new_start = lint.start + timedelta(0, d)
        ideal_new_end = lint.end + timedelta(0, d)
        new_start = 0
        new_end = 0
        new_orig_start = 0
        new_orig_end = 0

        # If the new start is within the free space, we can derive the new start of the interval easily
        if free_space.second_start <= ideal_new_start <= free_space.second_end:
            new_start = ideal_new_start
            new_orig_start = lint.orig_start
        # If it is before, we can only start at the free space start
        elif ideal_new_start <= free_space.second_start <= free_space.second_end:
            new_start = free_space.second_start
            new_orig_start = interpolate_single_time(lint, new_start - timedelta(0, d))

        if free_space.second_start <= ideal_new_end <= free_space.second_end:
            new_end = ideal_new_end
            new_orig_end = lint.orig_end
        elif free_space.second_start <= free_space.second_end <= ideal_new_end:
            new_end = free_space.second_end
            new_orig_end = interpolate_single_time(lint, new_end - timedelta(0, d))
        # Otherwise, again no point in doing anything

        if new_start != 0 and new_end != 0 and new_start < new_end:
            output += [LinkedInterval(new_start, new_end, new_orig_start, new_orig_end)]

        if i < len(intersected_intervals) - 1:
            next_interval = intersected_intervals[i+1]
            possible_end_time_next_interval = next_interval.start + timedelta(0, d)

            # Determine possible bonus interval (i.e. slow speed within free space)
            if new_end != 0 and new_end < free_space.second_end:
                bonus_start = new_end
                bonus_end = min(possible_end_time_next_interval, free_space.second_end)
                output += [LinkedInterval(bonus_start, bonus_end, new_orig_end, new_orig_end)]
        elif new_end != 0 and new_end < free_space.second_end:
            output += [LinkedInterval(new_end, free_space.second_end, new_orig_end, new_orig_end)]

    return output


def extend_parked_times(lint_list, free_spaces):
    intersected_intervals = intersect_intervals(lint_list, free_spaces)
    output = []

    for i in range(len(intersected_intervals)):
        lint = intersected_intervals[i]

        while free_spaces[0].end <= lint.start:
            free_spaces = free_spaces[1:]

        free_space = free_spaces[0]

        if free_space.start == free_space.end:
            print("Found bad input in parktime extension free spaces.")
            continue

        if lint.orig_end != lint.orig_start:
            output += [lint]

            if i < len(intersected_intervals) - 1:
                next_interval_start = intersected_intervals[i+1].start

                if lint.end < free_space.end:
                    bonus_start = lint.end
                    bonus_end = min(next_interval_start, free_space.end)
                    if bonus_end > bonus_start:
                        output += [LinkedInterval(bonus_start, bonus_end, lint.orig_end, lint.orig_end)]
            elif free_space.end > lint.end:
                output += [LinkedInterval(lint.end, free_space.end, lint.orig_end, lint.orig_end)]
        else:
            if i < len(intersected_intervals) - 1:
                next_interval_start = intersected_intervals[i + 1].start
                bonus_end = min(next_interval_start, free_space.end)
                output += [LinkedInterval(lint.start, bonus_end, lint.orig_end, lint.orig_end)]
            else:
                output += [LinkedInterval(lint.start, free_space.end, lint.orig_end, lint.orig_end)]

    return output


# Takes the union of a list with potentially overlapping intervals
def merge_normal_lists(list_of_intervals):
    events = []
    curr_count = 0
    last_start = 0

    for interval in list_of_intervals:
        events += [(interval.start, "start")]
        events += [(interval.end, "end")]

    events.sort(key=lambda x: x[0])
    output = []

    for event, event_type in events:
        if curr_count == 0 and event_type == "start":
            last_start = event
        elif curr_count == 0 and event_type == "end":
            raise Exception("No interval to end here")
        elif curr_count == 1 and event_type == "end":
            output += [Interval(last_start, event)]

        if event_type == "start":
            curr_count += 1
        else:
            curr_count -= 1

    return output


# Returns the start of the intersection of one interval with a list of intervals, all unlinked
# WARNING assumes the list of intervals is ordered by time
def intersect_one_interval(interval, list_of_intervals):
    for test_interval in list_of_intervals:
        if test_interval.start > interval.end or test_interval.end < interval.start:
            continue
        return Interval(max(test_interval.start, interval.start), min(test_interval.end, interval.end))

    return 0

# Returns the complement of a list of intervals within a certain time window
# WARNING: assumes the list of intervals is a sorted list without any overlap!
def interval_complement(list_of_intervals, window_start, window_end):
    output = []
    last_end = window_start

    for interval in list_of_intervals:
        if interval.end <= window_start:
            continue

        if interval.start <= window_start <= interval.end:
            last_end = interval.end

        if window_start < interval.start < window_end:
            output += [Interval(last_end, interval.start)]
            last_end = interval.end

        if interval.start > window_end:
            continue

    if last_end < window_end:
        output += [Interval(last_end, window_end)]
    return output