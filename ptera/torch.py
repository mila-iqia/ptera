import torch

from .core import Capture, Collector, to_pattern


class GradCollector(Collector):
    def __init__(self, pattern, mapper=None):
        super().__init__(pattern, None)
        self._mapper = mapper
        (self.target,) = self.pattern.find_tag(2)

    def finalize(self):
        def _log(cap, name, value):
            def hook(g):
                cap.accum(name, (value, g))

            return hook

        groups = {}
        for entry in self.map_full():
            target = entry[self.target.capture].value
            groups.setdefault(id(target), {"target": target, "entries": []})
            groups[id(target)]["entries"].append(
                {
                    name: cap
                    for name, cap in entry.items()
                    if name != self.target.capture
                }
            )

        new_entries = []
        for x in groups.values():
            hooks = []
            target = x["target"]
            for entry in x["entries"]:
                new_entry = {}
                for name, cap in entry.items():
                    new_cap = Capture(cap.element)
                    new_entry[name] = new_cap
                    for realname, value in zip(cap.names, cap.values):
                        if isinstance(value, int):
                            new_cap.accum(name, value)
                        else:
                            value.grad = None
                            hooks.append(
                                value.register_hook(
                                    _log(new_cap, realname, value)
                                )
                            )
                new_entries.append(new_entry)
            target.backward(torch.ones(target.shape), retain_graph=True)
            for h in hooks:
                h.remove()

        final_collector = Collector(self.pattern)
        final_collector.data = new_entries

        if self._mapper:
            return final_collector.map_full(self._mapper)
        else:
            return final_collector


class Grad:
    hasoutput = True

    def __init__(self, selector, mapper=None):
        self.selector = to_pattern(selector)
        self.mapper = mapper

    def hook(self, mapper):
        self.mapper = mapper
        return self

    def instantiate(self):
        return GradCollector(self.selector, self.mapper)
