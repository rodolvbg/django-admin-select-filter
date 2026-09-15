import re

from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import expect, sync_playwright

from tests.testapp.models import Author, Book


class SelectFilterTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        context = self.browser.new_context()
        self.addCleanup(context.close)
        self.page = context.new_page()

        User.objects.create_superuser("admin", "admin@example.com", "password")
        self.page.goto(f"{self.live_server_url}/admin/login/")
        self.page.fill("#id_username", "admin")
        self.page.fill("#id_password", "password")
        self.page.click("input[type=submit]")
        expect(self.page).to_have_url(f"{self.live_server_url}/admin/")

        rowling = Author.objects.create(name="Rowling")
        tolkien = Author.objects.create(name="Tolkien")
        Book.objects.create(title="Harry Potter", author=rowling)
        Book.objects.create(title="The Hobbit", author=tolkien)

    def test_sync_filter_navigates_and_filters_results(self):
        self.page.goto(f"{self.live_server_url}/e2e-admin/testapp/book/")

        self.page.locator(
            "select.django-admin-select-filter + span .select2-selection"
        ).click()
        self.page.get_by_role("option", name="Rowling").click()

        expect(self.page).to_have_url(re.compile(r"author="))
        rows = self.page.locator("#result_list tbody tr")
        expect(rows).to_have_count(1)
        expect(rows).to_contain_text("Harry Potter")

    def test_async_filter_loads_options_over_ajax_and_filters(self):
        self.page.goto(f"{self.live_server_url}/admin/testapp/book/")

        async_select = self.page.locator(
            "select.django-admin-select-filter"
            '[data-async-call="true"][data-parameter-name="author"]'
        )
        async_select.locator("xpath=following-sibling::span[1]").locator(
            ".select2-selection"
        ).click()

        search_box = self.page.locator(".select2-search__field")
        with self.page.expect_response(
            lambda r: "/django_admin_select_filter/options/" in r.url
        ):
            search_box.fill("Rowl")

        self.page.get_by_role("option", name="Rowling").click()

        expect(self.page).to_have_url(re.compile(r"author="))
        rows = self.page.locator("#result_list tbody tr")
        expect(rows).to_have_count(1)
        expect(rows).to_contain_text("Harry Potter")
