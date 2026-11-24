"""Only for the private Unix-socket deployment: Nginx overwrites X-Real-IP."""

import ipaddress
from django.http import HttpResponseBadRequest


class ClientAddress:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            value = request.META.get("HTTP_X_REAL_IP", "")
            if "%" in value:
                raise ValueError
            request.META["REMOTE_ADDR"] = str(ipaddress.ip_address(value))
        except ValueError:
            return HttpResponseBadRequest("Trusted edge address required")
        return self.get_response(request)
