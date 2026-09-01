"""DTOs that are not specific to one domain."""

from ozon_mcp.models.base import OzonModel


class WriteResult(OzonModel):
    """The outcome of a change to the account.

    Ozon answers a mutation with a page fragment and reports no refusal in it:
    an unknown SKU, a quantity beyond stock and a successful change all come
    back identical. So ``ok`` is never taken from that answer — either the
    change is read back and ``ok`` states what was actually found, or the tool
    says in ``detail`` how to verify it. A transport or auth failure raises
    instead of returning.
    """

    ok: bool = True
    detail: str | None = None
