"""
ARCH-0005, ARCH-0006: yerlesim, interface ve lib paketi kurallari.

Kaynak AST ile okunur, paket import edilmez. Her `find_*` ihlal listesini doner;
bir kurali gevsetmek icin once ADR yazilir, sonra bu dosya duzenlenir.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

PKG = "PKG_NAME"
SRC = Path(__file__).resolve().parents[2] / "src" / PKG

FEATURE_FILES = {"__init__.py", "service.py", "schema.py", "errors.py"}
# lib paketinin kokunde yalniz arayuz dosyalari ve tek giris modulu durur (ARCH-0006).
LIB_INTERFACE_FILES = {"__init__.py", "schema.py", "errors.py"}
# Baska lib paketlerinin kullanabildigi notr paketler; eklemek ADR ister.
NEUTRAL_LIBS: set[str] = set()
INFRA_GATES = {("infra", "database", "models"), ("infra", "database", "repos")}
CATCH_ALL_NAMES = {"utils", "common", "misc", "shared", "helper"}
# Bir feature'a ait olmayan route modulleri (ARCH-0006).
ROUTES_WITHOUT_FEATURE = {"health"}
CONTEXT_PARAMS = {"self", "actor", "admin", "client"}
# `resolve` yetki baglami doner (core tipi), veri degil.
CONTEXT_RETURNS = {"Actor", "AdminActor"}
FEATURE_INTERNALS = {"service", "schema", "errors", "helpers"}
SETTINGS_READER = re.compile(r"^get_\w*settings$")
# Python'in kendi adlari (`__init__`, `__all__`); bunlarin disinda cift alt cizgi olmaz (ARCH-0006).
PYTHON_OWN_NAME = re.compile(r"__[a-z0-9]+(_[a-z0-9]+)*__")


def _files(*sub: str) -> list[Path]:
    root = SRC.joinpath(*sub)
    return sorted(root.rglob("*.py")) if root.is_dir() else []


def _rel(path: Path) -> str:
    return path.relative_to(SRC).as_posix()


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _modules(path: Path) -> list[tuple[str, ...]]:
    """Dosyanin ice aktardigi moduller; goreli olanlar tam ada cevrilir."""
    package = [PKG, *path.relative_to(SRC).parts[:-1]]
    found: list[tuple[str, ...]] = []
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            found += [tuple(alias.name.split(".")) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else []
            module = (*base, *(node.module.split(".") if node.module else []))
            found.append(module)
            if node.level and not node.module:
                # `from . import x`: x bir alt modul olabilir
                found += [(*module, alias.name) for alias in node.names]
    return found


def _app(module: tuple[str, ...]) -> tuple[str, ...] | None:
    """Uygulama ici modul ise paket adi atilmis hali."""
    return module[1:] if module[:1] == (PKG,) else None


def _app_imports(path: Path) -> list[tuple[str, ...]]:
    return [inner for module in _modules(path) if (inner := _app(module)) is not None]


def _feature_groups() -> set[str]:
    root = SRC / "features"
    return {p.name for p in root.iterdir() if p.is_dir()} if root.is_dir() else set()


# lib (ARCH-0006)


def find_lib_depending_on_upper_layers() -> list[str]:
    upper = {"features", "interface", "worker", "config"}
    return [
        f"{_rel(path)}: {'.'.join(mod)}"
        for path in _files("lib")
        for mod in _app_imports(path)
        if mod[:1] and mod[0] in upper
    ]


def find_lib_packages_importing_each_other() -> list[str]:
    bad = []
    for path in _files("lib"):
        parts = path.relative_to(SRC / "lib").parts
        own = parts[0] if len(parts) > 1 else None
        for mod in _app_imports(path):
            other = mod[1] if mod[:1] == ("lib",) and len(mod) > 1 else None
            if other and other != own and other not in NEUTRAL_LIBS:
                bad.append(f"{_rel(path)}: {'.'.join(mod)}")
    return bad


def find_flat_lib_modules() -> list[str]:
    """
    lib bir kutuphaneler dizinidir: kokte gevsek modul olmaz; paketin
    kokunde arayuz dosyalari ve tek giris modulu disindaki her sey alt pakettedir."""
    root = SRC / "lib"
    if not root.is_dir():
        return []
    bad = [f"lib/{p.name}: gevsek modul" for p in sorted(root.glob("*.py")) if p.name != "__init__.py"]
    for package in sorted(p for p in root.iterdir() if p.is_dir() and p.name != "__pycache__"):
        extra = sorted(p.name for p in package.glob("*.py") if p.name not in LIB_INTERFACE_FILES)
        if len(extra) > 1:
            bad.append(f"lib/{package.name}: kokte birden cok modul ({', '.join(extra)})")
        if not (package / "__init__.py").exists():
            bad.append(f"lib/{package.name}: __init__.py yok")
    return bad


def find_imports_into_lib_internals() -> list[str]:
    """lib paketi yalniz kokunden kullanilir: `PKG.lib.<paket>`."""
    bad = []
    for path in _files():
        parts = path.relative_to(SRC).parts
        own = parts[1] if parts[0] == "lib" and len(parts) > 2 else None
        for mod in _app_imports(path):
            if mod[:1] == ("lib",) and len(mod) > 2 and mod[1] != own:
                bad.append(f"{_rel(path)}: {'.'.join(mod)}")
    return bad


# features (ARCH-0005, ARCH-0006)


def find_features_using_sqlalchemy() -> list[str]:
    return [
        f"{_rel(path)}: {'.'.join(mod)}"
        for path in _files("features")
        for mod in _modules(path)
        if mod[:1] == ("sqlalchemy",)
    ]


def _global_settings_reads(layer: str) -> list[str]:
    """Ayar giris noktasinda okunur ve parametre olarak gelir (ARCH-0007)."""
    bad = []
    for path in _files(layer):
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(f"{PKG}.config"):
                bad += [f"{_rel(path)}: {a.name}" for a in node.names if SETTINGS_READER.match(a.name)]
    return bad


def find_features_reading_global_settings() -> list[str]:
    return _global_settings_reads("features")


def find_infra_reading_global_settings() -> list[str]:
    return _global_settings_reads("infra")


def find_repos_used_outside_features() -> list[str]:
    """interface ve worker repo'ya dogrudan gitmez, servisten gecer (ARCH-0005)."""
    bad = []
    for layer in ("interface", "worker"):
        for path in _files(layer):
            bad += [
                f"{_rel(path)}: {'.'.join(mod)}"
                for mod in _app_imports(path)
                if mod[:3] == ("infra", "database", "repos")
            ]
    return bad


