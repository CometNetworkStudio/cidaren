import argparse
import json

from cidaren.runner import run


def _kv(items):
    out = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"格式应为 k=v: {item}")
        key, value = item.split("=", 1)
        out[key] = value
    return out


def main():
    parser = argparse.ArgumentParser(prog="cidaren")
    parser.add_argument("--action", required=True)
    parser.add_argument("--param", action="append", default=[])
    parser.add_argument("--credential", action="append", default=[])
    args = parser.parse_args()
    for event in run(args.action, _kv(args.param), _kv(args.credential)):
        print(json.dumps(event, ensure_ascii=False))
    return 0
