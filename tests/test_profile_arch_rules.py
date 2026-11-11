import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "src" / "templates" / "profiles" / "fastapi-saas"
RULES = PROFILE / "backend" / "tests" / "unit" / "test_architecture_placement.py"
ARCH_DOCS = PROFILE / "docs" / "01-architecture"
# Folders a local run of the template creates; never part of the template.
GENERATED = {".venv", ".cache", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}

# A small tree that follows every rule.
GOOD = {
    "core/ids.py": "import uuid\n",
    "infra/database/models.py": "from sqlalchemy.orm import DeclarativeBase\n",
    "infra/mail/client.py": "import smtplib\n",
    "lib/__init__.py": "",
    "lib/pricing/__init__.py": "from .pipeline import price\n",
    "lib/pricing/schema.py": "",
    "lib/pricing/errors.py": "",
    "lib/pricing/pipeline.py": "from .rules.taxes import add_tax\n",
    "lib/pricing/rules/__init__.py": "",
    "lib/pricing/rules/taxes.py": "from app.core.ids import new_id\n",
    "features/__init__.py": "",
    "features/billing/__init__.py": "from .wallet import WalletService\n",
    "features/billing/helpers/__init__.py": "from .policy import can_refund\n",
    "features/billing/helpers/policy.py": "from app.lib.pricing import price\n",
    "features/billing/wallet/__init__.py": "from .service import WalletService\n",
    "features/billing/wallet/schema.py": "",
    "features/billing/wallet/errors.py": "",
    "features/billing/wallet/service.py": (
        "from app.infra.database.models import Wallet\n"
        "from app.infra.mail import MailClient\n"
        "from ..helpers import can_refund\n"
        "from .schema import TopUpIn, WalletOut\n\n\n"
        "class WalletService:\n"
        "    def __init__(self, uow, settings):\n"
        "        self._uow = uow\n\n"
        "    async def top_up(self, payload: TopUpIn, *, actor) -> WalletOut: ...\n\n"
        "    async def history(self, payload: TopUpIn) -> list[WalletOut]: ...\n\n"
        "    async def close(self, *, actor) -> None: ...\n\n"
        "    async def resolve(self, payload: TopUpIn) -> Actor: ...\n\n"
        "    def _fee(self, amount): ...\n"
    ),
    "interface/http/app.py": "from .routes import ROUTERS\n",
    "interface/http/deps/services.py": "from app.infra.database import UnitOfWork\nfrom app.lib.pricing import price\n",
    "interface/http/security/headers.py": "",
    "interface/http/routes/__init__.py": "from .health import router\n",
    "interface/http/routes/health.py": "from fastapi import APIRouter\n",
    "interface/http/routes/billing.py": (
        "from app.features.billing import WalletService\n"
        "from app.features.billing.wallet import WalletOut\n"
        "from ..deps import WalletServiceDep\n"
    ),
    "interface/cli/commands/__init__.py": "",
    "interface/cli/commands/billing/__init__.py": "",
    "interface/cli/commands/billing/wallet.py": "from app.features.billing import WalletService\n",
}

