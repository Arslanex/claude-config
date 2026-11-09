#!/usr/bin/env python3
"""PreToolUse guard for the Bash tool.

Blocks (exit 2) commands that spend money or weaken security so autonomous
agents can run freely everywhere else. Fails open on malformed input.

Rules apply by command position: the command line is split into simple
commands (including $(...), `...`, `sh -c`, eval and script text piped into a
shell), and a rule only fires on the executed command name and its
arguments. Quoted arguments of data commands (echo, git commit, gh ...) and
heredoc bodies that do not reach a shell are never scanned. If the command
cannot be parsed, every rule falls back to an unanchored scan of the whole
text, so doubtful input still blocks. Heuristic only; the sandbox and
permission rules remain the primary controls.
"""
import json
import os
import re
import subprocess
import sys

try:
    data = json.load(sys.stdin)
    cmd = (data.get("tool_input") or {}).get("command") or ""
    cwd = data.get("cwd") or None
except Exception:
    sys.exit(0)

PROTECTED = {"main", "master", "production", "prod"}


def block(kind, why):
    if kind == "docker":
        tail = "Run the same command through tools/dockerw, which refuses unsafe flags and paths outside the project."
    else:
        tail = "Do not retry or work around this. Stop and ask the user for explicit approval."
    print(f"BLOCKED [{kind}]: {why}. {tail}", file=sys.stderr)
    sys.exit(2)


# Rules for the command itself, matched against "name args..." from its start.
CMD_RULES = [
    ("security", "sudo is not allowed", r"sudo\b"),
    ("money", "terraform/tofu apply or destroy changes real infrastructure",
     r"(?:terraform|tofu)\s+(?:apply|destroy)\b"),
    ("money", "pulumi up/destroy changes real infrastructure",
     r"pulumi\s+(?:up|destroy)\b"),
    ("money", "wrangler deploy/publish/delete",
     r"(?:npx\s+)?wrangler\s+(?:deploy|publish|delete|pages\s+deploy|versions\s+deploy)\b"),
    ("money", "fly.io deploy/scale/create",
     r"(?:fly|flyctl)\s+(?:deploy|launch|scale|machines?\s+(?:run|create)|"
     r"volumes?\s+create|apps?\s+create)\b"),
    ("money", "netlify deploy", r"(?:npx\s+)?netlify\s+deploy\b"),
    ("money", "vercel deploy",
     r"(?:npx\s+)?vercel(?=\s|$)(?!\s+(?:whoami|ls|list|inspect|logs|help|--version|-v)\b)"),
    ("money", "heroku create/scale/addons",
     r"heroku\s+(?:create|addons:create|ps:scale|ps:resize|pipelines:promote)\b"),
    ("money", "publishing a package or image",
     r"(?:(?:npm|pnpm|yarn|bun)\s+publish|twine\s+upload|cargo\s+publish|docker\s+push)\b"),
    ("money", "stripe CLI can touch real payments",
     r"stripe(?=\s|$)(?!\s+(?:listen|logs|--version|version|help|login)\b)"),
    ("docker", "raw container CLIs are not allowed for agents",
     r"(?:docker(?:-compose)?|podman|nerdctl|colima|orbctl)\b"),
]

# Rules matched anywhere in the arguments of any command that is not a data
# command (so `ssh host 'git push -f'` or `psql -c "DROP TABLE x"` still block).
LOOSE_RULES = [
    ("security", "force push is not allowed",
     r"\bgit\s+push\b[^;&|\n]*(?:\s--force\b|\s-f\b|--force-with-lease|\s\+\S)"),
    ("security", "push to a protected branch (main/master/production)",
     r"\bgit\s+push\b[^;&|\n]*\b(?:main|master|production|prod)\b"),
    ("security", "git reset --hard / git clean -f discards work",
     r"\bgit\s+(?:reset\s+--hard|clean\s+-\w*f)"),
    ("security", "recursive delete of a broad path",
     r"\brm\s+(?:-\w+\s+)*-\w*[rR]\w*\s+(?:-\w+\s+)*"
     r"(?:/|/\*|~|~/|~/\*|\$HOME|\$HOME/|\.\.|\.\./\S*|\*)(?=\s|$)"),
    ("security", "destructive SQL",
     r"\b(?:drop\s+(?:table|database|schema)|truncate\s+table)\b"),
]

