"""Worktree and index readers. Git index content and mode always come from one entry."""

import os
import stat
import subprocess
from pathlib import Path

MAX_BLOB = 16 * 1024 * 1024
HEADER_BYTES = 4097


def worktree(path):
    file = Path(path)
    info = file.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"Expected a regular file, not a symlink or special file: {path!r}")
    with file.open("rb") as stream:
        data = stream.read(HEADER_BYTES)
    executable = None if os.name == "nt" else bool(info.st_mode & 0o111)
    return data, executable, "filesystem"


def git(repo, *args):
    env = os.environ.copy()
    env.update(GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    proc = subprocess.run(
        ["git", "--literal-pathspecs", "-C", str(repo), *args],
        capture_output=True,
        timeout=20,
        env=env,
    )
    if proc.returncode:
        raise ValueError(
            "Git read failed: " + proc.stderr.decode("utf-8", "backslashreplace").strip()
        )
    return proc.stdout


class Index:
    def __init__(self, repo):
        self.root = Path(os.fsdecode(git(repo, "rev-parse", "--show-toplevel").rstrip(b"\r\n")))

    def read(self, path):
        # Paths are relative to --repo (not the caller's directory). Do not resolve
        # symlinks: index records are names, not current filesystem targets.
        file = Path(os.path.abspath(self.root / path))
        try:
            name = file.relative_to(self.root).as_posix()
        except ValueError as exc:
            raise ValueError("Index path is outside the repository") from exc
        records = git(self.root, "ls-files", "--stage", "-z", "--", name).split(b"\0")
        records = [record for record in records if record]
        if not records:
            raise ValueError(f"Path is not in the Git index: {name!r}")
        if len(records) != 1:
            raise ValueError(f"Unmerged or non-file index path: {name!r}")
        metadata, found_name = records[0].split(b"\t", 1)
        mode, blob, stage = metadata.split()
        if stage != b"0" or os.fsdecode(found_name) != name:
            raise ValueError(f"Unmerged or non-file index path: {name!r}")
        if mode not in (b"100644", b"100755"):
            raise ValueError(
                f"Index entry must be a regular file, not a symlink/submodule: {name!r}"
            )
        size = int(git(self.root, "cat-file", "-s", blob.decode("ascii")))
        if size > MAX_BLOB:
            raise ValueError(f"Index blob exceeds {MAX_BLOB} bytes: {name!r}")
        data = git(self.root, "cat-file", "blob", blob.decode("ascii"))
        return data[:HEADER_BYTES], mode == b"100755", "git-index"
