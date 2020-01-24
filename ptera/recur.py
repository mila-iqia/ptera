from collections import deque


class Recurrence:
    def __init__(self, lookback=1):
        self.lookback = lookback
        self.offset = None
        self.values = deque(maxlen=self.lookback)

    def __getitem__(self, idx):
        assert isinstance(idx, int)
        assert self.offset is not None
        idx -= self.offset
        if idx < 0:
            raise IndexError(f"Index {idx} is out of bounds")
        return self.values[idx]

    def __setitem__(self, idx, value):
        if self.offset is None:
            self.offset = idx
        if len(self.values) == self.lookback:
            self.offset += 1
        self.values.append(value)

    def __str__(self):
        values = {i + self.offset: value for i, value in enumerate(self.values)}
        return f"Recurrence({self.lookback}, {values})"

    __repr__ = __str__
