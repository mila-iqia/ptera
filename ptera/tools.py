import argparse
import re
from collections import defaultdict

from .categories import match_category
from .core import PteraFunction, overlay, Override
from .selfless import PreState
from .utils import ABSENT


def _catalogue(seen, results, fn):
    if id(fn) in seen:
        return

    seen.add(id(fn))

    if isinstance(fn, PteraFunction):
        state = fn.state.state if isinstance(fn.state, PreState) else fn.state
        res = {}
        results[fn] = res
        tst = type(state)
        for name, ann in tst.__annotations__.items():
            res[name] = {
                "annotation": ann,
                "doc": tst.__vardoc__.get(name, None),
            }
            val = getattr(state, name, ABSENT)
            _catalogue(seen, results, val)

    elif isinstance(fn, (list, tuple)):
        for entry in fn:
            _catalogue(seen, results, entry)


def catalogue(functions):
    results = {}
    _catalogue(set(), results, functions)
    return results


_catalogue_fn = catalogue


def _find_configurable(catalogue, category):
    rval = defaultdict(dict)
    for fn, variables in catalogue.items():
        for name, data in variables.items():
            ann = data["annotation"]
            if match_category(category, ann):
                rval[name][fn] = data
    return rval


def _fill_argparser(parser, names):
    entries = list(sorted(list(names.items())))
    for name, data in entries:
        docs = set()
        for fn, entry in data.items():
            if entry["doc"]:
                docs.add(entry["doc"])
            else:
                docs.add(f"Parameter in {fn}")
        parser.add_argument(
            f"--{name}",
            dest=name,
            action="store",
            metavar="VALUE",
            help="; ".join(docs),
        )
    return parser


class Configurator:
    def __init__(
        self,
        *,
        description=None,
        catalogue=None,
        category=None,
        entry_point=None,
        cli=True,
        argparser=None,
        eval_env=None,
    ):
        if catalogue is None:
            catalogue = _catalogue_fn(entry_point)
        catalogue = catalogue

        self.category = category
        self.names = _find_configurable(catalogue, category)
        if cli:
            if argparser is None:
                argparser = argparse.ArgumentParser(description=description)
        self.argparser = _fill_argparser(argparser, self.names)
        self.eval_env = eval_env

    def resolve(self, arg):
        if arg in ("True", "False", "None"):
            return eval(arg)
        elif re.match(r"^:[A-Za-z_0-9]+:", arg):
            _, modname, code = arg.split(":", 2)
            mod = __import__(modname)
            return eval(code, vars(mod))
        elif arg.startswith(":"):
            if not self.eval_env:
                raise Exception(f"No environment to evaluate {arg}")
            return eval(arg[1:], self.eval_env)
        else:
            try:
                f = float(arg)
                return eval(arg)
            except ValueError:
                return arg

    def __enter__(self):
        args = self.argparser.parse_args()
        self.ov = overlay(
            {
                f"{name}:{self.category}": {
                    "value": lambda __v=self.resolve(
                        getattr(args, name)
                    ), **_: __v
                }
                for name in self.names
                if getattr(args, name) is not None
            }
        )
        self.ov.__enter__()
        return self

    def __exit__(self, exc, typ, tb):
        return self.ov.__exit__(exc, typ, tb)


def auto_cli(entry_point, **kwargs):
    cf = Configurator(entry_point=entry_point, **kwargs)
    with cf:
        entry_point()
