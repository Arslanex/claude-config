#!/usr/bin/env python3
"""dockerw: project-scoped Docker wrapper for agents.

Allows a small set of docker commands, refuses privileged flags, host namespaces, the Docker socket
and any path (mount, compose file, build context) outside the project root, and pins the compose
project name so later cleanup can be scoped to this project's labels. Destructive commands are not
available here.
"""
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

READ_ONLY = {"ps", "images", "version", "info"}
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


# DOCKERW_LOG and FAKE only carry paths for the fake docker binary in the test suite.
ENV_ALLOW = {"HOME", "USER", "LOGNAME", "LANG", "TERM", "TMPDIR", "TZ", "DOCKERW_LOG", "FAKE"}


def _env():
    """Allow-list: ambient credentials (SSH agent, cloud and token variables) never reach docker."""
    env = {k: v for k, v in os.environ.items() if k in ENV_ALLOW or k.startswith("LC_")}
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
    allowed = _conf().get("allowed_roots")
    if allowed:
        bases = [Path(a).expanduser().resolve() for a in allowed]
        if root in bases:
            return f"project root {root} is an allowed root itself; use a directory below it"
        if not any(b in root.parents for b in bases):
            return f"project root {root} is not under an allowed root"
    return None


def project_name(root):
    """Sanitised basename plus a short hash of the full path, so same-named directories get different projects."""
    base = re.sub(r"[^a-z0-9_-]", "", Path(root).name.lower()).lstrip("-_") or "project"
    return f"{base}-{hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:8]}"


def inside(path, root, cwd):
    p = Path(os.path.expanduser(path))
    if not p.is_absolute():
        p = Path(cwd) / p
    p = p.resolve()
    return p == root or root in p.parents


def _resolve(path, cwd):
    p = Path(os.path.expanduser(path))
    return (p if p.is_absolute() else Path(cwd) / p).resolve()


def _host_path_reason(src, root, cwd):
    if not src:
        return None
    is_host_path = src.startswith(("/", "~", ".")) or "/" in src
    if is_host_path:
        return None if inside(src, root, cwd) else f"mount source outside the project: {src}"
    prefix = project_name(root) + "_"
    if not src.startswith(prefix):
        return f"named volume must belong to this project (start with {prefix}): {src}"
    return None


def _volume_reason(spec, root, cwd):
    return _host_path_reason(spec.split(":")[0], root, cwd)


def _mount_reason(spec, root, cwd):
    # Like docker: keys are case-insensitive, type is lower-cased, and the last of source/src wins.
    typ, src = "volume", ""
    for kv in spec.split(","):
        key, eq, value = kv.partition("=")
        if not eq:
            continue
        key = key.strip().lower()
        if key == "type":
            typ = value.strip().lower()
        elif key in ("source", "src"):
            src = value
    if typ == "bind":
        if not src:
            return "bind mount without a source"
        return _host_path_reason(src, root, cwd)
    if typ == "volume" and src:
        return _host_path_reason(src, root, cwd)
    return None


def scan(tokens, root, cwd):
    """Raise Refused for dangerous flags, mounts and the Docker socket."""
    for i, tok in enumerate(tokens):
        if "docker.sock" in tok:
            raise Refused("the Docker socket cannot be used")
        if tok.startswith("-") and not tok.startswith("--") and len(tok) > 2:
            raise Refused(f"combined or attached short option {tok!r} is not allowed; write each option separately")
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


BUILD_VALUE_FLAGS = {"-t", "--tag", "-f", "--file", "--build-arg", "--target", "--label", "--progress", "--platform"}
BUILD_BOOL_FLAGS = {"--no-cache", "--pull", "-q", "--quiet"}


def _build(rest, root, cwd):
    scan(rest, root, cwd)
    positional, i = [], 0
    while i < len(rest):
        tok = rest[i]
        if not tok.startswith("-"):
            positional.append(tok)
            i += 1
            continue
        name, eq, val = tok.partition("=")
        if name in BUILD_BOOL_FLAGS and not eq:
            i += 1
            continue
        if name in BUILD_VALUE_FLAGS:
            if not eq:
                if i + 1 >= len(rest):
                    raise Refused(f"{name} needs a value")
                val = rest[i + 1]
                i += 1
            if name in ("-f", "--file") and not inside(val, root, cwd):
                raise Refused(f"Dockerfile outside the project: {val}")
            i += 1
            continue
        raise Refused(f"build option not allowed: {tok}")
    if len(positional) != 1:
        raise Refused("build needs exactly one context path")
    ctx = positional[0]
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
    for t in after:
        opt = t.partition("=")[0]
        if (opt in ("--file", "--env-file", "--project-directory", "--project-name")
                or (opt == "-f" and sub != "logs") or (opt == "-p" and sub != "run")):
            raise Refused(f"{opt} must come before the compose subcommand")
    if sub == "down" and any(t in ("-v", "--volumes", "--rmi") or t.startswith(("--rmi=", "--volumes="))
                             for t in after):
        raise Refused("down with volumes or images removes data; ask the user or use the labelled cleanup")
    if sub == "build":
        for t in after:
            if t.partition("=")[0] in ("--ssh", "--push"):
                raise Refused(f"{t.partition('=')[0]} is not allowed: build must not use the SSH agent or push images")
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
                try:
                    out.add((svc, int(p["published"])))
                except (TypeError, ValueError):
                    continue
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
            raise ValueError("docker compose config failed")
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


