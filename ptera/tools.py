import argparse
import json
import os
import re
import sys
from collections import defaultdict
from contextlib import contextmanager

from .core import PteraFunction, overlay
from .selector import to_pattern
from .selfless import PreState
from .tags import Tag, TagSet, match_tag, tag
from .utils import ABSENT

Argument = tag.Argument


def _catalogue(seen, results, fn):
    if id(fn) in seen:
        return

    seen.add(id(fn))

    if isinstance(fn, PteraFunction):
        state = fn.state.state if isinstance(fn.state, PreState) else fn.state
        tst = type(state)
        res = tst.__info__
        results[fn] = res
        for name, ann in res.items():
            val = getattr(state, name, ABSENT)
            _catalogue(seen, results, val)

    elif isinstance(fn, (list, tuple)):
        for entry in fn:
            _catalogue(seen, results, entry)


def catalogue(functions):
    results = {}
    _catalogue(set(), results, functions)
    return results


def _find_configurable(catalogue, tag):
    rval = defaultdict(dict)
    for fn, variables in catalogue.items():
        for name, data in variables.items():
            ann = data["annotation"]
            if match_tag(tag, ann):
                rval[name][fn] = data
    return rval


class ArgsExpander:
    def __init__(
        self, prefix, loader=json.loads, default_file=None,
    ):
        self.prefix = prefix
        self.loader = loader
        self.default_file = default_file
        if default_file:
            assert self.prefix

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

            elif key == "#command":
                results.insert(0, value)

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
        with open(filename) as args_file:
            contents = self.loader(args_file.read())
            return self._generate_args_from_dict(contents)

    def expand(self, argv):
        if self.default_file:
            if os.path.exists(self.default_file):
                pfx = self.prefix[0]
                argv.insert(0, f"{pfx}{self.default_file}")

        new_args = []
        for arg in argv:
            if isinstance(arg, dict):
                new_args.extend(self._generate_args_from_dict(arg))
            elif not arg or arg[0] not in self.prefix:
                new_args.append(arg)
            else:
                new_args.extend(self._generate_args_from_file(arg[1:]))
        return new_args

    def __call__(self, argv, *, parser):
        try:
            return self.expand(argv)
        except OSError:
            err = sys.exc_info()[1]
            parser.error(str(err))


class Configurator:
    def __init__(
        self,
        *,
        entry_point=None,
        tag=Argument,
        description=None,
        argparser=None,
        eval_env=None,
        expand=None,
    ):
        cg = catalogue(entry_point)
        self.tag = tag
        self.names = _find_configurable(cg, tag)
        if argparser is None:
            argparser = argparse.ArgumentParser(
                description=description, argument_default=argparse.SUPPRESS,
            )
        self.argparser = argparser
        self._fill_argparser()
        self.eval_env = eval_env
        self.expand = expand

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
                if isinstance(ann, TagSet):
                    members = ann.members
                else:
                    members = [ann]
                for m in members:
                    if not isinstance(m, Tag):
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
                _metavars = {
                    int: "NUM",
                    float: "NUM",
                    argparse.FileType: "FILE",
                }
                ttyp = typ if isinstance(typ, type) else type(typ)
                mv = _metavars.get(ttyp, "VALUE")
                self.argparser.add_argument(
                    f"--{optname}",
                    dest=name,
                    type=self.resolver(typ or None),
                    action="store",
                    metavar=mv,
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
            if self.expand:
                argv = self.expand(argv, parser=self.argparser)
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
                to_pattern(f"{name}:##X", env={"##X": self.tag}): {
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
    tag=Argument,
    description=None,
    eval_env=None,
    expand=None,
):
    if expand is None or isinstance(expand, str):
        expand = ArgsExpander(
            prefix=expand or "", loader=json.loads, default_file=None,
        )

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
                tag=tag,
                description=description,
                eval_env=eval_env,
            )
            p.set_defaults(**{"#cfg": cfg, "#fn": fn})

        argv = sys.argv[1:] if argv is None else argv
        argv = expand(argv, parser=parser)

        opts = parser.parse_args(argv)
        cfg = getattr(opts, "#cfg")
        fn = getattr(opts, "#fn")
        with cfg(opts):
            return fn(*args)

    else:
        assert isinstance(entry, PteraFunction)
        cfg = Configurator(
            entry_point=entry,
            tag=tag,
            description=description,
            eval_env=eval_env,
            expand=expand,
        )
        with cfg(argv):
            return entry(*args)
