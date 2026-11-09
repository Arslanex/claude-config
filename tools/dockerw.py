#!/usr/bin/env python3
"""dockerw: project-scoped Docker wrapper for agents.

Allows a small set of docker commands, refuses privileged flags, host namespaces, the Docker socket
and any path (mount, compose file, build context) outside the project root, and pins the compose
project name so later cleanup can be scoped to this project's labels. Destructive commands are not
available here.
"""
import json
import os
import re
import socket
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


CONF = Path(__file__).resolve().parent / "dockerw.conf.json"
DOCKER_CANDIDATES = ("/usr/local/bin/docker", "/opt/homebrew/bin/docker",
                     "/Applications/Docker.app/Contents/Resources/bin/docker", "/usr/bin/docker")
SAFE_PATH = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/Applications/Docker.app/Contents/Resources/bin"


def _conf():
    """Settings come from a file next to this script (not writable by the sandbox), never from env vars."""
    try:
        data = json.loads(CONF.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _docker():
    configured = _conf().get("docker")
    if configured:
        return str(configured)
    for cand in DOCKER_CANDIDATES:
        if os.access(cand, os.X_OK):
            return cand
    raise SystemExit('dockerw: docker binary not found; set "docker" in dockerw.conf.json next to this script')


def _env():
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DOCKER_", "COMPOSE_", "BUILDKIT_", "BUILDX_"))}
    env["PATH"] = SAFE_PATH
    return env


def project_root():
    configured = _conf().get("root")
    if configured:
        return Path(configured).resolve()
    cwd = Path.cwd().resolve()
    for d in (cwd, *cwd.parents):
        if (d / ".git").exists():
            return d
    return cwd


def root_reason(root):
    root = Path(root).resolve()
    if root == Path(root.anchor) or root == Path.home().resolve():
        return f"project root is too broad ({root})"
    return None


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
    broad = root_reason(root)
    if broad:
        raise Refused(broad)
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


def _run(args, cwd=None):
    return subprocess.run([_docker(), *args], capture_output=True, text=True, cwd=cwd, env=_env())


def is_free(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def published_ports(config):
    """Sorted, de-duplicated (service, host port) pairs that a compose config publishes."""
    out = set()
    for svc, spec in (config.get("services") or {}).items():
        for p in (spec or {}).get("ports") or []:
            if isinstance(p, dict) and p.get("published"):
                out.add((svc, int(p["published"])))
    return sorted(out, key=lambda t: (t[1], t[0]))


def port_status(port, name):
    if is_free(port):
        return "free"
    r = _run(["ps", "--filter", f"publish={port}", "--format", '{{.Names}}|{{.Label "com.docker.compose.project"}}'])
    rows = [l.strip().split("|", 1) for l in r.stdout.splitlines() if l.strip()] if r.returncode == 0 else []
    if any(len(row) == 2 and row[1] == name for row in rows):
        return "own"
    return "other-container" if rows else "foreign-process"


def suggest_port(port, taken):
    for p in range(port + 1, min(port + 200, 65535) + 1):
        if p not in taken and is_free(p):
            return p
    return None


def cmd_ports(args):
    root = project_root()
    name = project_name(root)
    r = _run(["compose", "-p", name, "config", "--format", "json"], cwd=root)
    try:
        if r.returncode != 0:
            raise ValueError(r.stderr.strip()[:200] or "docker compose config failed")
        config = json.loads(r.stdout)
    except ValueError as exc:
        print(f"dockerw: could not read the compose config: {exc}", file=sys.stderr)
        return 1
    ports = published_ports(config)
    taken = {p for _, p in ports}
    for svc, port in ports:
        status = port_status(port, name)
        line = f"PORT {port} {svc} {status}"
        if status in ("other-container", "foreign-process"):
            s = suggest_port(port, taken)
            line += f" suggest={s}" if s else " suggest=none"
            if s:
                taken.add(s)
        print(line)
    if not ports:
        print("PORTS none")
    return 0


def cmd_clean(args):
    if any(a not in ("--apply", "--include-dangling") for a in args):
        print("dockerw: clean accepts only --apply and --include-dangling", file=sys.stderr)
        return 2
    apply = "--apply" in args
    name = project_name(project_root())
    steps = [(f"stopped containers of project {name}",
              ["container", "prune", "-f", "--filter", f"label=com.docker.compose.project={name}"])]
    if "--include-dangling" in args:
        steps.append(("dangling images (unreferenced, not project-labelled)", ["image", "prune", "-f"]))
    rc = 0
    for label, cmd in steps:
        if not apply:
            print(f"would run: {label}")
            continue
        r = _run(cmd)
        if r.returncode == 0:
            print(f"{label}: ok")
        else:
            rc = 1
            print(f"{label}: failed: {r.stderr.strip()[:200]}")
    if not apply:
        print("dry run: nothing removed (use --apply)")
    return rc


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    broad = root_reason(project_root())
    if broad:
        print(f"dockerw: refused: {broad}", file=sys.stderr)
        return 2
    if argv[:1] == ["ports"]:
        return cmd_ports(argv[1:])
    if argv[:1] == ["clean"]:
        return cmd_clean(argv[1:])
    reason, final = check(argv, project_root(), Path.cwd())
    if reason:
        print(f"dockerw: refused: {reason}", file=sys.stderr)
        return 2
    docker = _docker()
    os.execve(docker, [docker, *final], _env())


if __name__ == "__main__":
    sys.exit(main())
