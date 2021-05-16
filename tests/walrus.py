from ptera.selfless import selfless


@selfless
def ratatouille(x):
    return (y := x + 1) * y
