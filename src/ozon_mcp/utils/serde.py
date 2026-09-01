"""JSON in and out.

Ozon's payloads are large and read on every call, so they go through orjson,
which is also what the convention asks for. Two of its differences from the
stdlib matter here: it emits UTF-8 as it is, so Russian text stays readable
without being asked, and it returns bytes — these wrappers hand back ``str``,
which is what every caller wants.
"""

from typing import Any

import orjson


def dumps(value: Any, *, indent: bool = False) -> str:
    """Compact JSON text; ``indent`` only for files a person may open."""
    return orjson.dumps(value, option=orjson.OPT_INDENT_2 if indent else None).decode()


def loads(text: str | bytes) -> Any:
    """Parse JSON, raising ``ValueError`` on bad input as the stdlib does."""
    try:
        return orjson.loads(text)
    except orjson.JSONDecodeError as error:
        raise ValueError(str(error)) from error
