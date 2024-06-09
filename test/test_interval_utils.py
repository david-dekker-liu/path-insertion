# content of test_sample.py
from datetime import datetime
import src.interval_utils as intutils
from src.intervals import LinkedInterval, Interval, IntervalPair
import pytest


def d(x):
    return datetime.strptime(x, "%Y-%m-%d %H:%M:%S")


def e(x):
    return "2021-05-11 " + x + ":00"


def d2(x):
    return datetime.strptime(e(x), "%Y-%m-%d %H:%M:%S")


def s(x):
    return x.strftime("%Y-%m-%d %H:%M:%S")


def test_update_time_range_basic():
    linked_interval = LinkedInterval(
        start=d("2021-05-11 13:00:00"),
        end=d("2021-05-11 13:30:00"),
        orig_start=d("2021-05-11 12:00:00"),
        orig_end=d("2021-05-11 12:30:00"))

    new_start = d("2021-05-11 13:10:00")
    new_end = d("2021-05-11 13:20:00")

    updated_linked_interval = intutils.update_time_range(linked_interval, new_start, new_end)

    # I prefer checking separate values over checking whether two objects are the same,
    # as the error messages are clearer here
    assert s(updated_linked_interval.start) == "2021-05-11 13:10:00"
    assert s(updated_linked_interval.end) == "2021-05-11 13:20:00"
    assert s(updated_linked_interval.orig_start) == "2021-05-11 12:10:00"
    assert s(updated_linked_interval.orig_end) == "2021-05-11 12:20:00"


def test_update_time_range_date_boundary():
    linked_interval = LinkedInterval(
        start=d("2021-05-10 20:00:00"),
        end=d("2021-05-11 06:00:00"),
        orig_start=d("2021-05-09 04:10:12"),
        orig_end=d("2021-05-09 14:10:12"))

    new_start = d("2021-05-10 20:00:02")
    new_end = d("2021-05-11 03:15:00")

    updated_linked_interval = intutils.update_time_range(linked_interval, new_start, new_end)

    assert s(updated_linked_interval.start) == "2021-05-10 20:00:02"
    assert s(updated_linked_interval.end) == "2021-05-11 03:15:00"
    assert s(updated_linked_interval.orig_start) == "2021-05-09 04:10:14"
    assert s(updated_linked_interval.orig_end) == "2021-05-09 11:25:12"


# Test for an exception if the interval is not properly shortened
def test_update_time_range_bad_input():
    linked_interval = LinkedInterval(
        start=d("2021-05-10 20:00:00"),
        end=d("2021-05-11 06:00:00"),
        orig_start=d("2021-05-09 04:10:12"),
        orig_end=d("2021-05-09 14:10:12"))

    new_start = d("2021-05-10 18:00:00")
    new_end = d("2021-05-11 03:15:00")

    with pytest.raises(Exception):
        intutils.update_time_range(linked_interval, new_start, new_end)


def test_intersect_intervals():
    linked_interval_list = [
        LinkedInterval(
            d("2021-05-08 14:30:00"),
            d("2021-05-08 14:40:00"),
            d("2021-05-08 04:05:00"),
            d("2021-05-08 04:15:00")),
        LinkedInterval(
            d("2021-05-08 18:00:00"),
            d("2021-05-08 18:45:00"),
            d("2021-05-08 06:04:30"),
            d("2021-05-08 06:49:30")),
        LinkedInterval(
            d("2021-05-08 20:05:10"),
            d("2021-05-08 20:15:40"),
            d("2021-05-08 07:00:00"),
            d("2021-05-08 07:10:30"))]

    interval_list = [Interval(d("2021-05-08 14:00:00"), d("2021-05-08 15:00:00")),
                     Interval(d("2021-05-08 16:00:00"), d("2021-05-08 17:00:00")),
                     Interval(d("2021-05-08 18:00:00"), d("2021-05-08 18:12:00")),
                     Interval(d("2021-05-08 18:20:00"), d("2021-05-08 18:40:00")),
                     Interval(d("2021-05-08 18:40:00"), d("2021-05-08 20:10:00")),
                     Interval(d("2021-05-08 20:15:40"), d("2021-05-08 21:30:00"))]

    intersected_spaces = intutils.intersect_intervals(linked_interval_list, interval_list)

    assert len(intersected_spaces) == 5

    interval_1, interval_2, interval_3, interval_4, interval_5 = intersected_spaces

    assert s(interval_1.start) == "2021-05-08 14:30:00"
    assert s(interval_1.end) == "2021-05-08 14:40:00"
    assert s(interval_1.orig_start) == "2021-05-08 04:05:00"
    assert s(interval_1.orig_end) == "2021-05-08 04:15:00"

    assert s(interval_2.start) == "2021-05-08 18:00:00"
    assert s(interval_2.end) == "2021-05-08 18:12:00"
    assert s(interval_2.orig_start) == "2021-05-08 06:04:30"
    assert s(interval_2.orig_end) == "2021-05-08 06:16:30"

    assert s(interval_3.start) == "2021-05-08 18:20:00"
    assert s(interval_3.end) == "2021-05-08 18:40:00"
    assert s(interval_3.orig_start) == "2021-05-08 06:24:30"
    assert s(interval_3.orig_end) == "2021-05-08 06:44:30"

    assert s(interval_4.start) == "2021-05-08 18:40:00"
    assert s(interval_4.end) == "2021-05-08 18:45:00"
    assert s(interval_4.orig_start) == "2021-05-08 06:44:30"
    assert s(interval_4.orig_end) == "2021-05-08 06:49:30"

    assert s(interval_5.start) == "2021-05-08 20:05:10"
    assert s(interval_5.end) == "2021-05-08 20:10:00"
    assert s(interval_5.orig_start) == "2021-05-08 07:00:00"
    assert s(interval_5.orig_end) == "2021-05-08 07:04:50"


