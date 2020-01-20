import ast
import inspect
from ast import NodeTransformer


class PteraTransformer(NodeTransformer):
    def __init__(self):
        super().__init__()
        self.current_fn = None

    def make_interaction(self, targets, ann, value):
        (var_node,) = targets
        value_args = [
            ast.Constant(value=var_node.id),
            ann if ann else ast.Constant(value=None),
        ]
        if value is not None:
            value_args.append(value)
        new_value = ast.Call(
            func=ast.Name("__ptera_interact", ctx=ast.Load()),
            args=value_args,
            keywords=[],
        )
        if ann is None:
            return ast.Assign(targets=targets, value=new_value)
        else:
            return ast.AnnAssign(
                target=targets[0], value=new_value, annotation=ann, simple=True
            )

    def visit_FunctionDef(self, node):
        new_body = []
        old_fn = self.current_fn
        self.current_fn = node.name
        for arg in node.args.args:
            new_body.append(
                self.make_interaction(
                    targets=[ast.Name(id=arg.arg, ctx=ast.Store())],
                    ann=arg.annotation,
                    value=ast.Name(id=arg.arg, ctx=ast.Load()),
                )
            )
        new_body.extend(map(self.visit, node.body))
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
        return self.make_interaction([node.target], node.annotation, node.value)

    def visit_Assign(self, node):
        """Rewrite an assignment expression.

        Before::
            x = y + z

        After::
            x = ptera.interact('x', None, y + z)
        """
        return self.make_interaction(node.targets, None, node.value)


def transform(fn):
    from . import interact

    src = inspect.getsource(fn)
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
