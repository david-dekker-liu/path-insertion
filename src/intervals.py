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


class Interval:
    def __init__(self, start, end):
        self.start = start
        self.end = end
