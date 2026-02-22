"""CareVerify - Pagination"""


def paginate_query(query, page: int, page_size: int):
    offset = (page - 1) * page_size
    return query.range(offset, offset + page_size - 1)