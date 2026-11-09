#!/usr/bin/env python3
"""dockerw: project-scoped Docker wrapper for agents.

Allows a small set of docker commands, refuses privileged flags, host namespaces, the Docker socket
and any path (mount, compose file, build context) outside the project root, and pins the compose
project name so later cleanup can be scoped to this project's labels. Destructive commands are not
available here.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

READ_ONLY = {"ps", "images", "logs", "inspect", "version", "info"}
COMPOSE_SUBS = {"up", "down", "build", "ps", "logs", "config", "pull", "restart", "stop", "start",
                "exec", "run", "images", "top", "port"}
COMPOSE_VALUE_OPTS = {"-f", "--file", "-p", "--project-name", "--profile", "--env-file",
                      "--project-directory", "--ansi", "--progress", "--parallel"}
COMPOSE_PATH_OPTS = {"-f", "--file", "--env-file", "--project-directory"}
DENY_FLAGS = {"--privileged", "--cap-add", "--security-opt", "--device", "--pid", "--ipc", "--userns",
              "--cgroup-parent", "--uts", "-H", "--host", "--context"}


class Refused(Exception):
    pass


def project_root():
    env = os.environ.get("DOCKERW_ROOT")
    if env:
        return Path(env).resolve()
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             check=True).stdout.strip()
        return Path(out).resolve()
    except (OSError, subprocess.CalledProcessError):
        return Path.cwd().resolve()


def project_name(root):
    return re.sub(r"[^a-z0-9_-]", "", Path(root).name.lower()).lstrip("-_") or "project"


def inside(path, root, cwd):
    p = Path(os.path.expanduser(path))
    if not p.is_absolute():
        p = Path(cwd) / p
    p = p.resolve()
    return p == root or root in p.parents


def _host_path_reason(src, root, cwd):
    if not src:
        return None
    is_host_path = src.startswith(("/", "~", ".")) or "/" in src
    if is_host_path and not inside(src, root, cwd):
        return f"mount source outside the project: {src}"
    return None


def _volume_reason(spec, root, cwd):
    return _host_path_reason(spec.split(":")[0], root, cwd)


def _mount_reason(spec, root, cwd):
    fields = dict(kv.split("=", 1) for kv in spec.split(",") if "=" in kv)
    if fields.get("type", "volume") != "bind":
        return None
    src = fields.get("source") or fields.get("src") or ""
    if not src:
        return "bind mount without a source"
    return _host_path_reason(src, root, cwd)


def scan(tokens, root, cwd):
    """Raise Refused for dangerous flags, mounts and the Docker socket."""
    for i, tok in enumerate(tokens):
        if "docker.sock" in tok:
            raise Refused("the Docker socket cannot be used")
        name, _, val = tok.partition("=")
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if name in DENY_FLAGS:
            raise Refused(f"{name} is not allowed")
        if name in ("--network", "--net") and (val or nxt) == "host":
            raise Refused("host networking is not allowed")
        reason = None
        if name in ("-v", "--volume"):
            reason = _volume_reason(val or nxt, root, cwd)
        elif tok.startswith("-v") and not tok.startswith("--") and len(tok) > 2:
            reason = _volume_reason(tok[2:], root, cwd)
        elif name == "--mount":
            reason = _mount_reason(val or nxt, root, cwd)
        if reason:
            raise Refused(reason)


def _build(rest, root, cwd):
    scan(rest, root, cwd)
    i = 0
    while i < len(rest):
        name, eq, val = rest[i].partition("=")
        if name in ("-f", "--file"):
            if not eq:
                if i + 1 >= len(rest):
                    raise Refused(f"{name} needs a value")
                val = rest[i + 1]
                i += 1
            if not inside(val, root, cwd):
                raise Refused(f"Dockerfile outside the project: {val}")
        i += 1
    if not rest or rest[-1].startswith("-"):
        raise Refused("build needs a context path as the last argument")
    ctx = rest[-1]
    if "://" in ctx or ctx.startswith("git@") or not inside(ctx, root, cwd):
        raise Refused(f"build context outside the project: {ctx}")
    return ["build", *rest]


def _compose(args, root, cwd):
    name = project_name(root)
    has_project, sub, i = False, None, 0
    while i < len(args):
        tok = args[i]
        if not tok.startswith("-"):
            sub = tok
            break
        opt, eq, val = tok.partition("=")
        if opt in COMPOSE_VALUE_OPTS:
            if not eq:
                if i + 1 >= len(args):
                    raise Refused(f"{opt} needs a value")
                val = args[i + 1]
                i += 1
            if opt in COMPOSE_PATH_OPTS and not inside(val, root, cwd):
                raise Refused(f"{opt} points outside the project: {val}")
            if opt in ("-p", "--project-name"):
                if val != name:
                    raise Refused(f"project name is pinned to '{name}'")
                has_project = True
        i += 1
    if sub is None or sub not in COMPOSE_SUBS:
        raise Refused(f"compose subcommand not allowed: {sub or '(none)'}")
    after = args[i + 1:]
    if sub == "down" and any(t in ("-v", "--volumes", "--rmi") or t.startswith(("--rmi=", "--volumes="))
                             for t in after):
        raise Refused("down with volumes or images removes data; ask the user or use the labelled cleanup")
    scan(args, root, cwd)
    return ["compose", *([] if has_project else ["-p", name]), *args]


def _check(argv, root, cwd):
    if not argv:
        raise Refused("no command given")
    verb, rest = argv[0], argv[1:]
    if verb.startswith("-"):
        raise Refused(f"global option {verb} is not allowed; give a command first")
    if verb in READ_ONLY:
        scan(rest, root, cwd)
        return list(argv)
    if verb == "system":
        if rest != ["df"]:
            raise Refused("only 'system df' is allowed")
        return list(argv)
    if verb == "build":
        return _build(rest, root, cwd)
    if verb == "compose":
        return _compose(rest, root, cwd)
    raise Refused(f"'{verb}' is not allowed")


def check(argv, root, cwd):
    """Return (reason, final_argv). reason is None when the command is allowed."""
    try:
        return None, _check(list(argv), Path(root).resolve(), Path(cwd))
    except Refused as exc:
        return str(exc), None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    reason, final = check(argv, project_root(), Path.cwd())
    if reason:
        print(f"dockerw: refused: {reason}", file=sys.stderr)
        return 2
    docker = os.environ.get("DOCKERW_DOCKER", "docker")
    os.execvp(docker, [docker, *final])


if __name__ == "__main__":
    sys.exit(main())
