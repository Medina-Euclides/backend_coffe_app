from django.http import HttpResponseRedirect
from django.urls import Resolver404, resolve


class HttpResponseTemporaryRedirect(HttpResponseRedirect):
    # 307: conserva método y cuerpo en la redirección
    status_code = 307


class AppendSlashMiddleware:
    """Redirige con 307 (sin perder body) POST/PUT/PATCH/DELETE si falta '/'.
    Evita 500/404 confusos en Thunder Client cuando olvidan la barra final.
    """

    WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if request.method in self.WRITE_METHODS and not path.endswith("/"):
            try:
                resolve(path + "/")
            except Resolver404:
                pass
            else:
                new_path = path + "/"
                qs = request.META.get("QUERY_STRING")
                if qs:
                    new_path = f"{new_path}?{qs}"
                return HttpResponseTemporaryRedirect(new_path)
        return self.get_response(request)
