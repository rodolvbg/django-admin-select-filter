"""One-off script (run as a pytest test to reuse the e2e fixtures) that
generates the screenshots referenced in README.md, under docs/screenshots/.

Not part of the normal suite's guarantees — delete or rerun freely whenever
the widget's look changes. Run just this file with:

    uv run pytest tests/e2e/test_zzz_generate_screenshots.py -p no:randomly
"""

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.testapp.admin import AuthorFilter, GenreFilter, MultipleAuthorFilter
from tests.testapp.models import Author, Book

pytestmark = pytest.mark.django_db(transaction=True)

SCREENSHOTS_DIR = Path(__file__).resolve().parents[2] / "docs" / "screenshots"

PAD = 12


def _login(page: Page, live_server, admin_user) -> None:
    page.goto(f"{live_server.url}/admin/login/")
    page.fill("#id_username", "admin")
    page.fill("#id_password", "password")
    page.click("input[type=submit]")


def _seed_books() -> None:
    rowling = Author.objects.create(name="J.K. Rowling")
    tolkien = Author.objects.create(name="J.R.R. Tolkien")
    orwell = Author.objects.create(name="George Orwell")
    Book.objects.create(title="Harry Potter", author=rowling, genre="fiction")
    Book.objects.create(title="The Hobbit", author=tolkien, genre="fiction")
    Book.objects.create(title="1984", author=orwell, genre="fiction")
    Book.objects.create(title="Homage to Catalonia", author=orwell, genre="nonfiction")


def _union_clip(*boxes: dict) -> dict:
    x0 = min(b["x"] for b in boxes) - PAD
    y0 = min(b["y"] for b in boxes) - PAD
    x1 = max(b["x"] + b["width"] for b in boxes) + PAD
    y1 = max(b["y"] + b["height"] for b in boxes) + PAD
    return {"x": max(x0, 0), "y": max(y0, 0), "width": x1 - x0, "height": y1 - y0}


def test_generate_screenshots(live_server, page: Page, admin_user, monkeypatch):
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    _seed_books()
    _login(page, live_server, admin_user)

    from tests.testapp import admin as testapp_admin

    monkeypatch.setattr(
        testapp_admin.E2EBookAdmin, "list_filter", [AuthorFilter, GenreFilter]
    )
    page.goto(f"{live_server.url}/e2e-admin/testapp/book/")
    page.set_viewport_size({"width": 1280, "height": 900})

    sidebar = page.locator("#changelist-filter")
    sidebar.wait_for()
    sidebar.screenshot(path=str(SCREENSHOTS_DIR / "hero.png"))
    sidebar_box = sidebar.bounding_box()
    assert sidebar_box is not None

    genre_select = page.locator('select[data-parameter-name="genre"]')
    genre_select.locator("xpath=following-sibling::span[1]").click()
    dropdown = page.locator(".select2-container--open .select2-dropdown")
    dropdown.wait_for()
    dropdown_box = dropdown.bounding_box()
    assert dropdown_box is not None
    page.screenshot(
        path=str(SCREENSHOTS_DIR / "choice-filter.png"),
        clip=_union_clip(sidebar_box, dropdown_box),
    )
    page.keyboard.press("Escape")

    author_select = page.locator('select[data-parameter-name="author"]')
    author_select.locator("xpath=following-sibling::span[1]").click()
    dropdown = page.locator(".select2-container--open .select2-dropdown")
    dropdown.wait_for()
    dropdown_box = dropdown.bounding_box()
    assert dropdown_box is not None
    page.screenshot(
        path=str(SCREENSHOTS_DIR / "foreign-key-filter.png"),
        clip=_union_clip(sidebar_box, dropdown_box),
    )
    page.keyboard.press("Escape")

    # --- multiple.png ---
    # Select2's `closeOnSelect` defaults to true even for a multi-select, so
    # each pick closes the dropdown and (per our own JS) navigates right
    # away. Pick one author at a time, waiting for each reload, then
    # screenshot the final closed state showing both chips.
    monkeypatch.setattr(
        testapp_admin.E2EBookAdmin, "list_filter", [MultipleAuthorFilter]
    )
    page.goto(f"{live_server.url}/e2e-admin/testapp/book/")

    def _pick(name: str) -> None:
        select = page.locator('select[data-parameter-name="author"]')
        select.locator("xpath=following-sibling::span[1]").click()
        page.get_by_role("option", name=name).click()
        expect(page).to_have_url(re.compile(r"author="))

    _pick("J.K. Rowling")
    _pick("George Orwell")

    sidebar = page.locator("#changelist-filter")
    sidebar.wait_for()
    sidebar.screenshot(path=str(SCREENSHOTS_DIR / "multiple.png"))
