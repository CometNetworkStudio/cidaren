import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from runtime import serve

from cidaren.runner import run


def main():
    if sys.stdin.isatty() or "--cli" in sys.argv:
        from cli import main as cli_main
        return cli_main()
    serve(run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