def find_features_reaching_into_infra() -> list[str]:
    """`PKG.infra.<kapi>` ya da modeller/repo'lar kapisi; ic module uzanilmaz."""
    bad = []
    for path in _files("features"):
        for mod in _app_imports(path):
            if mod[:1] != ("infra",):
                continue
            if (len(mod) > 2 and mod[:3] not in INFRA_GATES) or len(mod) > 3:
                bad.append(f"{_rel(path)}: {'.'.join(mod)}")
    return bad


def find_features_reaching_into_other_features() -> list[str]:
    bad = []
    for path in _files("features"):
        parts = path.relative_to(SRC / "features").parts
        own = parts[0] if len(parts) > 1 else None
        for mod in _app_imports(path):
            if mod[:1] == ("features",) and len(mod) > 2 and mod[1] != own:
                bad.append(f"{_rel(path)}: {'.'.join(mod)}")
    return bad


def find_feature_files_outside_helpers() -> list[str]:
    return [
        _rel(path)
        for path in _files("features")
        if path.name not in FEATURE_FILES and "helpers" not in path.relative_to(SRC).parts
    ]


def find_services_without_schema_and_errors() -> list[str]:
    bad = []
    for path in _files("features"):
        if path.name == "service.py":
            bad += [
                f"{_rel(path.parent)}/{n} eksik" for n in ("schema.py", "errors.py") if not (path.parent / n).exists()
            ]
        elif path.name in ("schema.py", "errors.py") and not (path.parent / "service.py").exists():
            bad.append(f"{_rel(path)}: yaninda service.py yok")
    return bad


def _is_out(annotation: str) -> bool:
    text = annotation.replace("list[", "").replace("]", "").replace(" | None", "")
    return annotation == "None" or text.endswith("Out")