# One file (or a few) per rule that must be reported: finder name -> (files, text expected in a finding).
BAD = {
    "find_lib_depending_on_upper_layers": ({"lib/pricing/rules/limits.py": "from app.config import get_settings\n"}, "config"),
    "find_lib_packages_importing_each_other": ({"lib/tax/__init__.py": "from app.lib.pricing import price\n"}, "lib.pricing"),
    "find_flat_lib_modules": (
        {"lib/pricing/discounts.py": "", "lib/pricing/rounding.py": "", "lib/loose.py": ""},
        "kokte birden cok modul (discounts.py, pipeline.py, rounding.py)",
    ),
    "find_imports_into_lib_internals": (
        {"features/billing/helpers/fees.py": "from app.lib.pricing.rules.taxes import add_tax\n"}, "lib.pricing.rules.taxes"),
    "find_features_using_sqlalchemy": ({"features/billing/helpers/query.py": "from sqlalchemy import select\n"}, "sqlalchemy"),
    "find_features_reading_global_settings": (
        {"features/billing/helpers/limits.py": "from app.config import get_settings\n"}, "get_settings"),
    "find_infra_reading_global_settings": (
        {"infra/mail/client.py": "from app.config import get_settings\n"}, "infra/mail/client.py: get_settings"),
    "find_repos_used_outside_features": (
        {"worker/jobs/send.py": "from app.infra.database.repos.mail import MailRepo\n",
         "interface/http/deps/repos.py": "from app.infra.database.repos import MailRepo\n"},
        "worker/jobs/send.py: infra.database.repos.mail"),
    "find_features_reaching_into_infra": (
        {"features/billing/helpers/send.py": "from app.infra.mail.client import MailClient\n"}, "infra.mail.client"),
    "find_features_reaching_into_other_features": (
        {"features/identity/__init__.py": "", "features/identity/service.py": "from app.features.billing.wallet import x\n",
         "features/identity/schema.py": "", "features/identity/errors.py": ""}, "features.billing.wallet"),
    "find_feature_files_outside_helpers": ({"features/billing/wallet/fees.py": ""}, "features/billing/wallet/fees.py"),
    "find_services_without_schema_and_errors": (
        {"features/billing/refunds/service.py": "", "features/billing/stray/schema.py": ""}, "refunds/errors.py eksik"),
    "find_service_methods_breaking_the_contract": (
        {"features/billing/refunds/service.py": (
            "def helper(): ...\n\n\nclass RefundService:\n"
            "    async def refund(self, amount: int) -> dict: ...\n")},
        "girdi `amount: int`"),
    "find_unused_helpers": ({"features/billing/helpers/dead.py": ""}, "features/billing/helpers/dead.py"),
    "find_helpers_exported_from_feature_roots": (
        {"features/billing/__init__.py": "from .helpers import can_refund\nfrom .wallet import WalletService\n"}, "features.billing.helpers"),
    "find_double_underscore_names": (
        {"features/billing/helpers/policy.py": 'import os\n\nMAX__RETRY = 3\nMODE = os.environ["APP__MODE"]\n\n\ndef can__refund(): ...\n',
         "core/money__math.py": ""},
        "`MAX__RETRY`"),
    "find_misplaced_names": (
        {"infra/security/passwords.py": "", "core/utils.py": "", "lib/pricing/helpers/money.py": ""}, "infra/security/passwords.py"),
    "find_interface_modules_not_mirroring_features": (
        {"interface/http/routes/invoices.py": "", "interface/cli/commands/health.py": ""}, "`invoices` bir feature grubu degil"),
    "find_interface_modules_doing_more_than_translation": (
        {"interface/http/routes/billing.py": (
            "from sqlalchemy import select\n"
            "from app.infra.database.models import Invoice\n"
            "from app.lib.pricing import price\n"
            "from app.features.billing.wallet.service import WalletService\n"
            "from .health import router\n")},
        "infra.database.models"),
}


