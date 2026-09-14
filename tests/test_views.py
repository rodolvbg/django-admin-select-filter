import pytest
from django.test import Client
from django.urls import reverse

from tests.testapp.models import Author, Book

pytestmark = pytest.mark.django_db


def test_options_requires_all_parameters():
    client = Client()
    url = reverse("admin_select_filter:options")

    response = client.get(url, {"app_label": "testapp", "model_name": "book"})

    assert response.status_code == 404


def test_options_404_for_unknown_model():
    client = Client()
    url = reverse("admin_select_filter:options")

    response = client.get(
        url,
        {"app_label": "doesnotexist", "model_name": "nope", "parameter_name": "x"},
    )

    assert response.status_code == 404


def test_options_404_for_unregistered_model():
    client = Client()
    url = reverse("admin_select_filter:options")

    response = client.get(
        url,
        {
            "app_label": "contenttypes",
            "model_name": "contenttype",
            "parameter_name": "x",
        },
    )

    assert response.status_code == 404


def test_options_404_when_no_matching_filter():
    client = Client()
    url = reverse("admin_select_filter:options")

    response = client.get(
        url,
        {"app_label": "testapp", "model_name": "author", "parameter_name": "x"},
    )

    assert response.status_code == 404


def test_options_returns_select2_results():
    author = Author.objects.create(name="Rowling")
    Book.objects.create(title="Harry Potter", author=author)
    client = Client()
    url = reverse("admin_select_filter:options")

    response = client.get(
        url,
        {
            "app_label": "testapp",
            "model_name": "book",
            "parameter_name": "author",
            "q": "Rowl",
            "facets": "true",
        },
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0] == {"id": "__all__", "text": "All"}
    assert {"id": str(author.pk), "text": "Rowling (1)"} in results
