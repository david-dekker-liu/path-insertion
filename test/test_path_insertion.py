# content of test_sample.py
from datetime import datetime
import path_insertion
import pytest


def d(x):
    return datetime.strptime(x, "%Y-%m-%d %H:%M:%S")


def s(x):
    return x.strftime("%Y-%m-%d %H:%M:%S")


# Tests the linear interpolation of a time window when the corresponding window is shortened
def test_update_time_range_basic():
    window = (d("2021-05-11 13:18:00"), d("2021-05-11 13:38:00"))
    new_window = (d("2021-05-11 13:28:00"), d("2021-05-11 13:33:00"))
    original_departure_window = (d("2021-05-11 12:00:00"), d("2021-05-11 12:20:00"))

    new_departure_window = path_insertion.update_time_range(window[0], window[1], new_window[0], new_window[1], True, original_departure_window)

    assert s(new_departure_window[0]) == "2021-05-11 12:10:00"
    assert s(new_departure_window[1]) == "2021-05-11 12:15:00"


# Tests the linear interpolation of a time window when the corresponding window is shortened
def test_update_time_range_date_boundary():
    window = (d("2021-05-10 20:00:00"), d("2021-05-11 06:00:00"))
    new_window = (d("2021-05-10 20:00:02"), d("2021-05-11 03:15:00"))
    original_departure_window = (d("2021-05-09 04:10:12"), d("2021-05-09 14:10:12"))

    new_departure_window = path_insertion.update_time_range(window[0], window[1], new_window[0], new_window[1], True, original_departure_window)

    assert s(new_departure_window[0]) == "2021-05-09 04:10:14"
    assert s(new_departure_window[1]) == "2021-05-09 11:25:12"


# Tests the linear interpolation of a time window when the corresponding window is shortened, with bad input
def test_update_time_range_bad_input():
    window = (d("2021-05-10 20:00:00"), d("2021-05-11 06:00:00"))
    new_window = (d("2021-05-10 19:59:58"), d("2021-05-11 03:15:00"))
    original_departure_window = (d("2021-05-09 04:10:12"), d("2021-05-09 14:10:12"))

    with pytest.raises(Exception) as excinfo:
        path_insertion.update_time_range(window[0], window[1], new_window[0], new_window[1], True, original_departure_window)
    assert str(excinfo.value) == "The new time window is not contained in the old one."


# Tests the linear interpolation of a time window when the corresponding window is shortened
def test_update_time_range_constant():
    window = (d("2021-05-08 22:00:55"), d("2021-05-08 23:12:01"))
    new_window = (d("2021-05-08 22:22:22"), d("2021-05-08 22:52:55"))
    original_departure_window = (d("2021-05-07 11:11:11"), d("2021-05-07 11:11:11"))

    new_departure_window = path_insertion.update_time_range(window[0], window[1], new_window[0], new_window[1], True, original_departure_window)

    assert s(new_departure_window[0]) == "2021-05-07 11:11:11"
    assert s(new_departure_window[1]) == "2021-05-07 11:11:11"


