"""File I/O tools: read, write, edit, glob, grep."""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

from claude_agent_sdk import tool


@tool(
    "read_file",
    "Read a file from disk. Returns numbered lines.",
    {"path": str, "offset": int, "limit": int},
)
async def read_file(args: dict) -> dict:
    path: str = args["path"]
    offset: int = args.get("offset", 0)
    limit: int = args.get("limit", 2000)
    try:
        with open(path) as f:
            lines = f.readlines()
        selected = lines[offset : offset + limit]
        numbered = "".join(f"{i + offset + 1}\t{line}" for i, line in enumerate(selected))
        return {"content": [{"type": "text", "text": numbered or "(empty file)"}]}
    except OSError as e:
        return {"content": [{"type": "text", "text": f"Error reading {path}: {e}"}]}


@tool(
    "write_file",
    "Write content to a file, creating it if it doesn't exist.",
    {"path": str, "content": str},
)
async def write_file(args: dict) -> dict:
    path: str = args["path"]
    content: str = args["content"]
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return {"content": [{"type": "text", "text": f"Wrote {len(content)} bytes to {path}"}]}
    except OSError as e:
        return {"content": [{"type": "text", "text": f"Error writing {path}: {e}"}]}


@tool(
    "edit_file",
    "Replace an exact string in a file. old_string must appear exactly once.",
    {"path": str, "old_string": str, "new_string": str},
)
async def edit_file(args: dict) -> dict:
    path: str = args["path"]
    old_string: str = args["old_string"]
    new_string: str = args["new_string"]
    try:
        text = Path(path).read_text()
        count = text.count(old_string)
        if count == 0:
            return {"content": [{"type": "text", "text": f"old_string not found in {path}"}]}
        if count > 1:
            return {"content": [{"type": "text", "text": f"old_string found {count} times — must be unique"}]}
        new_text = text.replace(old_string, new_string, 1)
        Path(path).write_text(new_text)
        return {"content": [{"type": "text", "text": f"Edited {path} successfully"}]}
    except OSError as e:
        return {"content": [{"type": "text", "text": f"Error editing {path}: {e}"}]}


@tool(
    "glob_files",
    "Find files matching a glob pattern. Returns sorted list of paths.",
    {"pattern": str, "path": str},
)
async def glob_files(args: dict) -> dict:
    pattern: str = args["pattern"]
    path: str = args.get("path", ".")
    try:
        base = Path(path)
        matches = sorted(str(p) for p in base.glob(pattern))
        result = "\n".join(matches[:500]) if matches else "(no matches)"
        return {"content": [{"type": "text", "text": result}]}
    except OSError as e:
        return {"content": [{"type": "text", "text": f"Error: {e}"}]}


@tool(
    "grep_files",
    "Search file contents for a regex pattern. Returns matching lines with file and line number.",
    {"pattern": str, "path": str, "glob_filter": str},
)
async def grep_files(args: dict) -> dict:
    pattern_str: str = args["pattern"]
    path: str = args.get("path", ".")
    glob_filter: str = args.get("glob_filter", "*")
    try:
        regex = re.compile(pattern_str)
    except re.error as e:
        return {"content": [{"type": "text", "text": f"Invalid regex: {e}"}]}

    results = []
    base = Path(path)
    files = base.rglob(glob_filter) if "**" in glob_filter or "/" in glob_filter else base.glob(glob_filter)

    for filepath in files:
        if not filepath.is_file():
            continue
        try:
            with open(filepath) as f:
                for i, line in enumerate(f, 1):
                    if regex.search(line):
                        results.append(f"{filepath}:{i}: {line.rstrip()}")
                        if len(results) >= 200:
                            break
        except (OSError, UnicodeDecodeError):
            continue
        if len(results) >= 200:
            break

    text = "\n".join(results) if results else "(no matches)"
    return {"content": [{"type": "text", "text": text}]}
