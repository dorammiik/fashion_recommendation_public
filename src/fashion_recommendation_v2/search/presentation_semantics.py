"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

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


# ---- presentation_semantics_v57 ----

"""v57 presentation rubric shared by generation and conditional text review."""
PRESENTATION_CRITERIA_V57_presentation_semantics_v57 = """
PHOTO OBSERVATIONS (v57): evaluate the actual target garment independently from the
wearer's body crop. Head/feet/other garments outside the frame do not make the target
partial. Conversely, a visible person does not mean the target garment is full.
Full means the target's relevant complete outline is visible; partial means an actual
target portion is cropped/hidden; uncertain visibility stays unknown. Background removal
is not cropping. Do not infer full/partial from thum_quality or vice versa.
An isolated, spread-out single garment cutout on white/solid background, with no visible
wearer, mannequin or hanger, is product_only + flat_lay + solid. Do not invent an unseen
support. Visible hanger/mannequin/person takes its appropriate observed classification.
Count distinct actual background regions/colors, including wall-floor seams, borders
and visible background objects; ignore the target garment's colors. Natural gradients
and cast shadows on a single surface do not automatically add background colors.
Solid=1, two_color=.4, three_color=.25, multicolor=.1 in v57 scoring; scores are code-owned.
For person, background, support and thum_quality are excluded from Q and the remaining
weights are normalized; product_focus is still evaluated. Keep factual background
observations where visible, not a fabricated solid to compensate for exclusion.

THUM_QUALITY (product_only): judge wrinkles, shape presentation and lighting independently
from visibility/focus, condition, value or relevance. Full visibility or plain background
does not compensate for a real presentation defect; poor focus alone does not imply a
presentation defect. Use only the supplied image, never listing labels to restore color.
met: clear natural shape/color, with no substantial presentation defect. Normal drape,
regular design pleats, elastic-waist gathers, intentional asymmetric/angular silhouette
and gentle design folds are not defects, and need not be downgraded to mostly_met.
mostly_met: minor localized, fixable creases or slight local lighting variation leaving
the garment's overall shape, spread and color readily legible.
partial: material, non-local presentation problems. Examples: conspicuous creasing across
much of the garment; broad deep overlapping/turned-in panels that substantially collapse
spread/volume; support-induced bunching, pulling or sagging hiding the intended lower
outline; substantial regional glare/shadow obscuring texture/color although overall
appearance remains assessable. Distinguish actual collapse from natural flowing drape,
intentional asymmetry or design folds. A hanger alone is no defect. An irregular edge
alone is no defect. Do not invent collapse because the design is flowing/asymmetric.
unmet: severe widespread creasing/distortion or lighting/color loss substantially
prevents understanding the appearance. Severe washed-out main panels, deep shadows or
color casts that prevent reading the main garment color remain unmet even with a neat
outline. Bright lighting, pale color or a white background alone is not a defect.
unknown: insufficient visual evidence to assess presentation; name what is unavailable.
Evidence must state the observed location, extent and effect on shape/color readability.
Do not invent a defect to match a desired grade, or call substantial broad collapse minor.
"""
