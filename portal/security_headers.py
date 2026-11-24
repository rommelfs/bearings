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
            policy = POLICY
            if getattr(getattr(request, "resolver_match", None), "url_name", None) in {
                "circl-overview",
                "circl-map-location",
            }:
                from .map_configuration import map_options

                origin = map_options()["map_tile_origin"]
                if origin:
                    policy = policy.replace(
                        "img-src 'self' data: blob:;", "img-src 'self' data: blob: " + origin + ";"
                    )
            response.setdefault("Content-Security-Policy", policy)
            response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response
