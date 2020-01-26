import ast
import inspect
from ast import NodeTransformer
from textwrap import dedent

from .core import interact as default_interact


idx = 0


def gensym():
    global idx
    idx += 1
    return f'_ptera_tmp_{idx}'


class PteraTransformer(NodeTransformer):
    def __init__(self):
        super().__init__()
        self.current_fn = None

    def make_interaction(self, target, ann, value):
        if isinstance(target, ast.Name):
            value_args = [
                ast.Constant(value=target.id),
                ast.Constant(value=None),
                ann if ann else ast.Constant(value=None),
            ]
        elif isinstance(target, ast.Subscript):
            value_args = [
                ast.Constant(value=target.value.id),
                target.slice.value,
                ann if ann else ast.Constant(value=None),
            ]
        else:
            raise SyntaxError(target)
        if value is not None:
            value_args.append(value)
        new_value = ast.Call(
            func=ast.Name("__ptera_interact", ctx=ast.Load()),
            args=value_args,
            keywords=[],
        )
        if ann is None:
            return [ast.Assign(targets=[target], value=new_value)]
        else:
            return [ast.AnnAssign(
                target=target, value=new_value, annotation=ann, simple=True
            )]

    def visit_FunctionDef(self, node):
        new_body = []
        old_fn = self.current_fn
        self.current_fn = node.name
        for arg in node.args.args:
            new_body.extend(
                self.make_interaction(
                    target=ast.Name(id=arg.arg, ctx=ast.Store()),
                    ann=arg.annotation,
                    value=ast.Name(id=arg.arg, ctx=ast.Load()),
                )
            )
        for stmt in map(self.visit, node.body):
            if isinstance(stmt, list):
                new_body.extend(stmt)
            else:
                new_body.append(stmt)
        self.current_fn = old_fn
        return ast.FunctionDef(
            name=node.name,
            args=node.args,
            body=new_body,
            decorator_list=node.decorator_list,
            returns=node.returns,
            type_comment=node.type_comment,
        )

    def visit_Return(self, node):
        new_value = ast.Call(
            func=ast.Name("__ptera_interact", ctx=ast.Load()),
            args=[
                ast.Constant(value=self.current_fn),
                ast.Constant(value=None),
                ast.Constant(value=None),
                node.value,
            ],
            keywords=[],
        )
        return ast.Return(value=new_value)

    def visit_AnnAssign(self, node):
        """Rewrite an annotated assignment expression.

        Before::
            x: int

        After::
            x: int = ptera.interact('x', int)
        """
        return self.make_interaction(node.target, node.annotation, node.value)

    def visit_Assign(self, node):
        """Rewrite an assignment expression.

        Before::
            x = y + z

        After::
            x = ptera.interact('x', None, y + z)
        """
        target, = node.targets
        if isinstance(target, ast.Tuple):
            var_all = gensym()
            ass_all = ast.Assign(
                targets=[ast.Name(id=var_all, ctx=ast.Store())],
                value=node.value
            )
            accum = [ass_all]
            for i, tgt in enumerate(target.elts):
                accum += self.visit_Assign(
                    ast.Assign(
                        targets=[tgt],
                        value=ast.Subscript(
                            value=ast.Name(id=var_all, ctx=ast.Load()),
                            slice=ast.Index(value=ast.Constant(i)),
                            ctx=ast.Load()
                        )
                    )
                )
            return accum
        else:
            return self.make_interaction(target, None, node.value)


def transform(fn, interact=default_interact):
    src = dedent(inspect.getsource(fn))
    filename = inspect.getsourcefile(fn)
    tree = ast.parse(src, filename)
    tree = tree.body[0]
    assert isinstance(tree, ast.FunctionDef)
    tree.decorator_list = []
    new_tree = PteraTransformer().visit(tree)
    ast.fix_missing_locations(new_tree)
    _, lineno = inspect.getsourcelines(fn)
    ast.increment_lineno(new_tree, lineno)
    new_fn = compile(
        ast.Module(body=[new_tree], type_ignores=[]), filename, "exec"
    )
    glb = fn.__globals__
    glb["__ptera_interact"] = interact
    exec(new_fn, glb, glb)
    return glb[fn.__name__]