GATED = {"up", "run", "build", "start", "restart", "down"}
ENV_CHECKED = {"config"}  # printing the config reads env_files, so they are checked, but the full policy does not apply
KEEP_OPTS = {"-p", "--project-name", "--profile", "--ansi", "--progress", "--parallel"}


def _split_compose(args):
    """(options, subcommand, rest) of the arguments after 'compose'; options are (token, value-or-None)."""
    opts, i = [], 0
    while i < len(args) and args[i].startswith("-"):
        tok = args[i]
        opt, eq, _ = tok.partition("=")
        if opt in COMPOSE_VALUE_OPTS and not eq:
            opts.append((tok, args[i + 1] if i + 1 < len(args) else None))
            i += 2
        else:
            opts.append((tok, None))
            i += 1
    sub = args[i] if i < len(args) else None
    return opts, sub, args[i + 1:]


def _flat(opts):
    return [t for tok, val in opts for t in ((tok,) if val is None else (tok, val))]


def _config(args, cwd):
    r = _run(args, cwd=cwd)
    if r.returncode != 0:
        raise Refused("could not resolve the compose config: " + (r.stderr.strip()[:200] or "docker compose config failed"))
    try:
        cfg = json.loads(r.stdout)
    except ValueError:
        raise Refused("could not resolve the compose config: output is not JSON")
    if not isinstance(cfg, dict):
        raise Refused("could not resolve the compose config: unexpected output")
    return cfg


def _env_file_paths(cfg):
    for svc, spec in (cfg.get("services") or {}).items():
        files = (spec or {}).get("env_file") or []
        if isinstance(files, (str, dict)):
            files = [files]
        for f in files:
            path = str(f.get("path") or "") if isinstance(f, dict) else str(f)
            if path:
                yield svc, path


def validate_env_files(cfg, root, cwd):
    root = Path(root).resolve()
    for svc, path in _env_file_paths(cfg):
        if not inside(path, root, cwd):
            raise Refused(f"service {svc}: env_file outside the project: {path}")


def env_file_identity(cfg, cwd):
    """What each env_file points at right now: resolved path plus device and inode (None if missing)."""
    ident = []
    for _, path in _env_file_paths(cfg):
        p = Path(os.path.expanduser(path))
        p = (p if p.is_absolute() else Path(cwd) / p).resolve()
        try:
            st = p.stat()
            ident.append((str(p), st.st_dev, st.st_ino))
        except OSError:
            ident.append((str(p), None, None))
    return ident


def _validate_build(where, build, root, cwd):
    ctx = str(build.get("context") or ".")
    if "://" in ctx or ctx.startswith("git@") or not inside(ctx, root, cwd):
        raise Refused(f"{where}: build context outside the project: {ctx}")
    dockerfile = str(build.get("dockerfile") or "")
    if dockerfile and not inside(dockerfile, root, _resolve(ctx, cwd)):
        raise Refused(f"{where}: Dockerfile outside the project: {dockerfile}")
    for key in ("ssh", "entitlements", "cache_to", "privileged"):
        if build.get(key):
            raise Refused(f"{where}: build.{key} is not allowed")
    if build.get("network") == "host":
        raise Refused(f"{where}: build.network host is not allowed")
    for entry in build.get("cache_from") or []:
        if "type=local" in str(entry):
            raise Refused(f"{where}: local build cache is not allowed")
    for key, value in (build.get("additional_contexts") or {}).items():
        v = str(value)
        if v.startswith("docker-image://"):
            continue
        if "://" in v or not inside(v, root, cwd):
            raise Refused(f"{where}: additional build context outside the project: {v}")


