import functools
import inspect


def keyword_decorator(deco):
    """Wrap a decorator to optionally takes keyword arguments."""

    @functools.wraps(deco)
    def new_deco(fn=None, **kwargs):
        if fn is None:

            @functools.wraps(deco)
            def newer_deco(fn):
                return deco(fn, **kwargs)

            return newer_deco
        else:
            return deco(fn, **kwargs)

    return new_deco


def call_with_captures(fn, captures, full=True):
    args = inspect.getfullargspec(fn)
    if args.varkw:
        kwargs = captures
    else:
        kwargs = {}
        for k, v in captures.items():
            if k in args.args or k in args.kwonlyargs or args.varkw:
                kwargs[k] = v
    if not full:
        kwargs = {k: v.value for k, v in kwargs.items()}
    return fn(**kwargs)
