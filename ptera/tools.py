import argparse
import json
import os
import re
import sys
from collections import defaultdict
from contextlib import contextmanager

from .categories import CategorySet, match_category
from .core import PteraFunction, overlay
from .selector import to_pattern
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


def _find_configurable(catalogue, category):
    rval = defaultdict(dict)
    for fn, variables in catalogue.items():
        for name, data in variables.items():
            ann = data["annotation"]
            if match_category(category, ann):
                rval[name][fn] = data
    return rval


class Configurator:
    def __init__(
        self,
        *,
        entry_point=None,
        category=None,
        description=None,
        argparser=None,
        eval_env=None,
        config_option=False,
        default_config_file=None,
    ):
        cg = catalogue(entry_point)
        self.category = category
        self.names = _find_configurable(cg, category)
        if argparser is None:
            argparser = argparse.ArgumentParser(
                description=description,
                argument_default=argparse.SUPPRESS,
                fromfile_prefix_chars="@",
            )
        self.argparser = argparser
        self._fill_argparser()
        if config_option:
            if config_option is True:
                config_option = "config"
            self.argparser.add_argument(
                f"--{config_option}",
                action="store",
                dest="#config",
                metavar="FILE",
                nargs="+",
                type=argparse.FileType("r"),
                help="Configuration file to read options from.",
            )
            self.argparser.add_argument(
                f"--save-{config_option}",
                action="store",
                dest="#save_config",
                metavar="FILE",
                type=argparse.FileType("w"),
                help="Configuration file to save the options to.",
            )
        self.eval_env = eval_env
        self.default_config_file = default_config_file

    def _fill_argparser(self):
        entries = list(sorted(list(self.names.items())))
        for name, data in entries:
            docs = set()
            for fn, entry in data.items():
                if entry["doc"]:
                    docs.add(entry["doc"])
                else:
                    docs.add(f"Parameter in {fn}")

            optname = name.replace("_", "-")
            typ = []
            for x in data.values():
                ann = x["annotation"]
                if isinstance(ann, CategorySet):
                    members = ann.members
                else:
                    members = [ann]
                for m in members:
                    if isinstance(m, type):
                        typ.append(m)
            if len(typ) != 1:
                typ = None
            else:
                (typ,) = typ

            if typ is bool:
                self.argparser.add_argument(
                    f"--{optname}",
                    dest=name,
                    action="store_true",
                    help="; ".join(docs),
                )
                self.argparser.add_argument(
                    f"--no-{optname}",
                    dest=name,
                    action="store_false",
                    help=f"Set --{optname} to False",
                )
            else:
                self.argparser.add_argument(
                    f"--{optname}",
                    dest=name,
                    type=self.resolver(typ or None),
                    action="store",
                    metavar="VALUE",
                    help="; ".join(docs),
                )

    def resolver(self, typ):
        def resolve(arg):
            if typ is str:
                return arg
            elif re.match(r"^:[A-Za-z_0-9]+:", arg):
                _, modname, code = arg.split(":", 2)
                mod = __import__(modname)
                return eval(code, vars(mod))
            elif arg.startswith(":"):
                if not self.eval_env:
                    raise Exception(f"No environment to evaluate {arg}")
                return eval(arg[1:], self.eval_env)
            else:
                return arg if typ is None else typ(arg)

        resolve.__name__ = getattr(typ, "__name__", str(typ))
        return resolve

    def get_options(self, argv):
        if isinstance(argv, argparse.Namespace):
            args = argv
        else:
            args = self.argparser.parse_args(argv)
        opts = {k: v for k, v in vars(args).items() if not k.startswith("#")}

        cfglist = getattr(args, "#config", [])
        if self.default_config_file:
            if os.path.exists(self.default_config_file):
                cfglist.insert(0, open(self.default_config_file))
        for cfg in cfglist:
            with cfg:
                opts2 = json.load(cfg)
                opts = {**opts2, **opts}

        save = getattr(args, "#save_config", None)
        if save:
            print(f"Saving configuration to {save.name}")
            with save:
                json.dump(opts, save, indent=4)
                save.write("\n")
            sys.exit(0)
        return opts

    @contextmanager
    def __call__(self, argv=None):
        def _resolver(value):
            return lambda **_: value

        opts = self.get_options(argv)
        with overlay(
            {
                to_pattern(f"{name}:##X", env={"##X": self.category}): {
                    "value": _resolver(value)
                }
                for name, value in opts.items()
            }
        ):
            yield opts


def auto_cli(
    entry,
    args=(),
    *,
    argv=None,
    entry_point=None,
    category=None,
    description=None,
    eval_env=None,
    config_option=False,
    default_config_file=None,
):
    if isinstance(entry, dict):
        parser = argparse.ArgumentParser(
            description=description, argument_default=argparse.SUPPRESS,
        )
        subparsers = parser.add_subparsers()
        for name, fn in entry.items():
            assert isinstance(fn, PteraFunction)
            p = subparsers.add_parser(
                name, help=fn.__doc__, argument_default=argparse.SUPPRESS
            )
            cfg = Configurator(
                entry_point=fn,
                argparser=p,
                category=category,
                description=description,
                eval_env=eval_env,
                config_option=config_option,
                default_config_file=default_config_file,
            )
            p.set_defaults(**{"#cfg": cfg, "#fn": fn})

        opts = parser.parse_args()
        cfg = getattr(opts, "#cfg")
        fn = getattr(opts, "#fn")
        with cfg(opts):
            fn()

    else:
        assert isinstance(entry, PteraFunction)
        cfg = Configurator(
            entry_point=entry,
            category=category,
            description=description,
            eval_env=eval_env,
            config_option=config_option,
            default_config_file=default_config_file,
        )
        with cfg(argv):
            return entry(*args)
