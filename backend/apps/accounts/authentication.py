"""JWT from Authorization header or the httpOnly access cookie (for <img>/<video>/WS)."""
from rest_framework_simplejwt.authentication import JWTAuthentication

ACCESS_COOKIE_NAME = "yolov8_access"


class JWTHeaderOrCookieAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            return result
        raw = (request.COOKIES.get(ACCESS_COOKIE_NAME) or "").strip()
        if not raw:
            return None
        validated = self.get_validated_token(raw)
        return self.get_user(validated), validated


def bearer_token(request) -> str:
    header = request.META.get("HTTP_AUTHORIZATION") or ""
    if header.lower().startswith("bearer "):
        return header.split(" ", 1)[1].strip()
    return (request.COOKIES.get(ACCESS_COOKIE_NAME) or "").strip()


def set_access_cookie(response, token: str, request=None):
    if not token:
        return response
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        token,
        max_age=24 * 3600,
        httponly=True,
        samesite="Lax",
        secure=bool(request and request.is_secure()),
        path="/",
    )
    return response


def clear_access_cookie(response):
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/", samesite="Lax")
    return response
