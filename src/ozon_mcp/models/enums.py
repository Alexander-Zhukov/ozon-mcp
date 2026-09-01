"""Closed sets of values, as enums rather than as strings.

These are the values a caller can be handed and has to branch on. As plain
strings they had to be compared against literals spelled out at each site — and
one of them, ``PayAfterReceipt.scope``, decides how much money is charged today.
``StrEnum`` keeps them readable in JSON while making the set itself checkable.
"""

from enum import StrEnum


class PostPaymentScope(StrEnum):
    """How much of an order Ozon will let the buyer pay on receipt."""

    FULL = "full"
    """The whole order can be paid on receipt."""

    PARTIAL = "partial"
    """Only part of it; the rest is charged now."""

    NONE = "none"
    """Not offered for this order."""


class ListKind(StrEnum):
    """The kind of list a product can be filed under."""

    WISHLIST = "wishlist"
    """A вишлист: Ozon's own giftable list, addressed by a numeric id."""

    COLLECTION = "collection"
    """A подборка: curated and publishable, addressed by a uuid."""


class DeliveryMode(StrEnum):
    """How an order reaches the buyer, as Ozon labels the choice."""

    PICKUP = "Самовывоз"
    COURIER = "Курьером"


class LoginStage(StrEnum):
    """Where a two-step login has got to."""

    CODE_REQUESTED = "code_requested"
    """Ozon has sent a one-time code; it goes to submit_login_code()."""

    SIGNED_IN = "signed_in"
    """The code was accepted."""
