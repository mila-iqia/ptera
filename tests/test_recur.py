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
