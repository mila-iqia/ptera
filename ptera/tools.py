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


class ArgsExpander:
    def __init__(
        self,
        argparser,
        fromfile_prefix_chars,
        fromfile_loader,
        default_file,
    ):
        self.argparser = argparser
        self.fromfile_prefix_chars = fromfile_prefix_chars
        self.fromfile_loader = fromfile_loader
        self.default_file = default_file
        if default_file:
            assert self.fromfile_prefix_chars

    def _generate_args_from_dict(self, contents):
        results = []
        for key, value in contents.items():
            if key == "#include":
                if not isinstance(value, (list, tuple)):
                    value = [value]
                for other_filename in value:
                    results.extend(
                        self._generate_args_from_file(other_filename)
                    )

            elif isinstance(value, bool):
                if value:
                    results.append(f"--{key}")
                else:
                    results.append(f"--no-{key}")

            else:
                results.append(f"--{key}")
                results.append(str(value))
        return results

    def _generate_args_from_file(self, filename):
        try:
            with open(filename) as args_file:
                contents = self.fromfile_loader(args_file.read())
                return self._generate_args_from_dict(contents)
        except OSError:
            err = sys.exc_info()[1]
            self.argparser.error(str(err))

    def __call__(self, argv):
        if self.default_file:
            if os.path.exists(self.default_file):
                pfx = self.fromfile_prefix_chars[0]
                argv.insert(0, f"{pfx}{self.default_file}")

        new_args = []
        for arg in argv:
            if isinstance(arg, dict):
                new_args.extend(self._generate_args_from_dict(arg))
            elif not arg or arg[0] not in self.fromfile_prefix_chars:
                new_args.append(arg)
            else:
                new_args.extend(self._generate_args_from_file(arg[1:]))
        return new_args


class Configurator:
    def __init__(
        self,
        *,
        entry_point=None,
        category=None,
        description=None,
        argparser=None,
        eval_env=None,
        default_config_file=None,
        fromfile_prefix_chars=(),
        fromfile_loader=json.loads,
    ):
        cg = catalogue(entry_point)
        self.category = category
        self.names = _find_configurable(cg, category)
        if argparser is None:
            argparser = argparse.ArgumentParser(
                description=description, argument_default=argparse.SUPPRESS,
            )
        self.argparser = argparser
        self._fill_argparser()
        self.eval_env = eval_env
        self.expand = ArgsExpander(
            argparser=argparser,
            fromfile_prefix_chars=fromfile_prefix_chars,
            fromfile_loader=fromfile_loader,
            default_file=default_config_file,
        )

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
            argv = sys.argv[1:] if argv is None else argv
            argv = self.expand(argv)
            args = self.argparser.parse_args(argv)
        opts = {k: v for k, v in vars(args).items() if not k.startswith("#")}
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
    default_config_file=None,
    fromfile_prefix_chars=(),
    fromfile_loader=json.loads,
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
                default_config_file=default_config_file,
                fromfile_prefix_chars=fromfile_prefix_chars,
                fromfile_loader=fromfile_loader,
            )
            p.set_defaults(**{"#cfg": cfg, "#fn": fn})

        opts = parser.parse_args(argv)
        cfg = getattr(opts, "#cfg")
        fn = getattr(opts, "#fn")
        with cfg(opts):
            return fn(*args)

    else:
        assert isinstance(entry, PteraFunction)
        cfg = Configurator(
            entry_point=entry,
            category=category,
            description=description,
            eval_env=eval_env,
            default_config_file=default_config_file,
            fromfile_prefix_chars=fromfile_prefix_chars,
            fromfile_loader=fromfile_loader,
        )
        with cfg(argv):
            return entry(*args)
