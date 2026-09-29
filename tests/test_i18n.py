import re
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from django.contrib.auth.models import User
from django.test import TestCase
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


class TranslationCatalogTests(TestCase):
    def test_every_message_is_translated(self):
        catalogs = list(LOCALE_DIR.glob("*/LC_MESSAGES/django.po"))
        self.assertTrue(catalogs)
        for catalog in catalogs:
            for msgid, msgstr, fuzzy in po_entries(catalog):
                with self.subTest(catalog=catalog.parent.parent.name, msgid=msgid):
                    self.assertTrue(msgstr.strip(), "untranslated")
                    self.assertFalse(fuzzy, "fuzzy")

    def test_compiled_catalogs_are_shipped(self):
        for catalog in LOCALE_DIR.glob("*/LC_MESSAGES/django.po"):
            with self.subTest(catalog=str(catalog)):
                mo = catalog.with_suffix(".mo")
                self.assertTrue(mo.exists())
                self.assertGreaterEqual(mo.stat().st_mtime, catalog.stat().st_mtime)


class SpanishChangelistTests(TestCase):
    user: User

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser("admin", "a@example.com", "x")
        Book.objects.create(title="HP", author=Author.objects.create(name="Rowling"))

    def get(self, language):
        self.client.force_login(self.user)
        with translation.override(language):
            return self.client.get(reverse("admin:testapp_book_changelist"))

    def test_filter_texts_follow_the_language(self):
        html = self.get("es").content.decode()

        self.assertIn('data-placeholder="Buscar"', html)
        self.assertIn(">Todo<", re.sub(r">\s+", ">", re.sub(r"\s+<", "<", html)))

    def test_select2_gets_its_translation_file(self):
        html = self.get("es").content.decode()

        self.assertIn('data-language="es"', html)
        self.assertIn(
            'data-select2-i18n-url="/static/admin/js/vendor/select2/i18n/es.js"', html
        )

    def test_regional_variant_falls_back_to_the_language(self):
        html = self.get("es-ar").content.decode()

        self.assertIn('data-language="es"', html)

    def test_language_without_select2_translation(self):
        html = self.get("en").content.decode()

        self.assertIn('data-language="en"', html)
        select2_language = cast(property, BaseSelectFilter.select2_language)
        select2_i18n_url = cast(property, BaseSelectFilter.select2_i18n_url)
        assert select2_language.fget and select2_i18n_url.fget
        with translation.override("xx"):
            language = select2_language.fget(None)
            spec = SimpleNamespace(select2_language=language)

            self.assertIsNone(language)
            self.assertIsNone(select2_i18n_url.fget(spec))