# TODO rewrite...
def test_merge_intervals():
    list_of_intervals = [
        [LinkedInterval(d("2021-05-08 15:00:00"), d("2021-05-08 16:00:00"), d("2021-05-08 13:00:00"), d("2021-05-08 14:00:00")),
         LinkedInterval(d("2021-05-08 17:00:00"), d("2021-05-08 18:00:00"), d("2021-05-08 15:00:00"), d("2021-05-08 16:00:00"))
         ],
        [
            LinkedInterval(d("2021-05-08 15:45:00"), d("2021-05-08 16:30:00"), d("2021-05-08 14:00:00"), d("2021-05-08 14:45:00")),
        ],
        [
            LinkedInterval(d("2021-05-08 14:30:00"), d("2021-05-08 16:00:00"), d("2021-05-08 12:00:00"), d("2021-05-08 13:30:00")),
            LinkedInterval(d("2021-05-08 16:00:00"), d("2021-05-08 17:00:00"), d("2021-05-08 13:30:00"), d("2021-05-08 13:30:00")),
            LinkedInterval(d("2021-05-08 17:30:00"), d("2021-05-08 18:30:00"), d("2021-05-08 14:15:00"), d("2021-05-08 15:15:00")),
        ]
    ]
    merged = intutils.merge_intervals(list_of_intervals)

    assert s(merged[0].start) == "2021-05-08 14:30:00"
    assert s(merged[0].end) == "2021-05-08 15:00:00"
    assert s(merged[0].orig_start) == "2021-05-08 12:00:00"
    assert s(merged[0].orig_end) == "2021-05-08 12:30:00"

    assert s(merged[1].start) == "2021-05-08 15:00:00"
    assert s(merged[1].end) == "2021-05-08 15:45:00"
    assert s(merged[1].orig_start) == "2021-05-08 13:00:00"
    assert s(merged[1].orig_end) == "2021-05-08 13:45:00"

    assert s(merged[2].start) == "2021-05-08 15:45:00"
    assert s(merged[2].end) == "2021-05-08 16:30:00"
    assert s(merged[2].orig_start) == "2021-05-08 14:00:00"
    assert s(merged[2].orig_end) == "2021-05-08 14:45:00"

    assert s(merged[3].start) == "2021-05-08 16:30:00"
    assert s(merged[3].end) == "2021-05-08 17:00:00"
    assert s(merged[3].orig_start) == "2021-05-08 13:30:00"
    assert s(merged[3].orig_end) == "2021-05-08 13:30:00"

    assert s(merged[4].start) == "2021-05-08 17:00:00"
    assert s(merged[4].end) == "2021-05-08 18:00:00"
    assert s(merged[4].orig_start) == "2021-05-08 15:00:00"
    assert s(merged[4].orig_end) == "2021-05-08 16:00:00"

    assert s(merged[5].start) == "2021-05-08 18:00:00"
    assert s(merged[5].end) == "2021-05-08 18:30:00"
    assert s(merged[5].orig_start) == "2021-05-08 14:45:00"
    assert s(merged[5].orig_end) == "2021-05-08 15:15:00"


