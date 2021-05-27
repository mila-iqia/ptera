def inc(fn):
    def deco(x):
        return fn(x) + 1

    return deco


@inc
@inc
@inc
def cheese(x):
    a = x * x
    return a + 1
