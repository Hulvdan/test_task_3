import logging

from sqlalchemy_utils import escape_like

log = logging.getLogger()
logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)


def any_is_none(*args):
    return any(arg is None for arg in args)


def any_isnt_none(*args):
    return any(arg is not None for arg in args)


def all_arent_none(*args):
    return not any_is_none(*args)


def sa_column_contains(column, value: str):
    return column.ilike("%{}%".format(escape_like(value)))