def test_evaluate_running_times():
    lint_list = [
        LinkedInterval(d2("12:00"), d2("13:00"), d2("11:00"), d2("12:00")),
        LinkedInterval(d2("14:00"), d2("15:00"), d2("13:00"), d2("14:00")),
        LinkedInterval(d2("16:00"), d2("17:00"), d2("15:00"), d2("16:00")),
        LinkedInterval(d2("18:00"), d2("19:00"), d2("17:00"), d2("18:00")),
        LinkedInterval(d2("20:00"), d2("21:00"), d2("19:00"), d2("20:00")),
        LinkedInterval(d2("22:00"), d2("23:00"), d2("21:00"), d2("22:00")),
    ]
    free_spaces = [
        IntervalPair(d2("11:45"), d2("13:45"), d2("12:00"), d2("13:30")),
        IntervalPair(d2("14:30"), d2("15:30"), d2("14:40"), d2("16:30")),
        IntervalPair(d2("16:30"), d2("18:10"), d2("16:45"), d2("18:30")),
        IntervalPair(d2("18:30"), d2("19:00"), d2("18:35"), d2("19:10")),
        IntervalPair(d2("20:15"), d2("22:30"), d2("20:45"), d2("23:30"))
    ]

    output = intutils.evaluate_running_times(lint_list, free_spaces, 15*60)

    assert s(output[0].start) == e("12:15")
    assert s(output[0].end) == e("13:15")
    assert s(output[0].orig_start) == e("11:00")
    assert s(output[0].orig_end) == e("12:00")

    assert s(output[1].start) == e("13:15")
    assert s(output[1].end) == e("13:30")
    assert s(output[1].orig_start) == e("12:00")
    assert s(output[1].orig_end) == e("12:00")

    assert s(output[2].start) == e("14:45")
    assert s(output[2].end) == e("15:15")
    assert s(output[2].orig_start) == e("13:30")
    assert s(output[2].orig_end) == e("14:00")

    assert s(output[3].start) == e("15:15")
    assert s(output[3].end) == e("16:30")
    assert s(output[3].orig_start) == e("14:00")
    assert s(output[3].orig_end) == e("14:00")

    assert s(output[4].start) == e("16:45")
    assert s(output[4].end) == e("17:15")
    assert s(output[4].orig_start) == e("15:30")
    assert s(output[4].orig_end) == e("16:00")

    assert s(output[5].start) == e("17:15")
    assert s(output[5].end) == e("18:15")
    assert s(output[5].orig_start) == e("16:00")
    assert s(output[5].orig_end) == e("16:00")

    assert s(output[6].start) == e("18:15")
    assert s(output[6].end) == e("18:25")
    assert s(output[6].orig_start) == e("17:00")
    assert s(output[6].orig_end) == e("17:10")

    assert s(output[7].start) == e("18:25")
    assert s(output[7].end) == e("18:30")
    assert s(output[7].orig_start) == e("17:10")
    assert s(output[7].orig_end) == e("17:10")

    assert s(output[8].start) == e("18:45")
    assert s(output[8].end) == e("19:10")
    assert s(output[8].orig_start) == e("17:30")
    assert s(output[8].orig_end) == e("17:55")

    assert s(output[9].start) == e("20:45")
    assert s(output[9].end) == e("21:15")
    assert s(output[9].orig_start) == e("19:30")
    assert s(output[9].orig_end) == e("20:00")

    assert s(output[10].start) == e("21:15")
    assert s(output[10].end) == e("22:15")
    assert s(output[10].orig_start) == e("20:00")
    assert s(output[10].orig_end) == e("20:00")

    assert s(output[11].start) == e("22:15")
    assert s(output[11].end) == e("22:45")
    assert s(output[11].orig_start) == e("21:00")
    assert s(output[11].orig_end) == e("21:30")

    assert s(output[12].start) == e("22:45")
    assert s(output[12].end) == e("23:30")
    assert s(output[12].orig_start) == e("21:30")
    assert s(output[12].orig_end) == e("21:30")


