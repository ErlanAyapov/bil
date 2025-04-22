# middleware.py
import ipaddress

def get_client_ip(request):
    # X‑Forwarded‑For, если за обратным прокси
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR", "")
    # зачищаем IPv6‑шорткаты вида "::ffff:192.0.2.1"
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError:
        return None


class TrackIPMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        if ip := get_client_ip(request):
            request.META["CLIENT_IP"] = ip   # прокидываем ниже по стэку
        return self.get_response(request)