def find_service_methods_breaking_the_contract() -> list[str]:
    """Disa acik servis metodu `...In` alir, `...Out` (ya da None) doner."""
    bad = []
    functions = (ast.FunctionDef, ast.AsyncFunctionDef)
    for path in _files("features"):
        if path.name != "service.py":
            continue
        tree = _tree(path)
        bad += [
            f"{_rel(path)}: disa acik modul fonksiyonu {node.name}"
            for node in tree.body
            if isinstance(node, functions) and not node.name.startswith("_")
        ]
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            for method in cls.body:
                if not isinstance(method, functions) or method.name.startswith("_"):
                    continue
                where = f"{_rel(path)}::{cls.name}.{method.name}"
                for arg in method.args.args + method.args.kwonlyargs:
                    hint = ast.unparse(arg.annotation) if arg.annotation else ""
                    if arg.arg not in CONTEXT_PARAMS and not hint.endswith("In"):
                        bad.append(f"{where}: girdi `{arg.arg}: {hint}` bir ...In degil")
                returns = ast.unparse(method.returns) if method.returns else ""
                if not _is_out(returns) and not (method.name == "resolve" and returns in CONTEXT_RETURNS):
                    bad.append(f"{where}: donus `{returns}` bir ...Out degil")
    return bad


def find_unused_helpers() -> list[str]:
    """Helper kendi feature grubuna hizmet eder; grupta kullanani yoksa durmaz."""
    bad = []
    for group in sorted(_feature_groups()):
        files = _files("features", group)
        imported = {mod for path in files for mod in _app_imports(path)}
        for path in files:
            parts = path.relative_to(SRC).with_suffix("").parts
            if "helpers" in parts and path.name != "__init__.py" and parts not in imported:
                bad.append(_rel(path))
    return bad


def find_helpers_exported_from_feature_roots() -> list[str]:
    """
    Feature koku servis, sema ve hatayi disa acar; helper'i acmaz. Birden cok
    feature grubunun kullandigi kod helper degil lib paketidir (ARCH-0006)."""
    bad = []
    for group in sorted(_feature_groups()):
        root = SRC / "features" / group / "__init__.py"
        if root.exists():
            bad += [f"{_rel(root)}: {'.'.join(mod)}" for mod in _app_imports(root) if "helpers" in mod]
    return bad


# adlar ve yerler (ARCH-0006)


def find_misplaced_names() -> list[str]:
    bad = []
    for path in _files():
        parts = path.relative_to(SRC).with_suffix("").parts
        for part in parts:
            if part in CATCH_ALL_NAMES or (part == "helpers" and path.name == "helpers.py"):
                bad.append(f"{_rel(path)}: torba ad `{part}`")
        if "helpers" in parts[:-1] and parts[0] != "features":
            bad.append(f"{_rel(path)}: helpers/ yalniz features altinda olur")
        if parts[0] == "infra" and "security" in parts:
            bad.append(f"{_rel(path)}: saf guvenlik kodu infra'ya girmez (helpers, lib ya da interface/http)")
    return sorted(set(bad))


def _names(tree: ast.Module) -> list[tuple[int, str]]:
    """
    Dosyada gecen adlar: tanimlar, kullanimlar ve tek sozcukluk metin sabitleri
    (ortam degiskeni adi gibi).
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Name):
            found.append((line, node.id))
        elif isinstance(node, ast.Attribute):
            found.append((line, node.attr))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.append((line, node.name))
        elif isinstance(node, (ast.arg, ast.keyword)) and node.arg:
            found.append((line, node.arg))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and re.fullmatch(r"\w+", node.value):
            found.append((line, node.value))
    return found


def find_double_underscore_names() -> list[str]:
    """Adlarda en cok tek alt cizgi olur; yalniz Python'in kendi adlari haric."""
    bad = []
    for path in _files():
        parts = path.relative_to(SRC).with_suffix("").parts
        bad += [f"{_rel(path)}: dosya adi `{p}`" for p in parts if "__" in p and not PYTHON_OWN_NAME.fullmatch(p)]
        bad += [
            f"{_rel(path)}:{line} `{name}`"
            for line, name in _names(_tree(path))
            if "__" in name and not PYTHON_OWN_NAME.fullmatch(name)
        ]
    return sorted(set(bad))


