from django.db import models


class Country(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.name


class Author(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RETIRED = "retired", "Retired"

    name = models.CharField(max_length=100)
    country = models.ForeignKey(
        Country,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authors",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, null=True, blank=True
    )

    def __str__(self) -> str:
        return self.name


class Book(models.Model):
    class Genre(models.TextChoices):
        FICTION = "fiction", "Fiction"
        NONFICTION = "nonfiction", "Non-fiction"
        POETRY = "poetry", "Poetry"

    title = models.CharField(max_length=100)
    author = models.ForeignKey(
        Author, on_delete=models.SET_NULL, null=True, blank=True, related_name="books"
    )
    genre = models.CharField(
        max_length=20, choices=Genre.choices, null=True, blank=True
    )

    def __str__(self) -> str:
        return self.title
