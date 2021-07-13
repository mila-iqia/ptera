from rx.operators import (  # noqa: F401
    all,
    amb,
    as_observable,
    average,
    buffer,
    buffer_toggle,
    buffer_when,
    buffer_with_count,
    buffer_with_time,
    buffer_with_time_or_count,
    cast,
    catch,
    combine_latest,
    concat,
    contains,
    count,
    datetime,
    debounce,
    default_if_empty,
    delay,
    delay_subscription,
    delay_with_mapper,
    dematerialize,
    distinct,
    distinct_until_changed,
    do,
    do_action,
    do_while,
    element_at,
    element_at_or_default,
    exclusive,
    expand,
    filter,
    filter_indexed,
    finally_action,
    find,
    find_index,
    first,
    first_or_default,
    flat_map,
    flat_map_indexed,
    flat_map_latest,
    fork_join,
    group_by,
    group_by_until,
    group_join,
    ignore_elements,
    is_empty,
    join,
    last,
    last_or_default,
    map,
    map_indexed,
    materialize,
    max,
    max_by,
    merge,
    merge_all,
    min,
    min_by,
    multicast,
    observe_on,
    on_error_resume_next,
    overload,
    pairwise,
    partition,
    partition_indexed,
    pipe,
    pluck,
    pluck_attr,
    publish,
    publish_value,
    reduce,
    ref_count,
    repeat,
    replay,
    retry,
    sample,
    scan,
    sequence_equal,
    share,
    single,
    single_or_default,
    single_or_default_async,
    skip,
    skip_last,
    skip_last_with_time,
    skip_until,
    skip_until_with_time,
    skip_while,
    skip_while_indexed,
    skip_with_time,
    slice,
    some,
    starmap,
    starmap_indexed,
    start_with,
    subscribe_on,
    sum,
    switch_latest,
    take,
    take_last,
    take_last_buffer,
    take_last_with_time,
    take_until,
    take_until_with_time,
    take_while,
    take_while_indexed,
    take_with_time,
    throttle_first,
    throttle_with_mapper,
    throttle_with_timeout,
    time_interval,
    timedelta,
    timeout,
    timeout_with_mapper,
    timestamp,
    to_dict,
    to_future,
    to_iterable,
    to_list,
    to_marbles,
    to_set,
    typing,
    while_do,
    window,
    window_toggle,
    window_when,
    window_with_count,
    window_with_time,
    window_with_time_or_count,
    with_latest_from,
    zip,
    zip_with_iterable,
    zip_with_list,
)

# Shortcut to throttle_first
throttle = throttle_first


def format(string):
    """Format an object using a format string.

    Arguments:
        string: The format string.
    """

    def _fmt(x):
        if isinstance(x, dict):
            return string.format(**x)
        elif isinstance(x, (list, tuple)):
            return string.format(*x)
        else:
            return string.format(x)

    return map(_fmt)


def getitem(*names):
    """Extract a key from a dictionary.

    Arguments:
        name: Name of the key to index with.
    """
    import operator

    if len(names) == 1:
        (name,) = names
        return map(operator.itemgetter(name))
    else:
        return map(lambda arg: tuple(arg[name] for name in names))


def keymap(fn):
    """Map a dict, passing keyword arguments.

    Arguments:
        fn: A function that will be called for each element, passing the
            element using **kwargs.
    """
    return map(lambda kwargs: fn(**kwargs))


def roll(n, reduce=None, key_mapper=None, seed=None):  # noqa: F811
    """Group the last n elements, giving a sequence of overlapping sequences.

    This can be used to compute a rolling average of the 100 last element:
        op.roll(100, lambda xs: sum(xs) / len(xs))

    Arguments:
        n: The number of elements to group together.
        reduce: A function to reduce the group.

            It should take four arguments:
                last: The last result.
                add: The element that was just added. It is the last element
                    in the elements list.
                drop: The element that was dropped to make room for the
                    added one. It is *not* in the elements argument.
                    If the list of elements is not yet of size n, there is
                    no need to drop anything and drop is None.
                last_size: The window size on the last invocation.
                current_size: The window size on this invocation.

            Defaults to returning the deque of elements directly. The same
            reference is returned each time in order to save memory, so it
            should be processed immediately.
        key_mapper: A transform to apply to each element before reduction.
        seed: The first element of the reduction, defaults to None.
    """

    from collections import deque

    current = seed
    q = deque(maxlen=n)

    def queue(x):
        nonlocal current

        if key_mapper:
            x = key_mapper(x)

        if reduce:
            drop = q[0] if len(q) == n else None
            last_size = len(q)
            q.append(x)
            current_size = len(q)
            current = reduce(current, x, drop, last_size, current_size)
            return current
        else:
            q.append(x)
            return q

    return map(queue)


def rolling_average(n, key_mapper=None):
    """Compute the rolling average of the last n elements.

    Arguments:
        n: The number of elements for the rolling average.
        key_mapper: A transform to apply to each element before averaging.
    """

    def mean(last, add, drop, last_size, current_size):  # noqa: F811
        if last_size == current_size:
            return last + (add - drop) / current_size
        else:
            return (last * last_size + add) / current_size

    return roll(n, key_mapper=key_mapper, reduce=mean, seed=0)


def rolling_average_and_variance(n, key_mapper=None):
    """Compute the rolling average and variance of the last n elements.

    Arguments:
        n: The number of elements for the rolling average and variance.
        key_mapper: A transform to apply to each element before averaging.
    """
    v2 = 0

    def meanvar(last, add, drop, last_size, current_size):  # noqa: F811
        nonlocal v2

        prev_mean, _ = last
        if last_size == current_size:
            new_mean = prev_mean + (add - drop) / current_size
            v2 += (add - prev_mean) * (add - new_mean) - (drop - prev_mean) * (
                drop - new_mean
            )
        else:
            new_mean = (prev_mean * last_size + add) / current_size
            v2 += (add - prev_mean) * (add - new_mean)
        return (
            new_mean,
            v2 / (current_size - 1) if current_size >= 2 else None,
        )

    return pipe(
        roll(n, key_mapper=key_mapper, reduce=meanvar, seed=(0, 0)), skip(1)
    )
