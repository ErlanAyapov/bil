from django import template

register = template.Library()

@register.simple_tag
def page_window(page_obj, window=7):
    """
    Возвращает скользящее окно страниц.
    Использование в шаблоне:
      {% load pagination %}
      {% page_window page_obj 7 as win %}
    """
    total = page_obj.paginator.num_pages
    current = page_obj.number
    window = max(3, int(window))
    half = window // 2

    start = max(1, current - half)
    end   = min(total, start + window - 1)
    start = max(1, end - window + 1)

    return {
        "range": range(start, end + 1),
        "start": start,
        "end": end,
        "total": total,
    }
