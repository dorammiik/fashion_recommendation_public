"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- presentation_semantics_v45 ----
"""v45 Q rubric shared by product generation and conditional text review."""
PRESENTATION_CRITERIA_V45 = """Judge the garment's visible presentation, including wrinkles, shape and lighting.
Being fully in frame, recognizable and having a distinguishable color is NOT
sufficient for met or mostly_met. Judge whether the presentation problems below
are minor/localized, noticeable/material, or severe. Do not average away a
material problem because the background is plain or the color is recognizable.

met: clear, natural overall shape and distinguishable color, without substantial
distracting wrinkles or presentation problems.
mostly_met: only minor, localized creases, small natural folds, or slight lighting
variation; these do not materially disrupt the garment's drape or presentation.
partial: noticeable, non-minor presentation problems, EVEN IF the whole garment,
its general silhouette and broad color remain identifiable. Examples include:
- Multiple conspicuous wrinkles/creases distributed across the torso, lower panel
  or much of the garment, rather than a small isolated crease.
- Bunching around the waist together with uneven lower draping or an irregular
  hem that makes the natural fall/silhouette noticeably difficult to judge.
- Hanger-induced pulling, sagging, stretching or collapsed fabric that visibly
  distorts the intended shape; the outline need not be completely obscured.
- Uneven lighting, glare, casts or deep shadows that obscure color/texture over a
  meaningful region, even if the broad color family can still be identified.
If these noticeable problems are observed, use partial rather than mostly_met;
do not require loss of object recognition or an unidentifiable color for partial.
unknown: insufficient visual evidence to assess presentation; state what is missing.
unmet: severe widespread creasing, strongly distorted/unclear shape or serious
lighting/color ambiguity substantially prevents understanding the appearance.

V3 SHAPE-PRESENTATION CHECK (product_only only):
Assess visible creasing AND whether the garment is sufficiently spread to read
its shape. Smooth fabric and gentle-looking folds do not by themselves establish
good shape presentation. Seeing the entire outer contour is different from seeing
the garment's width, volume and lower outline clearly.

For suspended garments, inspect the side panels from the support points to the
lower edge. Use partial for substantial presentation collapse: broad, deep,
lengthwise folds make side panels turn inward, overlap or hang as narrow columns
over much of the length, so the spread/volume and lower outline are not readily
readable. An uneven, tucked or dangling lower edge can reinforce this finding.
This can be partial EVEN WITHOUT sharp wrinkles, an unrecognizable silhouette,
or an unclear broad color. A fully visible garment on a plain background does
not cancel this loss of shape presentation.

The natural-draping exception means shallow/localized folds with the lateral
spread and lower outline still legible. Do not call deep support-induced panel
collapse 'gentle vertical draping' solely because gravity causes it. Distinguish
intentional, regular design pleats from broad irregular panel overlap using
visible evidence; do not assume either an intended design or an intended fit
from a product title. Elastic-waist gathers, a hanger, sheer fabric, a flowing
design or an asymmetric design alone do not justify partial.

In thum_quality_evidence, state where the panels/folds are visible and whether
they obscure the spread or lower outline. Mostly_met requires a positive visual
reason that any folds are minor and leave these shape cues readable, not merely
'full garment visible' or 'color clear'. If the image only shows a small local
fold and the outline is clear, do not invent collapse to lower the judgment.

A hanger alone is not a defect. Intentional pleats, normal design draping, loose
silhouettes and gentle natural folds alone are NOT reasons for partial. Distinguish
these from disruptive creasing, bunching and uneven sagging using the image.
Evidence must name the observed issue, its location/extent and its effect. If the
evidence describes conspicuous distributed wrinkles or materially uneven draping,
the status must not call those issues merely minor to justify mostly_met.
This judges photo presentation, NOT condition, damage, value or request relevance.
Use visual evidence, never a title/brand/item identity or a metadata-only guess.
Do not claim to know the true color from the listing instead of visual evidence.

Lighting/color-readability check: assess the major garment regions from the image
itself. Clear color and tonal variation without material presentation defects is met;
minor localized reflections/shadows leaving the main color readable are mostly_met;
substantial regional interference with color/texture while the overall appearance is
still assessable is partial. Severe overexposure, color casts/bleeding or deep shadows
that prevent reading the main garment color are unmet. Use unknown only when there
is insufficient visual evidence to assess the presentation problem itself.
Brightness, a white background or pale garment color alone is not a defect. Lighting
that makes color clearer must not trigger unmet. Metadata color labels cannot restore
color readability in the photograph. A complete outline or neatly arranged garment
does not compensate for severe color-readability loss. Record the affected location,
extent and visible effect; do not invent lighting damage from a desired grade.
Representative example (lighting): a pale coat with its main panels washed out by
severe overexposure so color cannot be discerned is unmet. A brightly photographed
coat with clear color and tonal detail is not downgraded solely for bright lighting.
"""
