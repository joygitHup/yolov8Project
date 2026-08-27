from rest_framework.views import exception_handler


def _first_message(data):
    if data is None:
        return "请求失败"
    if isinstance(data, dict):
        if "detail" in data:
            return str(data["detail"])
        if "error" in data:
            return str(data["error"])
        for value in data.values():
            return _first_message(value)
    if isinstance(data, (list, tuple)) and data:
        return _first_message(data[0])
    return str(data)


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None
    response.data = {"error": _first_message(response.data)}
    return response