# interface (ARCH-0006)


def _interface_modules() -> list[tuple[Path, Path]]:
    """(modul, kok) ciftleri: http route'lari ve cli komutlari."""
    roots = [
        SRC / "interface" / "http" / "routes",
        SRC / "interface" / "cli" / "commands",
    ]
    return [(p, r) for r in roots if r.is_dir() for p in sorted(r.rglob("*.py")) if p.name != "__init__.py"]


def find_interface_modules_not_mirroring_features() -> list[str]:
    groups = _feature_groups()
    bad = []
    for path, root in _interface_modules():
        name = path.relative_to(root).with_suffix("").parts[0]
        allowed = groups | (ROUTES_WITHOUT_FEATURE if root.name == "routes" else set())
        if name not in allowed:
            bad.append(f"{_rel(path)}: `{name}` bir feature grubu degil")
    return bad


def find_interface_modules_doing_more_than_translation() -> list[str]:
    """
    Route ve komut ceviri yapar: infra, lib, SQL ve baska route/komut import etmez;
    feature'i (ya da alt feature'i) paket kokunden alir, ortak bagimliliklari `deps`'ten."""
    bad = []
    for path, root in _interface_modules():
        siblings = root.relative_to(SRC).parts
        own = path.relative_to(SRC).with_suffix("").parts
        for mod in _modules(path):
            inner = _app(mod)
            if mod[:1] == ("sqlalchemy",):
                bad.append(f"{_rel(path)}: sqlalchemy")
            elif inner is None:
                continue
            elif inner[:1] in (("infra",), ("lib",)):
                bad.append(f"{_rel(path)}: {'.'.join(inner)}")
            elif inner[:1] == ("features",) and FEATURE_INTERNALS & set(inner):
                bad.append(f"{_rel(path)}: {'.'.join(inner)} (feature paket kokunden alinir)")
            elif inner[: len(siblings)] == siblings and len(inner) > len(siblings) and inner != own[: len(inner)]:
                bad.append(f"{_rel(path)}: {'.'.join(inner)} (ortak olan deps'e)")
    return bad


# testler


def test_package_exists():
    assert SRC.is_dir(), f"paket dizini yok: {SRC}"


def test_lib_does_not_depend_on_upper_layers_or_settings():
    assert not find_lib_depending_on_upper_layers()


def test_lib_packages_do_not_import_each_other():
    assert not find_lib_packages_importing_each_other()


def test_lib_packages_are_structured_not_flat():
    assert not find_flat_lib_modules()


def test_lib_packages_are_used_through_their_root():
    assert not find_imports_into_lib_internals()


def test_features_do_not_touch_sqlalchemy():
    assert not find_features_using_sqlalchemy()


def test_features_receive_settings_instead_of_reading_them():
    assert not find_features_reading_global_settings()


def test_infra_receives_settings_instead_of_reading_them():
    assert not find_infra_reading_global_settings()


def test_interface_and_worker_reach_repos_only_through_services():
    assert not find_repos_used_outside_features()


def test_features_enter_infra_through_package_gates():
    assert not find_features_reaching_into_infra()


def test_features_use_each_other_only_through_the_package_root():
    assert not find_features_reaching_into_other_features()


def test_everything_but_service_schema_errors_lives_under_helpers():
    assert not find_feature_files_outside_helpers()


def test_every_service_has_its_schema_and_errors():
    assert not find_services_without_schema_and_errors()


def test_public_service_methods_take_in_and_return_out():
    assert not find_service_methods_breaking_the_contract()


def test_every_helper_is_used_by_its_own_feature_group():
    assert not find_unused_helpers()


def test_feature_roots_do_not_export_helpers():
    assert not find_helpers_exported_from_feature_roots()


def test_no_catch_all_names_and_nothing_in_the_wrong_layer():
    assert not find_misplaced_names()


def test_names_never_use_a_double_underscore():
    assert not find_double_underscore_names()


def test_routes_and_commands_mirror_the_features():
    assert not find_interface_modules_not_mirroring_features()


def test_routes_and_commands_only_translate():
    assert not find_interface_modules_doing_more_than_translation()
