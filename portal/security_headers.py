"""Browser policy for local assets; integration views retain their exact frame policy."""

POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; "
    "frame-src 'none'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
)


class BrowserPolicy:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.get("Content-Type", "").split(";", 1)[0].strip().lower() == "text/html":
            # A selected native application's policy includes its approved frame origin.
            response.setdefault("Content-Security-Policy", POLICY)
            response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response
