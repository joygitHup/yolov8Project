def paginate_qs(qs, request, serializer_class):
    try:
        page = max(int(request.query_params.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(int(request.query_params.get("pageSize", 10)), 1)
    except (TypeError, ValueError):
        page_size = 10
    total = qs.count()
    start = (page - 1) * page_size
    items = qs[start:start + page_size]
    return {
        "list": serializer_class(items, many=True).data,
        "total": total,
        "page": page,
        "pageSize": page_size,
    }
