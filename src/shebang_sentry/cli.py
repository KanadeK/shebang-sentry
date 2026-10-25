import argparse
import json
import subprocess
import sys

from . import __version__
from .core import inspect_header
from .sources import Index, worktree


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Inspect Linux script launch headers without executing scripts."
    )
    parser.add_argument(
        "files", nargs="+", help="Explicit scripts; index paths are relative to the repository root"
    )
    parser.add_argument("--source", choices=("worktree", "index"), default="worktree")
    parser.add_argument("--repo", default=".", help="Git repository for --source index")
    parser.add_argument(
        "--skip-mode", action="store_true", help="Explicitly check header bytes only"
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--fail-on", choices=("warning", "error", "none"), default="warning")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        index = Index(args.repo) if args.source == "index" else None
        reports = []
        for path in args.files:
            data, executable, source = index.read(path) if index else worktree(path)
            report = inspect_header(data, path, executable, source, not args.skip_mode)
            report["content_source"] = args.source
            reports.append(report)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print("shebang-sentry: " + ascii(str(exc)), file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps({"schema_version": 1, "files": reports}, ensure_ascii=True, indent=2))
    else:
        for report in reports:
            print(f"{ascii(report['path'])}: {report['assessment']} ({report['content_source']})")
            for item in report["findings"]:
                print(
                    f"  byte {item['byte_offset']}: {item['severity']} "
                    f"{item['code']} {item['message']}"
                )
            if report["kernel_argv"] is not None:
                print("  kernel argv: " + json.dumps(report["kernel_argv"], ensure_ascii=True))
            if report["env_command"] is not None:
                print("  env command: " + json.dumps(report["env_command"], ensure_ascii=True))
            for note in report["notes"]:
                print("  note: " + note)
    findings = [item for report in reports for item in report["findings"]]
    return int(
        any(
            args.fail_on == "warning" or (args.fail_on == "error" and x["severity"] == "error")
            for x in findings
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
