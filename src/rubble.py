"""
Rubble CLI Entry Point
Usage:
    python -m src.rubble <file.rbl>
    python -m src.rubble --repl
"""

import sys
import os


def run_file(path: str):
    """Lex, parse, and execute a .rbl source file."""
    if not os.path.exists(path):
        print(f"[Rubble] File not found: {path!r}", file=sys.stderr)
        sys.exit(1)

    with open(path, 'r', encoding='utf-8') as f:
        source = f.read()

    _run_source(source, source_name=path)


def run_repl():
    """Start an interactive Rubble REPL session."""
    from .lexer import Lexer, LexerError
    from .parser import Parser, ParseError
    from .interpreter import Interpreter, RubbleWreck, RuntimeError_

    interp = Interpreter()
    print("Rubble REPL — type 'exit' or Ctrl-C to quit\n")

    while True:
        try:
            line = input(">> ")
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if line.strip() in ("exit", "quit"):
            break
        if not line.strip():
            continue

        try:
            from .lexer import Lexer
            from .parser import Parser
            from .ast_nodes import Program
            tokens = Lexer(line).tokenize()
            ast = Parser(tokens).parse()
            interp.execute(ast)
        except LexerError as e:
            print(e, file=sys.stderr)
        except ParseError as e:
            print(e, file=sys.stderr)
        except RubbleWreck as e:
            print(e, file=sys.stderr)
        except RuntimeError_ as e:
            print(e, file=sys.stderr)
        except Exception as e:
            print(f"[Unexpected Error] {e}", file=sys.stderr)


def _run_source(source: str, source_name: str = "<string>"):
    from .lexer import Lexer, LexerError
    from .parser import Parser, ParseError
    from .interpreter import Interpreter, RubbleWreck, RuntimeError_

    try:
        tokens = Lexer(source).tokenize()
    except LexerError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    interp = Interpreter()
    try:
        interp.execute(ast)
    except RubbleWreck as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except RuntimeError_ as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except SystemExit:
        raise   # Let machinery.halt() propagate
    except Exception as e:
        print(f"[Internal Error] {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    args = sys.argv[1:]

    if not args:
        print("Usage: rubble <file.rbl>  |  rubble --repl", file=sys.stderr)
        sys.exit(1)

    if args[0] == '--repl':
        run_repl()
    else:
        run_file(args[0])


if __name__ == '__main__':
    main()
