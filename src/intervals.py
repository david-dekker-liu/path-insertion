from datetime import datetime


class LinkedInterval:
    def __init__(self, start, end, orig_start, orig_end):
        self.start = start
        self.end = end
        self.orig_start = orig_start
        self.orig_end = orig_end

    def __eq__(self, other):
        if type(other) is type(self):
            return self.__dict__ == other.__dict__
        return False

    def __repr__(self):
        return f"({self.start.strftime('%Y-%m-%d %H:%M:%S')}, {self.end.strftime('%Y-%m-%d %H:%M:%S')}, {self.orig_start.strftime('%Y-%m-%d %H:%M:%S')}, {self.orig_end.strftime('%Y-%m-%d %H:%M:%S')})"

    def __str__(self):
        return f"({self.start.strftime('%Y-%m-%d %H:%M:%S')}, {self.end.strftime('%Y-%m-%d %H:%M:%S')}, {self.orig_start.strftime('%Y-%m-%d %H:%M:%S')}, {self.orig_end.strftime('%Y-%m-%d %H:%M:%S')})"


class Interval:
    def __init__(self, start, end):
        self.start = start
        self.end = end

    def __repr__(self):
        return f"({self.start.strftime('%Y-%m-%d %H:%M:%S')}, {self.end.strftime('%Y-%m-%d %H:%M:%S')})"

    def __str__(self):
        return f"({self.start.strftime('%Y-%m-%d %H:%M:%S')}, {self.end.strftime('%Y-%m-%d %H:%M:%S')})"


class IntervalPair:
    def __init__(self, first_start, first_end, second_start, second_end):
        self.first_start = first_start
        self.first_end = first_end
        self.second_start = second_start
        self.second_end = second_end

    def __eq__(self, other):
        if type(other) is type(self):
            return self.__dict__ == other.__dict__
        return False

    def __repr__(self):
        return f"({self.first_start.strftime('%Y-%m-%d %H:%M:%S')}, {self.first_end.strftime('%Y-%m-%d %H:%M:%S')}, {self.second_start.strftime('%Y-%m-%d %H:%M:%S')}, {self.second_end.strftime('%Y-%m-%d %H:%M:%S')})"

    def __str__(self):
        return f"({self.first_start.strftime('%Y-%m-%d %H:%M:%S')}, {self.first_end.strftime('%Y-%m-%d %H:%M:%S')}, {self.second_start.strftime('%Y-%m-%d %H:%M:%S')}, {self.second_end.strftime('%Y-%m-%d %H:%M:%S')})"