#!/usr/bin/env python3
"""
PreToolUse (Bash): asks only for a suspicious new dependency (supply chain).

An ordinary registry install passes without a prompt. It asks when a package
name is one edit away from a popular package (typosquatting) or when the
source is not the default registry (URL, git, custom index, archive).
Restores from a lock file pass. On any error it stays silent.
"""
import json
import re
import sys

POPULAR = set("""
requests urllib3 numpy pandas django flask fastapi uvicorn pydantic sqlalchemy alembic httpx httpcore
aiohttp anyio sniffio boto3 botocore pytest setuptools wheel pip six python-dateutil pyyaml jinja2 click
rich typer celery redis psycopg psycopg2 psycopg2-binary asyncpg aiosqlite cryptography pillow scipy
matplotlib scikit-learn tensorflow torch transformers openai anthropic beautifulsoup4 lxml selenium
playwright mypy ruff black isort coverage tqdm colorama attrs certifi idna charset-normalizer packaging
markupsafe werkzeug gunicorn starlette structlog orjson ujson simplejson pyjwt bcrypt passlib paramiko
docker kubernetes yt-dlp defusedxml tzdata python-multipart tenacity pytz arrow pendulum
react react-dom preact next vue svelte express lodash axios typescript vite vitest jest eslint prettier webpack
zod tailwindcss postcss autoprefixer chalk commander dotenv moment dayjs uuid nanoid socket.io mongoose
prisma redux rxjs jquery cross-env nodemon ts-node tsx esbuild rollup puppeteer cypress electron colors color
debug request async yargs minimist glob rimraf mkdirp fs-extra body-parser cors jsonwebtoken pg mysql
mysql2 sqlite3 ioredis htmx.org serde tokio clap anyhow rand reqwest
""".split())
# Flags that pick a source other than the default registry.
SOURCE_FLAGS = {"-i", "--index", "--index-url", "--extra-index-url", "--default-index", "-f",
                "--find-links", "--registry", "--git", "--tap", "--source"}
# Flags whose next token is a value, not a package.
VALUE_FLAGS = {"-r", "--requirement", "-c", "--constraint", "-e", "--editable", "--group", "--optional",
               "--extra", "-p", "--python", "--package", "--directory", "--project", "--prefix",
               "--target", "-t", "--branch", "--tag", "--rev", "--features", "--version"}


def install_args(t):
    """
    Returns the arguments after the install verb, or None when it is not an install.
    """
    if not t:
        return None
    if t[0] == "uv" and len(t) > 1:
        if t[1] == "add":
            return t[2:]
        if t[1:3] == ["pip", "install"]:
            return t[3:]
        return None
    if t[0] in ("pip", "pip3") and t[1:2] == ["install"]:
        return t[2:]
    if t[0] in ("python", "python3") and t[1:4] == ["-m", "pip", "install"]:
        return t[4:]
    if t[0] in ("npm", "pnpm", "bun") and len(t) > 1 and t[1] in ("add", "install", "i"):
        return t[2:]
    if t[0] == "yarn" and t[1:2] == ["add"]:
        return t[2:]
    if t[0] in ("cargo", "brew", "gem") and len(t) > 1 and t[1] in ("add", "install"):
        return t[2:]
    if t[0] == "go" and t[1:2] in (["get"], ["install"]):
        return []  # Go modules come from the checksummed module proxy.
    return None


def base_name(arg):
    """
    Returns the bare package name of an install argument, without version or extras.
    """
    scope = ""
    if arg.startswith("@") and "/" in arg:
        scope, arg = arg.split("/", 1)
        scope += "/"
    name = re.split(r"[\[<>=!~@;:]", arg, 1)[0]
    return (scope + name).lower().replace("_", "-")


def near(a, b):
    """
    True when a and b differ by one edit (insert, delete, replace or swap).
    """
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1
                                  and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    short, long_ = sorted((a, b), key=len)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def problem(args):
    """
    Returns why an install needs a human, or None when it can proceed.
    """
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        flag = a.split("=", 1)[0]
        if flag in SOURCE_FLAGS:
            return "kaynak varsayilan kayit degil (" + flag + ")"
        if a.startswith("-"):
            skip = flag in VALUE_FLAGS and "=" not in a
            continue
        if re.match(r"^(git\+|https?:|file:|github:|gitlab:|ssh:)", a) or re.search(r"\.(whl|tar\.gz|tgz|zip)$", a):
            return "kaynak varsayilan kayit degil (" + a[:60] + ")"
        if a.startswith((".", "/", "~")):
            continue  # a local path inside the project
        name = base_name(a)
        if name in POPULAR:
            continue
        bare = name.split("/", 1)[-1]
        if len(bare) >= 4:
            for p in POPULAR:
                if len(p) >= 4 and near(bare, p):
                    return "'" + name + "' populer '" + p + "' paketine cok benziyor (typosquatting?)"
    return None


try:
    d = json.load(sys.stdin)
    cmd = (d.get("tool_input") or {}).get("command") or ""
except Exception:
    sys.exit(0)

# Quoted text is held aside so a separator inside it does not split the command.
quoted = []


def hold(m):
    quoted.append(m.group(0)[1:-1])
    return "\0" + str(len(quoted) - 1) + "\0"


cmd = re.sub(r"'[^']*'|\"[^\"]*\"", hold, cmd)
for seg in re.split(r"&&|\|\||;|\||\n", cmd):
    toks = [re.sub(r"\0(\d+)\0", lambda m: quoted[int(m.group(1))], t) for t in seg.split()]
    while toks and re.match(r"^\w+=", toks[0]):
        toks.pop(0)
    args = install_args(toks)
    why = problem(args) if args else None
    if why:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": "Supheli bagimlilik: " + why,
        }}, ensure_ascii=False))
        break