def load(src):
    """The template's rule module with its placeholders filled in and SRC pointed at a tree."""
    scratch = Path(tempfile.mkdtemp())
    module_path = scratch / "placement_rules.py"
    module_path.write_text(RULES.read_text(encoding="utf-8").replace("PKG_NAME", "app"), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("placement_rules", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    shutil.rmtree(scratch, ignore_errors=True)
    module.SRC = src
    return module


class PlacementRulesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.src = self.tmp / "app"
        self.write(GOOD)
        self.rules = load(self.src)

    def write(self, files):
        for rel, text in files.items():
            path = self.src / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def finders(self):
        return sorted(name for name in dir(self.rules) if name.startswith("find_"))

    def test_every_finder_has_a_bad_example_and_a_test_function(self):
        self.assertEqual(self.finders(), sorted(BAD))
        tests = [name for name in dir(self.rules) if name.startswith("test_")]
        self.assertEqual(len(tests), len(BAD) + 1)

    def test_a_tree_that_follows_the_rules_is_clean(self):
        for name in self.finders():
            with self.subTest(rule=name):
                self.assertEqual(getattr(self.rules, name)(), [])

    def test_each_rule_reports_its_violation(self):
        for name, (files, expected) in BAD.items():
            with self.subTest(rule=name):
                shutil.rmtree(self.src)
                self.write(GOOD)
                self.write(files)
                found = "\n".join(getattr(self.rules, name)())
                self.assertIn(expected, found)

    def test_double_underscores_are_found_everywhere_but_python_names(self):
        self.write(BAD["find_double_underscore_names"][0])
        self.write({"core/ok.py": '__all__ = ["x"]\n\n\nclass A:\n    def __init__(self):\n        self.one_two = __name__\n'})
        found = "\n".join(self.rules.find_double_underscore_names())
        for part in ("`MAX__RETRY`", "`APP__MODE`", "`can__refund`", "dosya adi `money__math`"):
            self.assertIn(part, found)
        self.assertNotIn("core/ok.py", found)

    def test_misplaced_names_cover_every_case(self):
        self.write(BAD["find_misplaced_names"][0])
        found = "\n".join(self.rules.find_misplaced_names())
        self.assertIn("core/utils.py: torba ad `utils`", found)
        self.assertIn("lib/pricing/helpers/money.py: helpers/ yalniz features altinda olur", found)
        self.assertNotIn("interface/http/security", found)

    def test_interface_rule_names_each_forbidden_import(self):
        self.write(BAD["find_interface_modules_doing_more_than_translation"][0])
        found = "\n".join(self.rules.find_interface_modules_doing_more_than_translation())
        for part in ("sqlalchemy", "lib.pricing", "features.billing.wallet.service (feature paket kokunden alinir)",
                     "interface.http.routes.health (ortak olan deps'e)"):
            self.assertIn(part, found)
        self.assertNotIn("deps/services.py", found)

    @unittest.skipIf(sys.version_info < (3, 12), "the skeleton uses Python 3.12 syntax (requires-python >= 3.12)")
    def test_the_shipped_skeleton_is_clean(self):
        shutil.rmtree(self.src)
        shutil.copytree(PROFILE / "backend" / "src" / "PKG_NAME", self.src, ignore=shutil.ignore_patterns("__pycache__"))
        for path in self.src.rglob("*.py"):
            path.write_text(path.read_text(encoding="utf-8").replace("PKG_NAME", "app"), encoding="utf-8")
        for name in self.finders():
            with self.subTest(rule=name):
                self.assertEqual(getattr(self.rules, name)(), [])


class ArchitectureDocsTest(unittest.TestCase):
    def read(self, prefix):
        return next(ARCH_DOCS.glob(f"{prefix}-*.md")).read_text(encoding="utf-8")

    def test_new_decisions_wait_for_the_user(self):
        for prefix in ("ARCH-0001", "ARCH-0002", "ARCH-0003", "ARCH-0004", "ARCH-0005", "ARCH-0006", "ARCH-0007", "ARCH-0008"):
            with self.subTest(doc=prefix):
                text = self.read(prefix)
                self.assertIn("status: draft", text)
                for heading in ("## Soru", "## Karar", "## Neden", "## Nasıl denetlenir"):
                    self.assertIn(heading, text)

    def test_placement_is_decided_by_rule_and_splits_by_content(self):
        text = self.read("ARCH-0006")
        for part in ("`infra/<kapı>/`", "`interface/http/security/`", "`helpers/`", "`lib/<paket>/`", "`infra/security` olmaz",
                     "Dosya satır sayısına göre bölünmez"):
            self.assertIn(part, text)
        self.assertNotRegex(text, r"\d+\s*satır")

    def test_rule_files_exist_for_each_area(self):
        rules = PROFILE / ".claude" / "rules"
        for name, path in (("backend-architecture", "backend/src/**/*.py"), ("backend-interface", "interface/**/*.py"),
                           ("backend-lib", "lib/**/*.py")):
            with self.subTest(rule=name):
                self.assertIn(path, (rules / f"{name}.md").read_text(encoding="utf-8"))

    def test_template_docstrings_start_below_the_opening_quotes(self):
        bad = []
        for path in sorted(p for p in (PROFILE / "backend").rglob("*.py") if not GENERATED & set(p.parts)):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith('"""') and len(stripped) > 3 and not stripped.endswith('"""'):
                    bad.append(f"{path.relative_to(PROFILE)}:{number}")
        self.assertEqual(bad, [])

    def test_template_code_has_no_dash_banners(self):
        bad = [str(p.relative_to(PROFILE)) for p in sorted((PROFILE / "backend").rglob("*.py")) if not GENERATED & set(p.parts)
               if any(line.lstrip().startswith("#") and "---" in line for line in p.read_text(encoding="utf-8").splitlines())]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