CLOUD_CLIS = {"aws", "gcloud", "az", "doctl"}
CLOUD_READ = r"\b(?:list|ls|describe|get|show|help|version|whoami)\b"
CLOUD_MUTATE = (
    r"\b(?:create|run|start|launch|delete|terminate|update|put|deploy|apply|publish|"
    r"invoke|scale|rm|remove|attach|enable|modify|purchase|allocate|destroy|import|"
    r"insert|copy|cp|mv|sync)"
)
CLOUD_WHY = "cloud CLI command that may create or change billable resources"

SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
DOWNLOADERS = {"curl", "wget"}

# Commands whose arguments and heredoc bodies are plain data.
DATA_CMDS = {
    "echo", "printf", "grep", "egrep", "fgrep", "rg", "ag", "ack", "cat", "tee",
    "head", "tail", "less", "more", "ls", "wc", "sort", "uniq", "diff", "tr",
    "cut", "gh",
}
# git subcommands that can do harm; every other git subcommand is data.
GIT_RISKY = {"push", "reset", "clean"}
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}

# Wrappers that run the rest of the line; value = options that take an argument.
WRAPPERS = {
    "env": {"-u", "-C", "-S", "--unset", "--chdir"},
    "command": set(),
    "builtin": set(),
    "nohup": set(),
    "time": {"-f", "-o"},
    "exec": {"-a"},
    "nice": {"-n"},
    "stdbuf": {"-i", "-o", "-e"},
    "timeout": {"-s", "-k"},
    "xargs": {"-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a", "-J"},
    "npx": {"-p", "--package"},
    "bunx": set(),
}
RESERVED = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "}"}
UNSUPPORTED = {"case", "select", "coproc", "function"}
ASSIGN = re.compile(r"^[A-Za-z_]\w*=")
MAX_DEPTH = 8


class ParseError(Exception):
    pass


class Cmd:
    """One simple command: its words, heredoc/here-string bodies, pipe source."""

    def __init__(self, pipe_from):
        self.words = []
        self.heredocs = []
        self.pipe_from = pipe_from