def test_extend_parked_times():
    lint_list = [
        LinkedInterval(d2("12:00"), d2("13:00"), d2("11:00"), d2("12:00")),
        LinkedInterval(d2("14:00"), d2("15:00"), d2("13:00"), d2("14:00")),
        LinkedInterval(d2("16:00"), d2("17:00"), d2("15:00"), d2("16:00")),
        LinkedInterval(d2("18:00"), d2("19:00"), d2("17:00"), d2("18:00")),
        LinkedInterval(d2("20:00"), d2("21:00"), d2("19:00"), d2("20:00")),
        LinkedInterval(d2("22:00"), d2("23:00"), d2("21:00"), d2("22:00")),
    ]
    free_spaces = [
        Interval(d2("11:45"), d2("13:45")),
        Interval(d2("14:30"), d2("15:30")),
        Interval(d2("16:30"), d2("18:10")),
        Interval(d2("18:30"), d2("19:00")),
        Interval(d2("20:15"), d2("23:30"))
    ]

    output = intutils.extend_parked_times(lint_list, free_spaces)

    assert s(output[0].start) == e("12:00")
    assert s(output[0].end) == e("13:00")
    assert s(output[0].orig_start) == e("11:00")
    assert s(output[0].orig_end) == e("12:00")

    assert s(output[1].start) == e("13:00")
    assert s(output[1].end) == e("13:45")
    assert s(output[1].orig_start) == e("12:00")
    assert s(output[1].orig_end) == e("12:00")

    assert s(output[2].start) == e("14:30")
    assert s(output[2].end) == e("15:00")
    assert s(output[2].orig_start) == e("13:30")
    assert s(output[2].orig_end) == e("14:00")

    assert s(output[3].start) == e("15:00")
    assert s(output[3].end) == e("15:30")
    assert s(output[3].orig_start) == e("14:00")
    assert s(output[3].orig_end) == e("14:00")

    assert s(output[4].start) == e("16:30")
    assert s(output[4].end) == e("17:00")
    assert s(output[4].orig_start) == e("15:30")
    assert s(output[4].orig_end) == e("16:00")

    assert s(output[5].start) == e("17:00")
    assert s(output[5].end) == e("18:00")
    assert s(output[5].orig_start) == e("16:00")
    assert s(output[5].orig_end) == e("16:00")

    assert s(output[6].start) == e("18:00")
    assert s(output[6].end) == e("18:10")
    assert s(output[6].orig_start) == e("17:00")
    assert s(output[6].orig_end) == e("17:10")

    assert s(output[7].start) == e("18:30")
    assert s(output[7].end) == e("19:00")
    assert s(output[7].orig_start) == e("17:30")
    assert s(output[7].orig_end) == e("18:00")

    assert s(output[8].start) == e("20:15")
    assert s(output[8].end) == e("21:00")
    assert s(output[8].orig_start) == e("19:15")
    assert s(output[8].orig_end) == e("20:00")

    assert s(output[9].start) == e("21:00")
    assert s(output[9].end) == e("22:00")
    assert s(output[9].orig_start) == e("20:00")
    assert s(output[9].orig_end) == e("20:00")

    assert s(output[10].start) == e("22:00")
    assert s(output[10].end) == e("23:00")
    assert s(output[10].orig_start) == e("21:00")
    assert s(output[10].orig_end) == e("22:00")

    assert s(output[11].start) == e("23:00")
    assert s(output[11].end) == e("23:30")
    assert s(output[11].orig_start) == e("22:00")
    assert s(output[11].orig_end) == e("22:00")


def test_extended_intervals_weird_case():
    lint_list = [
        LinkedInterval(d("2021-01-20 09:19:47"), d("2021-01-20 09:20:12"), d("2021-01-20 07:46:20"), d("2021-01-20 07:46:20")),
        LinkedInterval(d("2021-01-20 09:20:12"), d("2021-01-20 09:21:41"), d("2021-01-20 08:14:15"), d("2021-01-20 08:15:44")),
        LinkedInterval(d("2021-01-20 10:24:03"), d("2021-01-20 10:44:38"), d("2021-01-20 08:26:56"), d("2021-01-20 08:26:56")),
    ]
    free_spaces = [
        Interval(d("2021-01-20 07:00:00"), d("2021-01-20 14:00:00"))
    ]

    output = intutils.extend_parked_times(lint_list, free_spaces)

    assert s(output[0].start) == "2021-01-20 09:19:47"
    assert s(output[0].end) == "2021-01-20 09:20:12"
    assert s(output[0].orig_start) == "2021-01-20 07:46:20"
    assert s(output[0].orig_end) == "2021-01-20 07:46:20"

    assert s(output[1].start) == "2021-01-20 09:20:12"
    assert s(output[1].end) == "2021-01-20 09:21:41"
    assert s(output[1].orig_start) == "2021-01-20 08:14:15"
    assert s(output[1].orig_end) == "2021-01-20 08:15:44"

    assert s(output[2].start) == "2021-01-20 09:21:41"
    assert s(output[2].end) == "2021-01-20 10:24:03"
    assert s(output[2].orig_start) == "2021-01-20 08:15:44"
    assert s(output[2].orig_end) == "2021-01-20 08:15:44"

    assert s(output[3].start) == "2021-01-20 10:24:03"
    assert s(output[3].end) == "2021-01-20 14:00:00"
    assert s(output[3].orig_start) == "2021-01-20 08:26:56"
    assert s(output[3].orig_end) == "2021-01-20 08:26:56"
