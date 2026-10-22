"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- photo_admission_v59 ----

"""v59 product-only completeness gate; Q scores and person admission are unchanged."""
PHOTO_ADMISSION_V59_photo_admission_v59 = '''Photo admission: person needs full/partial product_focus; product_only needs
product_focus=full AND hanger/mannequin/flat_lay support, solid/two_color background,
and front/side/unknown angle. For product_only, partial or unknown product_focus fails
photo_pass regardless of other photo attributes or thum_quality.'''

@_preserve_function('photo_pass', 'fashion_recommendation_v2.search.photo_admission_v59')
def photo_pass_photo_admission_v59(observation):
    return observation.passes() and (observation.photo_type != 'product_only' or observation.product_focus == 'full')