class Parser:
    """Minimal shell lexer. Appends every simple command, including those inside
    substitutions, to `out`. Raises ParseError on anything it cannot follow."""

    def __init__(self, text, out):
        self.s = text
        self.i = 0
        self.out = out
        self.pending = []  # heredocs waiting for their body: (cmd, delim, strip, quoted)

    def parse_all(self):
        self.parse_list(False)
        if self.pending:
            raise ParseError("unterminated heredoc")

    def read_heredocs(self):
        s = self.s
        for cmd, delim, strip, quoted in self.pending:
            lines = []
            while True:
                if self.i >= len(s):
                    raise ParseError("unterminated heredoc")
                j = s.find("\n", self.i)
                end = j if j >= 0 else len(s)
                line = s[self.i:end]
                self.i = j + 1 if j >= 0 else len(s)
                if (line.lstrip("\t") if strip else line) == delim:
                    break
                lines.append(line)
            body = "\n".join(lines)
            cmd.heredocs.append(body)
            if not quoted:
                self.scan_subs(body)
        self.pending = []

    def scan_subs(self, body):
        """Run substitutions inside an unquoted heredoc body (the body is data)."""
        p = Parser(body, self.out)
        while p.i < len(body):
            c = body[p.i]
            if c == "\\":
                p.i += 2
            elif c == "$" and body.startswith("(", p.i + 1):
                p.i += 2
                p.parse_list(True)
            elif c == "`":
                p.backtick()
            else:
                p.i += 1
        if p.pending:
            raise ParseError("unterminated heredoc")

    def backtick(self):
        s = self.s
        j = self.i + 1
        while True:
            if j >= len(s):
                raise ParseError("unterminated backtick")
            if s[j] == "\\":
                j += 2
            elif s[j] == "`":
                break
            else:
                j += 1
        Parser(s[self.i + 1:j].replace("\\`", "`"), self.out).parse_all()
        self.i = j + 1

    def arith(self):
        j = self.s.find("))", self.i)
        if j < 0:
            raise ParseError("unterminated arithmetic")
        inner = self.s[self.i:j]
        if "$(" in inner or "`" in inner:
            raise ParseError("substitution inside arithmetic")
        self.i = j + 2

    def read_dq(self):
        s = self.s
        self.i += 1
        out = []
        while True:
            if self.i >= len(s):
                raise ParseError("unterminated double quote")
            c = s[self.i]
            if c == '"':
                self.i += 1
                return "".join(out)
            if c == "\\" and self.i + 1 < len(s):
                n = s[self.i + 1]
                if n in '$`"\\':
                    out.append(n)
                elif n != "\n":
                    out.append(c + n)
                self.i += 2
            elif c == "$" and s.startswith("((", self.i + 1):
                self.i += 1
                self.arith()
                out.append("0")
            elif c == "$" and s.startswith("(", self.i + 1):
                self.i += 2
                self.parse_list(True)
                out.append("$(...)")
            elif c == "`":
                self.backtick()
                out.append("$(...)")
            else:
                out.append(c)
                self.i += 1

    def parse_list(self, closer):
        s = self.s
        n = len(s)
        cur = None
        buf = None
        quoted = False
        redir = False
        hd = None  # strip-tabs flag while the next word is a heredoc delimiter
        herestr = False
        pipe_from = None

        def cmd_():
            nonlocal cur
            if cur is None:
                cur = Cmd(pipe_from)
                self.out.append(cur)
            return cur

        def flush():
            nonlocal buf, quoted, redir, hd, herestr
            if buf is None:
                return
            w, q = buf, quoted
            buf, quoted = None, False
            if hd is not None:
                self.pending.append((cmd_(), w, hd, q))
                hd = None
            elif herestr:
                cmd_().heredocs.append(w)
                herestr = False
            elif redir:
                redir = False  # redirect target, not an argument
            else:
                cmd_().words.append(w)

        def end(pipe=False):
            nonlocal cur, pipe_from
            flush()
            pipe_from = cur if pipe else None
            cur = None

        def add(text, q=False):
            nonlocal buf, quoted
            buf = (buf or "") + text
            quoted = quoted or q

        while True:
            if self.i >= n:
                if closer:
                    raise ParseError("unterminated $(")
                end()
                return
            c = s[self.i]
            nx = s[self.i + 1] if self.i + 1 < n else ""
            if c in " \t":
                flush()
                self.i += 1
            elif c == "\n":
                flush()
                self.i += 1
                if self.pending:
                    self.read_heredocs()
                end()
            elif c == "\\":
                if nx == "\n":
                    self.i += 2
                elif nx:
                    add(nx, True)
                    self.i += 2
                else:
                    add(c)
                    self.i += 1
            elif c == "'":
                j = s.find("'", self.i + 1)
                if j < 0:
                    raise ParseError("unterminated single quote")
                add(s[self.i + 1:j], True)
                self.i = j + 1
            elif c == '"':
                add(self.read_dq(), True)
            elif c == "$" and nx == "'":
                j = self.i + 2
                while True:
                    if j >= n:
                        raise ParseError("unterminated $'...'")
                    if s[j] == "\\":
                        j += 2
                    elif s[j] == "'":
                        break
                    else:
                        j += 1
                add(s[self.i + 2:j], True)
                self.i = j + 1
            elif c == "$" and s.startswith("((", self.i + 1):
                self.i += 1
                self.arith()
                add("0")
            elif c == "$" and nx == "(":
                self.i += 2
                self.parse_list(True)
                add("$(...)")
            elif c == "`":
                self.backtick()
                add("$(...)")
            elif c in "<>" and nx == "(":
                self.i += 2
                self.parse_list(True)
                add("$(...)")
            elif c == "<" and s.startswith("<<<", self.i):
                flush()
                herestr = True
                self.i += 3
            elif c == "<" and nx == "<":
                flush()
                self.i += 2
                hd = s.startswith("-", self.i)
                if hd:
                    self.i += 1
            elif c in "<>":
                if buf is not None and buf.isdigit() and not quoted:
                    buf = None  # fd number as in 2>&1
                else:
                    flush()
                self.i += 1
                while self.i < n and s[self.i] in "&>|":
                    self.i += 1
                redir = True
            elif c == ";":
                end()
                self.i += 1
            elif c == "&":
                if nx == ">":
                    flush()
                    self.i += 1
                else:
                    end()
                    self.i += 2 if nx == "&" else 1
            elif c == "|":
                if nx == "|":
                    end()
                    self.i += 2
                else:
                    end(pipe=True)
                    self.i += 2 if nx == "&" else 1
            elif c == "(":
                end()
                self.i += 1
            elif c == ")":
                end()
                self.i += 1
                if closer:
                    return
            elif c == "#" and buf is None:
                j = s.find("\n", self.i)
                self.i = j if j >= 0 else n
            else:
                add(c)
                self.i += 1


