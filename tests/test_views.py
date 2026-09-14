import pytest
from django.test import Client
from django.urls import reverse

from tests.testapp.models import Author, Book

pytestmark = pytest.mark.django_db


class Select2FilterOptionsViewTests:
    def test_options_requires_all_parameters(self):
        client = Client()
        url = reverse("admin_select_filter:options")

        response = client.get(url, {"app_label": "testapp", "model_name": "book"})

        assert response.status_code == 400

    def test_options_404_for_unknown_model(self):
        client = Client()
        url = reverse("admin_select_filter:options")

        response = client.get(
            url,
            {"app_label": "doesnotexist", "model_name": "nope", "parameter_name": "x"},
        )

        assert response.status_code == 404

    def test_options_404_for_unregistered_model(self):
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

    def test_options_403_for_unprivileged_user(self):
        client = Client()
        url = reverse("admin_select_filter:options")

        response = client.get(
            url,
            {"app_label": "testapp", "model_name": "book", "parameter_name": "author"},
        )

        assert response.status_code == 403

    def test_options_404_when_no_matching_filter(self, admin_client):
        url = reverse("admin_select_filter:options")

        response = admin_client.get(
            url,
            {"app_label": "testapp", "model_name": "author", "parameter_name": "x"},
        )

        assert response.status_code == 404

    def test_options_404_for_non_async_filter(self, admin_client):
        url = reverse("admin_select_filter:options")

        response = admin_client.get(
            url,
            {
                "app_label": "testapp",
                "model_name": "book",
                "parameter_name": "not_a_real_field",
            },
        )

        assert response.status_code == 404

    def test_options_returns_select2_results_for_foreign_key_filter(self, admin_client):
        author = Author.objects.create(name="Rowling")
        Book.objects.create(title="Harry Potter", author=author)
        url = reverse("admin_select_filter:options")

        response = admin_client.get(
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

    def test_options_returns_select2_results_for_choice_filter(self, admin_client):
        Book.objects.create(title="Dune", genre="fiction")
        url = reverse("admin_select_filter:options")

        response = admin_client.get(
            url,
            {
                "app_label": "testapp",
                "model_name": "book",
                "parameter_name": "genre",
                "q": "Fic",
            },
        )

        assert response.status_code == 200
        results = response.json()["results"]
        assert results == [
            {"id": "__all__", "text": "All"},
            {"id": "fiction", "text": "Fiction"},
        ]
