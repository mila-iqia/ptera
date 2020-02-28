import pytest

from ptera.recur import Recurrence


def test_recurrence():
    rq = Recurrence(2)

    rq[0] = 9
    with pytest.raises(IndexError):
        rq[-1]
    assert rq[0] == 9

    rq[1] = 3
    assert rq[0] == 9
    assert rq[1] == 3

    rq[2] = 4
    with pytest.raises(IndexError):
        rq[0]
    assert rq[1] == 3
    assert rq[2] == 4


def test_recurrence_repr():
    rq = Recurrence(2)
    assert str(rq) == "Recurrence(2, {})"
    rq[0] = 1
    rq[1] = 2
    rq[2] = 3
    rq[3] = 4
    assert str(rq) == "Recurrence(2, {2: 3, 3: 4})"
