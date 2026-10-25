"""Conservative, byte-oriented preflight for direct Linux script launch."""

import re

SIMPLE_WORD = re.compile(r"[A-Za-z0-9_./:+-]+\Z")


def inspect_header(data, path="<input>", executable=None, mode_source="unknown", check_mode=True):
    """Inspect a header prefix. Does not resolve interpreters or execute anything.

    `data` need only include the first 4097 bytes. `kernel_argv` is the Linux
    shebang argument shape for supported headers, excluding caller-supplied arguments.
    """
    findings = []
    notes = []
    first = data.split(b"\n", 1)[0]
    result = {
        "path": path,
        "mode_source": mode_source,
        "executable": executable,
        "mode_checked": check_mode,
        "header_hex": first[:256].hex(),
        "kernel_argv": None,
        "env_command": None,
        "findings": findings,
        "notes": notes,
    }

    def add(code, message, offset=0, severity="error"):
        findings.append(
            {"code": code, "severity": severity, "byte_offset": offset, "message": message}
        )

    if check_mode:
        if executable is False:
            add("SB008", "Script is not marked executable in the selected mode source.")
        elif executable is None:
            add(
                "SB105",
                "Executable mode is unknown; use the Git index or explicitly skip mode checks.",
                severity="warning",
            )
    if data.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")):
        add("SB002", "A byte-order mark precedes the shebang; #! must be bytes 0 and 1.")
    elif not data.startswith(b"#!"):
        if data.lstrip(b" \t\r\n").startswith(b"#!"):
            add("SB003", "Whitespace precedes the shebang; Linux will not recognize it.")
        else:
            add("SB001", "No shebang at byte zero; this is not a recognized Linux script header.")
    else:
        if b"\r" in first:
            add(
                "SB004",
                "CR is literal in the Linux shebang, including a CRLF line ending.",
                first.index(b"\r"),
            )
        control = next(
            (i for i, value in enumerate(first) if (value < 32 and value != 9) or value == 127),
            None,
        )
        if control is not None and first[control] != 13:
            add(
                "SB005",
                "Control byte in the shebang requires correction or manual review.",
                control,
            )
        if len(first) > 255:
            add(
                "SB101",
                "Shebang exceeds 255 bytes; Linux 5.1+ may truncate it. Older kernels allow less.",
                255,
                "warning",
            )
        # CR/control/oversize input is intentionally not presented as an exact launch prediction.
        if not any(item["code"] in {"SB004", "SB005", "SB101"} for item in findings):
            try:
                line = first[2:].strip(b" \t").decode("utf-8")
            except UnicodeDecodeError:
                add(
                    "SB106",
                    "Non-UTF-8 interpreter bytes are outside the supported inspection scope.",
                    2,
                    "warning",
                )
            else:
                match = re.match(r"([^ \t]+)(?:[ \t]+(.*))?\Z", line)
                if not match or not match.group(1).startswith("/"):
                    add(
                        "SB006",
                        "A nonempty absolute interpreter path is required by this policy.",
                        2,
                    )
                else:
                    interpreter, argument = match.groups()
                    result["kernel_argv"] = (
                        [interpreter] + ([argument] if argument else []) + ["<script>"]
                    )
                    if interpreter in {"/usr/bin/env", "/bin/env"}:
                        inspect_env(argument, result, add)
                    elif argument and re.search(r"[ \t]", argument):
                        add(
                            "SB102",
                            "Linux passes the interpreter's remaining text as ONE argument.",
                            2 + first[2:].find(argument.encode()),
                            "warning",
                        )
                    if '"' in interpreter or "'" in interpreter:
                        add(
                            "SB107",
                            "Quotes in an interpreter path are literal; Linux does not unquote it.",
                            2,
                            "warning",
                        )
    result["assessment"] = (
        "blocked"
        if any(x["severity"] == "error" for x in findings)
        else ("review" if findings else "no-findings")
    )
    return result


def inspect_env(argument, result, add):
    if not argument:
        add("SB007", "env has no interpreter name; the script path would become its command.")
        return
    split = None
    if argument.startswith("-S"):
        split = argument[2:].lstrip(" \t")
    elif argument.startswith("--split-string="):
        split = argument[len("--split-string=") :]
    if split is not None:
        result["notes"].append("Split-string requires an env implementation with -S support.")
        words = re.split(r"[ \t]+", split) if split else []
        if not words:
            add("SB007", "env split-string is empty.")
        elif all(SIMPLE_WORD.fullmatch(word) for word in words) and not words[0].startswith("-"):
            result["env_command"] = words
        else:
            add(
                "SB104",
                "Complex env split-string needs review; only plain words are interpreted.",
                severity="warning",
            )
    elif argument.startswith("-") or "=" in argument:
        add(
            "SB104",
            "env options/assignments need manual review; no command is inferred.",
            severity="warning",
        )
    elif re.search(r"[ \t]", argument):
        add(
            "SB007",
            "env receives one name containing whitespace; use supported -S syntax for arguments.",
        )
    else:
        result["env_command"] = [argument]
        if "'" in argument or '"' in argument:
            add(
                "SB107",
                "Quotes in a plain env command name are literal, not shell quoting.",
                severity="warning",
            )
