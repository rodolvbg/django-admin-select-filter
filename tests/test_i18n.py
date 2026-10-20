import ast
import gettext
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import translation

from django_admin_select_filter.filters import BaseSelectFilter
from tests.testapp.models import Author, Book

LOCALE_DIR = Path(__file__).parent.parent / "src/django_admin_select_filter/locale"


def po_entries(path: Path) -> list[tuple[str, str, bool]]:
    """``(msgid, msgstr, fuzzy)`` for every message of a .po file."""
    entries = []
    for block in path.read_text(encoding="utf-8").split("\n\n"):
        msgid = "".join(
            re.findall(r'^(?:msgid|")\s*"?(.*?)"$', block, re.MULTILINE)[:1]
        )
        if (
            not re.search(r"^msgid ", block, re.MULTILINE)
            or 'msgid ""\nmsgstr ""' in block
        ):
            continue
        msgstrs = re.findall(r'^msgstr(?:\[\d+\])? "(.*)"$', block, re.MULTILINE)
        entries.append((msgid, " ".join(msgstrs), "#, fuzzy" in block))
    return entries


PO_LINE = re.compile(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?) (".*")$')


def po_messages(path):
    """``{msgid: msgstr}`` (``{(msgid, n): msgstr}`` for plurals) of a .po file."""
    messages: dict[Any, str] = {}
    for block in path.read_text(encoding="utf-8").split("\n\n"):
        fields: dict[str, str] = {}
        key = None
        for line in block.splitlines():
            match = PO_LINE.match(line)
            if match:
                key = match.group(1)
                fields[key] = ast.literal_eval(match.group(2))
            elif line.startswith('"') and key:
                fields[key] += ast.literal_eval(line)
        msgid = fields.get("msgid")
        if not msgid or "#, fuzzy" in block:
            continue
        if "msgctxt" in fields:
            msgid = f"{fields['msgctxt']}\x04{msgid}"
        if "msgid_plural" in fields:
            for name, value in fields.items():
                if name.startswith("msgstr["):
                    messages[(msgid, int(name[7:-1]))] = value
        else:
            messages[msgid] = fields["msgstr"]
    return messages


def mo_messages(path):
    """The same, from the compiled .mo (as Django will load it)."""
    with path.open("rb") as file:
        catalog = getattr(gettext.GNUTranslations(file), "_catalog")  # noqa: B009
    return {key: value for key, value in catalog.items() if key != ""}


CATALOGS = sorted(LOCALE_DIR.glob("*/LC_MESSAGES/django.po"))
ENTRIES = [
    pytest.param(catalog, msgstr, fuzzy, id=f"{catalog.parent.parent.name}-{msgid}")
    for catalog in CATALOGS
    for msgid, msgstr, fuzzy in po_entries(catalog)
]
CATALOG_IDS = [catalog.parent.parent.name for catalog in CATALOGS]


class TestTranslationCatalogs:
    """The shipped .po / .mo catalogs."""

    def test_catalogs_exist(self):
        assert CATALOGS

    @pytest.mark.parametrize(("catalog", "msgstr", "fuzzy"), ENTRIES)
    def test_every_message_is_translated(self, catalog, msgstr, fuzzy):
        assert msgstr.strip(), "untranslated"
        assert not fuzzy, "fuzzy"

    @pytest.mark.parametrize("catalog", CATALOGS, ids=CATALOG_IDS)
    def test_compiled_catalogs_are_shipped(self, catalog):
        """The shipped .mo has exactly the .po's translations (not compared by
        date: a git checkout gives both files arbitrary modification times)."""
        mo = catalog.with_suffix(".mo")
        assert mo.exists()
        assert mo_messages(mo) == po_messages(catalog)


@pytest.mark.django_db
class TestSpanishChangelist:
    """The changelist filter texts rendered in other languages."""

    @pytest.fixture(autouse=True)
    def _data(self, client):
        user = User.objects.create_superuser("admin", "a@example.com", "x")
        Book.objects.create(title="HP", author=Author.objects.create(name="Rowling"))
        client.force_login(user)

    def get(self, client, language):
        with translation.override(language):
            return client.get(reverse("admin:testapp_book_changelist"))

    def test_filter_texts_follow_the_language(self, client):
        html = self.get(client, "es").content.decode()

        assert 'data-placeholder="Buscar"' in html
        assert ">Todo<" in re.sub(r">\s+", ">", re.sub(r"\s+<", "<", html))

    def test_select2_gets_its_translation_file(self, client):
        html = self.get(client, "es").content.decode()

        assert 'data-language="es"' in html
        assert (
            'data-select2-i18n-url="/static/admin/js/vendor/select2/i18n/es.js"' in html
        )

    def test_regional_variant_falls_back_to_the_language(self, client):
        html = self.get(client, "es-ar").content.decode()

        assert 'data-language="es"' in html

    def test_language_without_select2_translation(self, client):
        html = self.get(client, "en").content.decode()

        assert 'data-language="en"' in html

    def test_unknown_language_has_no_select2_translation(self):
        select2_language = cast(property, BaseSelectFilter.select2_language)
        select2_i18n_url = cast(property, BaseSelectFilter.select2_i18n_url)
        assert select2_language.fget and select2_i18n_url.fget
        with translation.override("xx"):
            language = select2_language.fget(None)
            spec = SimpleNamespace(select2_language=language)

            assert language is None
            assert select2_i18n_url.fget(spec) is None
