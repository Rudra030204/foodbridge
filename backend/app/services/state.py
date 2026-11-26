"""Listing state machine. Illegal transitions raise HTTP 409."""
from app.core.errors import conflict
from app.db.models import FoodListing

ALLOWED: dict[str, set[str]] = {
    "open": {"claimed", "diverted", "expired", "cancelled"},
    "claimed": {"assigned", "open", "cancelled"},
    "diverted": {"assigned", "open", "cancelled"},
    "assigned": {"picked_up", "claimed", "diverted", "open", "cancelled"},
    "picked_up": {"delivered"},
    "delivered": set(),
    "expired": set(),
    "cancelled": set(),
}
TERMINAL = {"delivered", "expired", "cancelled"}


def can_transition(old: str, new: str) -> bool:
    return old == new or new in ALLOWED.get(old, set())


def transition(listing: FoodListing, new_status: str) -> None:
    """Move a listing to ``new_status`` or raise a 409 ``illegal_transition``."""
    if listing.status == new_status:
        return
    if not can_transition(listing.status, new_status):
        raise conflict("illegal_transition", f"Cannot change listing from '{listing.status}' to '{new_status}'.")
    listing.status = new_status
