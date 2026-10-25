# shebang-sentry

Inspect Linux script launch headers and executable modes before shipping them, even
when you develop on Windows. The tool reads bytes and reports how the Linux shebang
would pass arguments. It never runs a script, changes permissions or rewrites a file.

Two common failures look correct in an editor: a CRLF header asks for an interpreter
whose name contains a carriage return, and `#!/usr/bin/env python3 -u` passes
`python3 -u` as **one** command name. The checker makes those details visible.

## Install and try

Python 3.11+ is required. Git is needed only for index inspection. There are no runtime
Python dependencies. Distribution is via GitHub source and release files, not PyPI.

```text
git clone https://github.com/KanadeK/shebang-sentry.git
cd shebang-sentry
python -m venv .venv
```

Activate with `source .venv/bin/activate` on Linux/macOS or `.venv\Scripts\Activate.ps1`
in PowerShell. Alternatively invoke that environment's Python by its full path.

```text
python -m pip install .
shebang-sentry examples/hello.sh --skip-mode
shebang-sentry examples/unsplit.sh --skip-mode --format json
shebang-sentry examples/hello.sh --source index
```

The first and third commands exit **0** in a fresh Git clone. The deliberately broken
second example exits **1** with `SB007`. No examples are executed. The source archive
has no Git index; use worktree/header mode there. `python -m shebang_sentry` is an
equivalent entry point.

## Select the evidence you need

- **Worktree (default):** reads up to 4097 header bytes from each explicit regular
  file. On Unix, checks whether any filesystem execute bit is set. On Windows, mode
  is reported as unknown (`SB105`), because POSIX execute bits cannot be inferred.
- **Git index (`--source index --repo path`):** reads both the staged blob and its
  staged `100755`/`100644` mode. Paths are relative to the repository root discovered
  from `--repo`. Unstaged edits do not affect this result. Unmerged paths, symlinks,
  submodules, untracked paths and directory inputs are refused. Lazy fetching is
  disabled, so missing partial-clone objects are errors rather than network access.
- **Header only (`--skip-mode`):** explicitly omits the executable-mode gate; the
  report retains `mode_checked: false` so this cannot be confused with a full check.

An index blob is limited to 16 MiB. Inspection of the body is out of scope. Neither
source follows symlink entries, and the tool does not change Git configuration or
the index. A concurrent working-file replacement is outside the trust boundary.

## Findings

| Code | Meaning |
|---|---|
| SB001–SB003 | Missing shebang, BOM, or preceding whitespace |
| SB004–SB005 | Literal CR or other control byte in the header |
| SB006 | Empty or relative interpreter path; this policy requires absolute paths |
| SB007 | Missing env command, or unsplit command name containing whitespace |
| SB008 | Selected source marks the script non-executable |
| SB101 | Header longer than 255 bytes; modern Linux may truncate it |
| SB102 | Direct interpreter receives one optional argument containing whitespace |
| SB104 | Complex env split strings, options or assignments need manual review |
| SB105 | Executable mode is unknown on this host/source |
| SB106 | Non-UTF-8 interpreter bytes are outside the supported analysis |
| SB107 | Quotes are literal in interpreter paths or plain env command names |

`SB001`–`SB008` are error-level policy findings. `SB101`–`SB107` are warnings.
Some unusual legal headers intentionally trigger this conservative policy. A report
of `blocked` means a policy error; `review` means a warning; `no-findings` means only
that the selected checks found no issue. **It is not proof that a script will run.**

`--fail-on warning` fails on any finding (default); `error` fails only on errors;
`none` reports without a findings-related failure. Exit **2** is invalid usage or an
input/read/Git error. Such errors are never converted to a clean report.

## Argument explanations and limits

The report's `kernel_argv` contains the interpreter, at most one optional argument,
and the placeholder `<script>`. Caller-supplied script arguments are not included.
CR/control, oversized and unsupported-encoding headers are not given an exact argv
prediction. The 255-byte policy targets Linux 5.1+; older kernels may allow less.

For `/usr/bin/env` and `/bin/env`, `env_command` describes a plain command name or a
simple `-S`, attached `-S...`, or `--split-string=...` form. Split-string support must
exist on the target host. Only plain ASCII words (letters, digits, `_ . / : + -`)
are split; quoting, backslash escapes, variable expansion, comments, env options and
assignments are explicitly left for review. This is not a full GNU env parser.

The checker does not validate interpreter existence, PATH resolution, interpreter
flags, Unix ACLs, `noexec` mounts, script syntax, body line endings, Windows launcher
behavior, shell fallback, container configuration or every operating system's
shebang behavior. Use it alongside a real target-platform smoke test.

JSON uses `schema_version: 1` and a `files` list with content/mode provenance, header
hex (first 256 bytes), argv explanation, notes and findings. `byte_offset` is zero
based within the file, not a display column. Terminal reports escape input-derived
paths/arguments. Reports can contain sensitive header paths; review before sharing.

## Development and removal

See [CONTRIBUTING.md](CONTRIBUTING.md). Tests create temporary Git repositories and
cover staged/worktree divergence, executable bits, unusual literal filenames,
unmerged entries, rejected links, size limits, malformed headers and CLI behavior.
Linux CI additionally invokes known synthetic scripts to check real `exec` behavior;
these integration tests skip on other systems and do not execute user input.

```text
python -m pip uninstall shebang-sentry
```

Deactivate and remove a dedicated `.venv` and clone if no longer needed. No persistent
application state is created.

## Related tools and references

[pre-commit-hooks](https://github.com/pre-commit/pre-commit-hooks) already provides
shebang/executable consistency hooks. [Ruff](https://docs.astral.sh/ruff/rules/shebang-leading-whitespace/)
checks Python shebang placement, and [pkg-bin-doctor](https://github.com/vjymisal0/pkg-bin-doctor)
targets npm bin metadata. This tool adds cross-language header-byte explanations and
an explicit staged content/mode workflow. The [Linux implementation](https://github.com/torvalds/linux/blob/master/fs/binfmt_script.c)
is a semantic reference; no kernel or competitor source code is included. Project
code is original and [MIT licensed](LICENSE).

## 中文说明

在发布 Linux 可执行脚本前检查 shebang 的真实字节、参数传递方式和执行位。Windows
开发者可用 `--source index` 同时读取暂存内容和 Git 执行位，避免操作系统权限显示
造成误判。工具不会执行或修改脚本。它能发现 BOM、CRLF、前置空白、错误的 env 参数
和缺少执行位等问题；复杂 env 语法会明确标记需要复核。通过检查不代表目标环境必然
可运行，仍需实际平台测试。安装、示例、退出码及卸载方式见上文。
