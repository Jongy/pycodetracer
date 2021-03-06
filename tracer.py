from __future__ import annotations

import argparse
import ast
import os
import sys
from ast import (
    AST,
    Add,
    Assign,
    Attribute,
    AugAssign,
    BinOp,
    Call,
    Constant,
    Expr,
    FunctionDef,
    Global,
    Import,
    Load,
    Module,
    Mult,
    Name,
    NodeTransformer,
    Return,
    Store,
    Sub,
    alias,
    arg,
    copy_location,
    expr,
    fix_missing_locations,
    keyword,
    parse,
    stmt,
)
from typing import List, Sequence, Tuple, Union, cast

from termcolor import colored


# TODO: break up to multiple transformers
class TraceTransformer(NodeTransformer):
    _INDENT = 2  # indentation per depth
    _DEPTH_VAR = "__depth"
    _RETURN_VAR = "__return"
    FUNC_COLOR = "red"  # colors function calls
    FUNC_CALLED_COLOR = "yellow"  # colors called functions
    RETURN_COLOR = "magenta"  # colors returns & values
    NAME_COLOR = "green"  # colors names
    CONST_COLOR = "cyan"  # colors constants

    # backported from ast._Unparser (3.9 IIRC)
    BINOP = {
        "Add": "+",
        "Sub": "-",
        "Mult": "*",
        "MatMult": "@",
        "Div": "/",
        "Mod": "%",
        "LShift": "<<",
        "RShift": ">>",
        "BitOr": "|",
        "BitXor": "^",
        "BitAnd": "&",
        "FloorDiv": "//",
        "Pow": "**",
    }

    @staticmethod
    def _fix_location(n: AST, old: AST):
        return fix_missing_locations(copy_location(n, old))

    def _fix_location_all(self, nodes: Sequence[AST], old: AST):
        return [self._fix_location(n, old) for n in nodes]

    def _make_print(self, ns: List[expr], prefix: str = None) -> Expr:
        # create the indent: ' ' * depth
        mul_by = Name(self._DEPTH_VAR, Load())
        indent = BinOp(Constant(" "), Mult(), mul_by)
        # if prefix is given, indent is: ' ' * (depth - len(prefix)) + prefix
        if prefix is not None:
            assert len(prefix) <= self._INDENT, f"too long {prefix} for given indent {self._INDENT}"
            indent.right = BinOp(mul_by, Sub(), Constant(len(prefix)))
            indent = BinOp(indent, Add(), Constant(prefix))

        return Expr(
            Call(
                Name("print", Load()),
                args=cast(List[expr], [indent]) + ns,
                keywords=[
                    keyword("sep", Constant("")),
                    keyword("file", Attribute(Name("sys", Load()), "stderr", Load())),
                ],
            )
        )

    def _repr_rvalue(self, n: AST) -> str:
        if isinstance(n, Name):
            assert isinstance(n.ctx, Load)
            return colored(f"{n.id} ({{{n.id}!r}})", self.NAME_COLOR)
        elif isinstance(n, Constant):
            return colored(f"{n.value!r}", self.CONST_COLOR)
        elif isinstance(n, BinOp):
            # TODO should use cached result, as it may have side effects. see comment on Call.
            return " ".join(
                [
                    self._repr_rvalue(n.left),
                    self.BINOP[n.op.__class__.__name__],
                    self._repr_rvalue(n.right),
                ]
            )
        elif isinstance(n, Call):
            # TODO: this one is more complex: requires generation of temporary variables,
            # so we can cache the results, because it's likely that arguments are exprs
            # with side effects. ahhh, GCC's SAVE_EXPR... where are you
            return self._repr_call_base(n)
        elif isinstance(n, arg):
            return colored(f"{n.arg}={{{n.arg}}}", self.NAME_COLOR)
        else:
            raise NotImplementedError(f"{n} not supported")

    def _repr_func(self, n: AST, first=True) -> str:
        if isinstance(n, Name):
            return n.id if first else self._repr_rvalue(n)
        elif isinstance(n, Attribute):
            return self._repr_func(n.value, first=False) + f".{colored(n.attr, self.FUNC_COLOR)}"
        else:
            raise NotImplementedError(f"{n} not supported")

    def _repr_call_base(self, n: Call) -> str:
        return (
            f"{colored(self._repr_func(n.func), self.FUNC_COLOR)}("
            + ", ".join(self._repr_rvalue(arg) for arg in n.args)
            + ")"
        )

    def _repr_call(self, n: Call) -> stmt:
        return self._make_print([self._parse_fstring(self._repr_call_base(n))])

    def _parse_fstring(self, fstr: str) -> expr:
        parsed = ast.parse("f" + repr(fstr))
        assert (
            isinstance(parsed, Module)
            and isinstance(parsed.body, list)
            and len(parsed.body) == 1
            and isinstance(parsed.body[0], Expr)
        )
        return parsed.body[0].value

    def visit_Assign(self, n: Assign) -> Union[Assign, Tuple[Assign, Expr]]:
        assert len(n.targets) == 1 and isinstance(n.targets[0], Name)
        print_str = Call(
            Attribute(
                Constant(value=colored(f"{n.targets[0].id} = {{}}", "red")),
                attr="format",
                ctx=Load(),
            ),
            args=[Name(n.targets[0].id, Load())],
            keywords=[],
        )
        return (n, self._fix_location(self._make_print([print_str]), n))

    def visit_Return(self, n: Return):
        """
        * Decrement the depth before exiting. We have to save the returned value into a temporary,
          and only then decrement; otherwise, if the return value itself is a Call, we lose the
          depth.
        """
        var = Assign([Name(self._RETURN_VAR, Store())], n.value)
        n.value = Name(self._RETURN_VAR, Load())
        return self._fix_location_all(
            [
                var,
                self._make_print(
                    [
                        self._parse_fstring(
                            colored(f"return {{{self._RETURN_VAR}}}", self.RETURN_COLOR)
                        )
                    ],
                    "< ",
                ),
                self._decrement_depth(),
                n,
            ],
            n,
        )

    def visit_Module(self, n: Module) -> Module:
        """
        Adds:
        1. a global "__depth". TODO: make it a thread-local variable, instead of a global.
        2. "import sys"
        """
        self.generic_visit(n)
        # add it afterwards: so this variable doesn't get traced itself :)
        n.body.insert(
            0, self._fix_location(Assign([Name(self._DEPTH_VAR, Store())], Constant(0)), n.body[0])
        )

        # add the import
        n.body.insert(0, self._fix_location(Import([alias("sys")]), n.body[0]))
        return n

    def _decrement_depth(self) -> AugAssign:
        return AugAssign(Name(self._DEPTH_VAR, Store()), Sub(), Constant(self._INDENT))

    def _increment_depth(self) -> AugAssign:
        return AugAssign(Name(self._DEPTH_VAR, Store()), Add(), Constant(self._INDENT))

    def visit_Expr(self, n: Expr) -> Union[Expr, Tuple[stmt, Expr]]:
        value = n.value
        if isinstance(value, Call):
            return (self._fix_location(self._repr_call(value), n), n)
        return n

    def visit_FunctionDef(self, n: FunctionDef) -> FunctionDef:
        """
        * Adds a first statement "global" to mark our depth variable as such
        * Increment the depth on entry
        * Decrement the depth as the last statement (we also decrement before each Return)
        We'll do that on function entry/exit and not on each Call-site, because functions can begin
        executing without a Call at all (e.g: __getattr__).
        * Print my arguments
        """
        self.generic_visit(n)
        n.body.insert(0, self._fix_location(Global([self._DEPTH_VAR]), n))
        n.body.insert(1, self._fix_location(self._increment_depth(), n))
        rep = (
            f"{colored(n.name, self.FUNC_CALLED_COLOR)}("
            # TODO posonly, kwargs, ...
            + ", ".join(self._repr_rvalue(arg) for arg in n.args.args)
            + ")"
        )
        n.body.insert(2, self._fix_location(self._make_print([self._parse_fstring(rep)], "> "), n))
        n.body.append(self._fix_location(self._decrement_depth(), n))
        return n


def run_script(args):
    """
    based loosely on Lib/trace.py
    TODO: just do it with import hooks - then, we can affect all additional imported stuff, not
    just a single file.
    """
    sys.argv = [args.progname] + args.arguments
    sys.path[0] = os.path.dirname(args.progname)

    with open(args.progname, "rb") as fp:
        ast_obj = parse(fp.read(), args.progname)
        TraceTransformer().visit(ast_obj)
        if args.show:
            import astor  # type: ignore

            print(astor.to_source(ast_obj), file=sys.stderr)
        code = compile(ast_obj, args.progname, "exec")
    globs = {
        "__file__": args.progname,
        "__name__": "__main__",
    }
    exec(code, globs, globs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", action="store_true")
    parser.add_argument("progname", help="file to run as main program")
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help="arguments to the program")

    args = parser.parse_args()
    run_script(args)
