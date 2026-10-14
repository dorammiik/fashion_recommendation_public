"""Local persistence adapters."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from fashion_recommendation_v2.storage.preference import PreferenceStore
from fashion_recommendation_v2.storage.preference import StoreConflict
from fashion_recommendation_v2.storage.preference import UserUnavailable

__all__ = ['PreferenceStore', 'StoreConflict', 'UserUnavailable']