def validate_config(cfg, root, cwd):
    """Raise Refused when a resolved compose config asks for more than the project may have."""
    root = Path(root).resolve()
    prefix = project_name(root) + "_"
    for svc, spec in (cfg.get("services") or {}).items():
        spec = spec or {}
        where = f"service {svc}"
        if spec.get("privileged"):
            raise Refused(f"{where}: privileged is not allowed")
        for key in ("cap_add", "devices", "security_opt", "device_cgroup_rules", "pid", "ipc", "uts",
                    "userns_mode", "cgroup", "cgroup_parent", "provider"):
            if spec.get(key):
                raise Refused(f"{where}: {key} is not allowed")
        mode = str(spec.get("network_mode") or "")
        if mode == "host" or mode.startswith("container:"):
            raise Refused(f"{where}: network_mode {mode} is not allowed")
        if any(str(v).startswith("container:") for v in spec.get("volumes_from") or []):
            raise Refused(f"{where}: volumes_from a container is not allowed")
        for v in spec.get("volumes") or []:
            if isinstance(v, str):
                reason = _volume_reason(v, root, cwd)
                if reason:
                    raise Refused(f"{where}: {reason}")
            elif isinstance(v, dict) and v.get("type") == "bind":
                src = str(v.get("source") or "")
                if not src or "docker.sock" in src or not inside(src, root, cwd):
                    raise Refused(f"{where}: bind mount source outside the project: {src or '(empty)'}")
        if isinstance(spec.get("build"), dict):
            _validate_build(where, spec["build"], root, cwd)
    for key, vol in (cfg.get("volumes") or {}).items():
        vol = vol or {}
        vname = str(vol.get("name") or key)
        if vname != prefix + key:
            raise Refused(f"volume {key}: name must be exactly {prefix}{key} (got {vname})")
        if (vol.get("driver") or "local") != "local":
            raise Refused(f"volume {key}: only the local driver is allowed")
        device = (vol.get("driver_opts") or {}).get("device")
        if device and not inside(str(device), root, cwd):
            raise Refused(f"volume {key}: device outside the project: {device}")
    for key, net in (cfg.get("networks") or {}).items():
        nname = str((net or {}).get("name") or key)
        if not nname.startswith(prefix):
            raise Refused(f"network {key}: name must start with {prefix} (got {nname})")
    for kind in ("secrets", "configs"):
        for key, item in (cfg.get(kind) or {}).items():
            item = item or {}
            if item.get("file") and not inside(str(item["file"]), root, cwd):
                raise Refused(f"{kind} {key}: file outside the project: {item['file']}")
            if item.get("environment"):
                raise Refused(f"{kind} {key}: reading a host environment variable is not allowed")


def gate_compose(final, root, cwd):
    """Return (reason, argv, stdin). Commands that start containers run the validated config from stdin."""
    opts, sub, rest = _split_compose(final[1:])
    if sub not in GATED | ENV_CHECKED:
        return None, final, None
    try:
        everything = _flat(opts)
        unresolved = _config(["compose", *everything, "config", "--no-env-resolution", "--format", "json"], cwd)
        validate_env_files(unresolved, root, cwd)
        before = env_file_identity(unresolved, cwd)
        cfg = _config(["compose", *everything, "config", "--format", "json"], cwd)
        validate_env_files(unresolved, root, cwd)
        if env_file_identity(unresolved, cwd) != before:
            raise Refused("an env_file changed while the compose config was being resolved")
        if sub in GATED:
            validate_config(cfg, root, cwd)
    except Refused as exc:
        return str(exc), None, None
    keep = _flat([(tok, val) for tok, val in opts if tok.partition("=")[0] in KEEP_OPTS])
    return None, ["compose", *keep, "-f", "-", sub, *rest], json.dumps(cfg)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = project_root()
    broad = root_reason(root)
    if broad:
        print(f"dockerw: refused: {broad}", file=sys.stderr)
        return 2
    if argv[:1] == ["ports"]:
        return cmd_ports(argv[1:])
    if argv[:1] == ["clean"]:
        return cmd_clean(argv[1:])
    reason, final = check(argv, root, Path.cwd())
    stdin_data = None
    if not reason and final and final[0] == "compose":
        reason, final, stdin_data = gate_compose(final, root, Path.cwd())
    if reason:
        print(f"dockerw: refused: {reason}", file=sys.stderr)
        return 2
    docker = _docker()
    if stdin_data is None:
        os.execve(docker, [docker, *final], _env())
    return subprocess.run([docker, *final], input=stdin_data, text=True, env=_env()).returncode


if __name__ == "__main__":
    sys.exit(main())
