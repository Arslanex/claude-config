"""Birim testleri icin veritabanisiz sahte oturum ve motor."""

from typing import Any, Self


class FakeResult:
    def __init__(self, value: Any = None, rows: list[tuple[Any, ...]] | None = None) -> None:
        self.value = value
        self.rows = rows or []

    def scalar_one_or_none(self) -> Any:
        return self.value

    def __iter__(self):
        return iter(self.rows)


class FakeNested:
    def __init__(self, session: "FakeSession") -> None:
        self.session = session

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: object) -> None:
        return None


class FakeSession:
    """Cagrilari `calls` listesine yazar; `flush_error` verilirse flush onu firlatir."""

    def __init__(self, result: Any = None, flush_error: Exception | None = None, commit_error: Exception | None = None):
        self.calls: list[tuple[str, Any]] = []
        self.result = result
        self.flush_error = flush_error
        self.commit_error = commit_error

    async def execute(self, statement: Any, params: Any = None) -> FakeResult:
        self.calls.append(("execute", (str(statement), params)))
        return FakeResult(self.result)

    def add(self, record: Any) -> None:
        self.calls.append(("add", record))

    async def flush(self) -> None:
        self.calls.append(("flush", None))
        if self.flush_error is not None:
            raise self.flush_error

    def begin_nested(self) -> FakeNested:
        self.calls.append(("begin_nested", None))
        return FakeNested(self)

    async def commit(self) -> None:
        self.calls.append(("commit", None))
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self) -> None:
        self.calls.append(("rollback", None))

    async def close(self) -> None:
        self.calls.append(("close", None))

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]


class FakeSessions:
    """`async_sessionmaker` yerine; her cagrida ayni oturumu verir ve sayar."""

    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.opened = 0

    def __call__(self) -> FakeSession:
        self.opened += 1
        return self.session


class FakeConnection:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def execute(self, statement: Any) -> FakeResult:
        return FakeResult(rows=self.rows)


class FakeEngine:
    """`connect()` verilen satirlari doner ya da `error` firlatir."""

    def __init__(self, rows: list[tuple[Any, ...]] | None = None, error: Exception | None = None) -> None:
        self.rows = rows or []
        self.error = error

    def connect(self) -> FakeConnection:
        if self.error is not None:
            raise self.error
        return FakeConnection(self.rows)