def git_split(args):
    """Return (subcommand, rest) of a git invocation, skipping global options."""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in GIT_OPTS_WITH_VALUE else 1
    return (args[i], args[i + 1:]) if i < len(args) else ("", [])


def unwrap(words):
    """Drop reserved words, VAR=val and wrapper commands; return the real argv."""
    i, n = 0, len(words)
    while i < n:
        w = words[i]
        if w in RESERVED or ASSIGN.match(w):
            i += 1
            continue
        name = os.path.basename(w).lower()
        if name not in WRAPPERS:
            break
        value_opts = WRAPPERS[name]
        i += 1
        while i < n:
            t = words[i]
            if t == "--":
                i += 1
                break
            if name == "env" and ASSIGN.match(t):
                i += 1
            elif t.startswith("-") and len(t) > 1:
                if name == "command" and t in ("-v", "-V"):
                    return []  # lookup only, nothing is executed
                i += 2 if t in value_opts else 1
            else:
                break
        if name == "timeout" and i < n:
            i += 1  # duration
    return words[i:]


def check_protected_branch():
    try:
        br = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        br = ""
    if br in PROTECTED:
        block("security", f"git push while on protected branch '{br}'")


def check_pipe_into_shell(shell_cmd, depth):
    """Script text piped into a shell is executed, so analyse it."""
    stage = shell_cmd.pipe_from
    while stage is not None:
        argv = unwrap(stage.words)
        if argv:
            if os.path.basename(argv[0]).lower() in DOWNLOADERS:
                block("security", "piping a download into a shell")
            for a in argv[1:]:
                analyze(a, depth + 1)
        for body in stage.heredocs:
            analyze(body, depth + 1)
        stage = stage.pipe_from


def check_cmd(c, depth):
    argv = unwrap(c.words)
    if not argv:
        return
    name = os.path.basename(argv[0]).lower()
    if name.startswith("$") or name in UNSUPPORTED:
        raise ParseError(f"cannot resolve command name {name!r}")
    args = argv[1:]
    if name == "git":
        sub, rest = git_split(args)
        s = " ".join(["git", sub] + rest)
    else:
        sub = ""
        s = " ".join([name] + args)

    for kind, why, pat in CMD_RULES:
        if re.match(pat, s, re.I):
            block(kind, why)
    if name in CLOUD_CLIS:
        if not re.search(CLOUD_READ, s) or re.search(CLOUD_MUTATE, s):
            block("money", CLOUD_WHY)

    is_data = name in DATA_CMDS or (name == "git" and sub not in GIT_RISKY)
    if not is_data:
        text = " ".join([s] + c.heredocs)
        for kind, why, pat in LOOSE_RULES:
            if re.search(pat, text, re.I):
                block(kind, why)
        if re.search(r"\bgit\s+push\b", text):
            check_protected_branch()

    if name in SHELLS:
        for i, a in enumerate(args):
            if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", a):
                if i + 1 < len(args):
                    analyze(args[i + 1], depth + 1)
                return
        for body in c.heredocs:
            analyze(body, depth + 1)
        if c.pipe_from is not None:
            check_pipe_into_shell(c, depth)
    elif name == "eval":
        analyze(" ".join(args), depth + 1)


def analyze(text, depth=0):
    if depth > MAX_DEPTH:
        raise ParseError("nesting too deep")
    out = []
    Parser(text, out).parse_all()
    for c in out:
        check_cmd(c, depth)


def scan_whole_text(text):
    """Fail-closed fallback: every rule, unanchored, over the raw text."""
    start = r"(?<![\w.-])"
    for kind, why, pat in CMD_RULES:
        if re.search(start + pat, text, re.I):
            block(kind, why)
    for kind, why, pat in LOOSE_RULES:
        if re.search(pat, text, re.I):
            block(kind, why)
    if re.search(start + r"(?:curl|wget)\b[^\n]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b", text):
        block("security", "piping a download into a shell")
    if re.search(start + r"(?:aws|gcloud|az|doctl)(?=\s|$)", text):
        if not re.search(CLOUD_READ, text) or re.search(CLOUD_MUTATE, text):
            block("money", CLOUD_WHY)
    if re.search(r"\bgit\s+push\b", text):
        check_protected_branch()


try:
    analyze(cmd)
except Exception:  # ParseError, RecursionError or anything unexpected
    scan_whole_text(cmd)

sys.exit(0)
