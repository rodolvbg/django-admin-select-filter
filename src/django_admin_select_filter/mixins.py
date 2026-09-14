from __future__ import annotations

from typing import ClassVar


class AdminSelectFilterMixin:
    """Render an admin list filter with the project's Select2 template."""

    template: ClassVar[str] = "admin/filters/select2_filter.html"
