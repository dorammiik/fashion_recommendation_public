"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- storage ----

"""Local persistence adapters."""
from fashion_recommendation_v2.storage.preference import PreferenceStore
from fashion_recommendation_v2.storage.preference import StoreConflict
from fashion_recommendation_v2.storage.preference import UserUnavailable
__all__ = ['PreferenceStore', 'StoreConflict', 'UserUnavailable']
