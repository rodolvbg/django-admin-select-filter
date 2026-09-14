import re

import pytest
from playwright.sync_api import Page, expect

from tests.testapp.models import Author, Book

pytestmark = pytest.mark.django_db(transaction=True)


def _login(page: Page, live_server, django_user_model) -> None:
    django_user_model.objects.create_superuser(
        username="admin", email="admin@example.com", password="password"
    )
    page.goto(f"{live_server.url}/admin/login/")
    page.fill("#id_username", "admin")
    page.fill("#id_password", "password")
    page.click("input[type=submit]")
    expect(page).to_have_url(f"{live_server.url}/admin/")


def test_sync_filter_navigates_and_filters_results(
    live_server, page, django_user_model
):
    rowling = Author.objects.create(name="Rowling")
    tolkien = Author.objects.create(name="Tolkien")
    Book.objects.create(title="Harry Potter", author=rowling)
    Book.objects.create(title="The Hobbit", author=tolkien)

    _login(page, live_server, django_user_model)
    page.goto(f"{live_server.url}/e2e-admin/testapp/book/")

    page.locator("select.django-admin-select-filter + span .select2-selection").click()
    expect(page.locator(".select2-search__field")).to_have_attribute(
        "autocomplete", "off"
    )
    page.get_by_role("option", name="Rowling").click()

    expect(page).to_have_url(re.compile(r"author="))
    rows = page.locator("#result_list tbody tr")
    expect(rows).to_have_count(1)
    expect(rows).to_contain_text("Harry Potter")


def test_async_filter_loads_options_over_ajax_and_filters(
    live_server, page, django_user_model
):
    rowling = Author.objects.create(name="Rowling")
    tolkien = Author.objects.create(name="Tolkien")
    Book.objects.create(title="Harry Potter", author=rowling)
    Book.objects.create(title="The Hobbit", author=tolkien)

    _login(page, live_server, django_user_model)
    page.goto(f"{live_server.url}/admin/testapp/book/")

    async_select = page.locator(
        'select.django-admin-select-filter[data-async-call="true"]'
    )
    async_select.locator("xpath=following-sibling::span[1]").locator(
        ".select2-selection"
    ).click()

    search_box = page.locator(".select2-search__field")
    with page.expect_response(lambda r: "/admin/select-filter/options/" in r.url):
        search_box.fill("Rowl")

    page.get_by_role("option", name="Rowling").click()

    expect(page).to_have_url(re.compile(r"author="))
    rows = page.locator("#result_list tbody tr")
    expect(rows).to_have_count(1)
    expect(rows).to_contain_text("Harry Potter")