def test_intersect():
    possibly_entering = [(d("2021-05-08 14:30:00"), d("2021-05-08 14:40:00"), d("2021-05-08 04:05:00"), d("2021-05-08 04:15:00")), (d("2021-05-08 18:00:00"), d("2021-05-08 18:45:00"), d("2021-05-08 06:04:30"), d("2021-05-08 06:49:30")), (d("2021-05-08 20:05:10"), d("2021-05-08 20:15:40"), d("2021-05-08 07:00:00"), d("2021-05-08 07:10:30"))]
    intersections = [(d("2021-05-08 14:00:00"), d("2021-05-08 15:00:00")), (d("2021-05-08 16:00:00"), d("2021-05-08 17:00:00")), (d("2021-05-08 18:00:00"), d("2021-05-08 18:12:00")), (d("2021-05-08 18:20:00"), d("2021-05-08 18:40:00")), (d("2021-05-08 18:40:00"), d("2021-05-08 20:10:00")), (d("2021-05-08 20:15:40"), d("2021-05-08 21:30:00"))]

    intersected_spaces = path_insertion.intersect(possibly_entering, intersections)

    # Observe: we ignore the single time stamp interval at 20:15:40!
    assert len(intersected_spaces) == 5

    window_0, window_1, window_2, window_3, window_4 = intersected_spaces

    assert s(window_0[0]) == "2021-05-08 14:30:00"
    assert s(window_0[1]) == "2021-05-08 14:40:00"
    assert s(window_0[2]) == "2021-05-08 04:05:00"
    assert s(window_0[3]) == "2021-05-08 04:15:00"

    assert s(window_1[0]) == "2021-05-08 18:00:00"
    assert s(window_1[1]) == "2021-05-08 18:12:00"
    assert s(window_1[2]) == "2021-05-08 06:04:30"
    assert s(window_1[3]) == "2021-05-08 06:16:30"

    assert s(window_2[0]) == "2021-05-08 18:20:00"
    assert s(window_2[1]) == "2021-05-08 18:40:00"
    assert s(window_2[2]) == "2021-05-08 06:24:30"
    assert s(window_2[3]) == "2021-05-08 06:44:30"

    assert s(window_3[0]) == "2021-05-08 18:40:00"
    assert s(window_3[1]) == "2021-05-08 18:45:00"
    assert s(window_3[2]) == "2021-05-08 06:44:30"
    assert s(window_3[3]) == "2021-05-08 06:49:30"

    assert s(window_4[0]) == "2021-05-08 20:05:10"
    assert s(window_4[1]) == "2021-05-08 20:10:00"
    assert s(window_4[2]) == "2021-05-08 07:00:00"
    assert s(window_4[3]) == "2021-05-08 07:04:50"


def test_merge_intervals():
    list_of_intervals = [
        [(d("2021-05-08 15:00:00"), d("2021-05-08 16:00:00"), d("2021-05-08 13:00:00"), d("2021-05-08 14:00:00")),
         (d("2021-05-08 17:00:00"), d("2021-05-08 18:00:00"), d("2021-05-08 15:00:00"), d("2021-05-08 16:00:00"))
         ],
        [
            (d("2021-05-08 15:45:00"), d("2021-05-08 16:30:00"), d("2021-05-08 14:00:00"), d("2021-05-08 14:45:00")),
        ],
        [
            (d("2021-05-08 14:30:00"), d("2021-05-08 16:00:00"), d("2021-05-08 12:00:00"), d("2021-05-08 13:30:00")),
            (d("2021-05-08 16:00:00"), d("2021-05-08 17:00:00"), d("2021-05-08 13:30:00"), d("2021-05-08 13:30:00")),
            (d("2021-05-08 17:30:00"), d("2021-05-08 18:30:00"), d("2021-05-08 14:15:00"), d("2021-05-08 15:15:00")),
        ]
    ]

    merged = path_insertion.merge_intervals(list_of_intervals)

    assert s(merged[0][0]) == "2021-05-08 14:30:00"
    assert s(merged[0][1]) == "2021-05-08 15:00:00"
    assert s(merged[0][2]) == "2021-05-08 12:00:00"
    assert s(merged[0][3]) == "2021-05-08 12:30:00"

    assert s(merged[1][0]) == "2021-05-08 15:00:00"
    assert s(merged[1][1]) == "2021-05-08 15:45:00"
    assert s(merged[1][2]) == "2021-05-08 13:00:00"
    assert s(merged[1][3]) == "2021-05-08 13:45:00"

    assert s(merged[2][0]) == "2021-05-08 15:45:00"
    assert s(merged[2][1]) == "2021-05-08 16:30:00"
    assert s(merged[2][2]) == "2021-05-08 14:00:00"
    assert s(merged[2][3]) == "2021-05-08 14:45:00"

    assert s(merged[3][0]) == "2021-05-08 16:30:00"
    assert s(merged[3][1]) == "2021-05-08 17:00:00"
    assert s(merged[3][2]) == "2021-05-08 13:30:00"
    assert s(merged[3][3]) == "2021-05-08 13:30:00"

    assert s(merged[4][0]) == "2021-05-08 17:00:00"
    assert s(merged[4][1]) == "2021-05-08 18:00:00"
    assert s(merged[4][2]) == "2021-05-08 15:00:00"
    assert s(merged[4][3]) == "2021-05-08 16:00:00"

    assert s(merged[5][0]) == "2021-05-08 18:00:00"
    assert s(merged[5][1]) == "2021-05-08 18:30:00"
    assert s(merged[5][2]) == "2021-05-08 14:45:00"
    assert s(merged[5][3]) == "2021-05-08 15:15:00"