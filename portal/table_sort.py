"""Allowlisted list ordering and query links that retain the current scope."""

from django.db.models import F


class TableSort:
    def __init__(self, request, columns):
        # key, visible label, database field, inverse numeric priority rank
        self.params = request.GET.copy()
        self.key = request.GET.get("sort", "priority")
        self.direction = request.GET.get("direction", "desc" if self.key == "priority" else "asc")
        choices = {key: (field, inverse) for key, label, field, inverse in columns}
        if self.key not in choices or self.direction not in {"asc", "desc"}:
            raise ValueError("Unsupported sort")
        field, inverse = choices[self.key]
        descending = (self.direction == "desc") != inverse
        self.order = F(field).desc(nulls_last=True) if descending else F(field).asc(nulls_last=True)
        self.headers = []
        for key, label, field, inverse in columns:
            active = key == self.key
            direction = (
                ("asc" if self.direction == "desc" else "desc")
                if active
                else ("desc" if key == "priority" else "asc")
            )
            self.headers.append(
                {
                    "label": label,
                    "url": self.url(sort=key, direction=direction, page=None),
                    "aria_sort": ("descending" if self.direction == "desc" else "ascending")
                    if active
                    else "none",
                    "active": active,
                    "arrow": ("↓" if self.direction == "desc" else "↑") if active else "↕",
                }
            )

    def url(self, **changes):
        params = self.params.copy()
        for key, value in changes.items():
            if value is None:
                params.pop(key, None)
            else:
                params[key] = value
        return "?" + params.urlencode()

    def context(self, page):
        return {
            "sort_headers": self.headers,
            "sort_key": self.key,
            "sort_direction": self.direction,
            "previous_url": self.url(page=page.previous_page_number()) if page.has_previous() else "",
            "next_url": self.url(page=page.next_page_number()) if page.has_next() else "",
        }
