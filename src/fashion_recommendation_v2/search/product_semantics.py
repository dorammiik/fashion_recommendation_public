"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- product_semantics_v40 ----

"""Common v40 satisfaction semantics for generation, validation and consumers."""
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import HARD_PASS_STATUSES_v40
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import HARD_FINDING_STATUSES_v40
CONDITION_RULES_v40 = """
Judge each exact request independently, preserving polarity, hard/soft and OR values.
Do not count how many different requirements passed to grade one requirement.
Prefer image_observation ONLY for visually assessable facts when differences in wording,
lighting or broad-versus-specific descriptions can be explained by recorded evidence.
Such explainable differences alone do not force unknown. Never invent a reconciliation.
Important conflicts suggesting a different product/variant, e.g. metadata black versus
image red, are unknown with unresolved_conflict. Both sources red versus requested black
is unmet. Nonvisual facts (brand, audience, exact composition, price etc.) need metadata;
image appearance cannot establish them. Keep both sources and their consistency record.
met: clearly satisfies the request. Black is clearly black; floral is the main pattern
although other motifs coexist; long skirt visibly reaches the ankle. Agreement of both
sources supports met, but missing metadata alone does not prevent met when visual evidence
is clear (e.g. clearly visible floral without a metadata pattern field).
mostly_met: sufficient evidence with a small permitted difference. Requested black may be
black-looking dark gray/dark navy; metadata black with brighter image areas explained by
lighting reflections is also mostly_met under this rubric. Floral recurs as a pattern but
is not dominant or has equal share with other patterns; use partial instead when flowers
are only isolated accents. Long skirt reaches the lower calf but not the ankle.
partial: related elements exist but exceed the permitted difference: ordinary gray for
black, flowers only as isolated accents instead of a pattern, mid-calf length for long.
unmet: clear mismatch: distinctly blue/light blue/purple/yellow/red for black (the explicit
black-looking dark-navy mostly_met exception takes precedence); dots/stripes without flowers
for floral; short length for long. Preserve negative requests when judging satisfaction.
unknown: insufficient evidence or important unresolved source conflict. Examples: cannot
identify whether a motif is floral; cannot establish length because no worn-photo reference
or hem is cropped; metadata black versus image red. Do not infer length from missing views.
The image-priority rule never substitutes for evidence of nonvisual attributes.
For every hard requirement, only met or mostly_met passes. partial/unmet/unknown fails.
Price remains code-owned with its existing exact comparison; no approximate price rule.
OR aggregation: any met -> met; otherwise any mostly_met -> mostly_met; otherwise any unknown
-> unknown; otherwise any partial -> partial; otherwise unmet. Preserve every option.
Hard findings mirror judgments: met=matched, mostly_met=mostly_matched,
partial=partial_match, unmet=clear_mismatch, unknown=insufficient_evidence.
Soft conditions remain recorded and do not become Search admission gates.
"""

@_preserve_function('aggregate_alternatives', 'fashion_recommendation_v2.search.product_semantics_v40')
def aggregate_alternatives_v40(states):
    for status in ('met', 'mostly_met', 'unknown', 'partial'):
        if status in states:
            return status
    return 'unmet'


# ---- product_semantics_v45 ----

"""Shared v45 satisfaction semantics; historical semantics remain reproducible."""
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import HARD_PASS_STATUSES_v40 as HARD_PASS_STATUSES
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import HARD_FINDING_STATUSES_v40 as HARD_FINDING_STATUSES
aggregate_alternatives = aggregate_alternatives_v40
CONDITION_RULES = """
Judge each exact request independently, preserving polarity, hard/soft and OR values.
Do not count how many different requirements passed to grade one requirement.
Prefer image_observation ONLY for visually assessable facts when differences in wording,
lighting or broad-versus-specific descriptions can be explained by recorded evidence.
Such explainable differences alone do not force unknown. Never invent a reconciliation.
Important conflicts suggesting a different product/variant, e.g. metadata black versus
image red, are unknown with unresolved_conflict. Both sources red versus requested black
is unmet. Nonvisual facts (brand, audience, exact composition, price etc.) need metadata;
image appearance cannot establish them. Keep both sources and their consistency record.
First establish whether evidence is sufficient and whether an important source conflict
remains, then grade satisfaction. mostly_met requires sufficient evidence of a permitted
small difference; it is never a substitute for insufficient evidence or low confidence.
Do not add solid-color, single-pattern or exact subtype constraints absent from the request.
For related garment subtypes, judge the user's actual target features: a broad top label
versus a specific top style is not automatically a different-product conflict. Preserve
explicit sleeve/type constraints; a tank and a T-shirt are not universally interchangeable.
A small terminology difference alone neither requires unknown nor guarantees mostly_met.

met: clearly satisfies the request. Black is clearly black; floral is the main pattern
although other motifs coexist; long length is clearly at the ankle or longer with sufficient
evidence. Agreement of both sources supports met, but missing metadata alone does not
prevent met when visual evidence is clear.
mostly_met: sufficient evidence with a small permitted difference. Black-looking dark
gray/dark navy for black, or black-looking near-navy for navy, is permitted; brighter areas
explained by lighting reflections also qualify. Do not extend these near-color allowances
to arbitrary hues. For mixed colors, stripes or prints, the requested color must be the
visually dominant base color to qualify as mostly_met. Floral must be identifiable and
recur as a pattern, even if not dominant or equal in share to other patterns. For long
length, the hem is clearly below the knee within the calf region, including mid-calf.
partial: related elements exist but exceed the permitted difference: ordinary/light gray
for black, light blue for navy, the requested color present only as a secondary color or
print/trim accent, flowers only as isolated accents. For long length, the hem is around
the knee and not clearly below it.
unmet: clear mismatch: distinctly different colors rather than an allowed near-color or
same-family partial match; dots/stripes without flowers for floral; clearly short/mini
length for long. Preserve negative requests when judging satisfaction.
unknown: insufficient evidence or important unresolved source conflict, not merely a
small difference. Use it when floral cannot be identified, length class cannot be
established, or metadata black versus image red suggests different products/options.

Length evidence: background removal (a cutout) is not photo cropping. A product-only image
or minor edge clipping does not by itself make length unknown. Use the visible waistline,
lower silhouette, proportions and valid listing length evidence to establish length class.
Do not infer a wearer's ankle position from garment proportions alone or invent unseen hem.
Record actual clipping/hidden parts honestly in photo observations; condition satisfaction
and photo presentation are separate decisions. Do not use a fixed missing-image percentage.
Judge whether the parts needed to determine length are supported, not the fraction visible.
If the available evidence cannot distinguish the relevant length classes, use unknown;
if it can, use the corresponding satisfaction status, not a confidence downgrade.
Seller labels Long/Maxi/Midi alone do not override sufficiently evidenced observed hem
position or force unknown. If the same product is sufficiently established, grade the
observed length. Additional color/structure conflicts suggesting another option remain
unknown. The image-priority rule never substitutes for evidence of nonvisual attributes.

OR evidence: check whether the source interpretations are both permitted alternatives.
When the same product AND actual sale composition are sufficiently supported and only the
exact permitted alternative is uncertain, that distinction alone does not make the whole
condition unknown. Assign mostly_met to the evidence-supported allowed interpretation(s),
record the bounded ambiguity, and aggregate normally; do not mark all alternatives unknown
and override the aggregate. Never invent support for an alternative. Preserve unknown for
important uncertainty about product/option identity or actual sale contents. If both
sources establish pants outside the allowed dress/skirt-set alternatives, use unmet;
metadata describing a top but an image showing pants is an unresolved source conflict,
so retain unknown rather than treating it as a clear request mismatch.

Elastic waistband evidence: before judging, inspect all supplied title, description and
structured listing aspects for the target attribute. Do not omit explicit title evidence
merely because a dedicated aspect is absent. Cite the actual supplied source field.
Absence of visible elasticity is not evidence of non-elastic construction. A same-product
listing explicitly stating elastic waist, elasticized waistband or hidden elastic,
without important contrary evidence, supports mostly_met when the image cannot confirm
elastic construction. This specific rule takes precedence over general visual uncertainty
or metadata-only met interpretations for this condition. If image evidence clearly
establishes elastic construction and other evidence does not contradict it, use met.
A visible ordinary waistband, stretchy fabric, or a drawstring alone does not establish
elastic construction. Lack of contrary evidence is not positive evidence; without adequate
positive evidence use unknown. Gathering alone may be caused by a drawstring: distinguish
clear elastic construction from an ambiguous gathered waist.
An explicit same-product elastic/non-elastic contradiction remains unknown unless actual
source context establishes that the negative statement concerns another option/product
or an irrelevant passage. Never dismiss it as minor just to admit a product. Preserve both
claims and their source consistency record; do not invent a reconciliation.
When metadata supports elasticity but the image cannot confirm it, lack of visual
confirmation alone is visually_indeterminate, not a confirmed source contradiction.
Length decision check: apply the stated hem-position boundaries to the recorded evidence.
A clearly below-knee calf-region hem is mostly_met, never unmet or unknown solely because
the seller or observation uses Midi. Do not loosen these boundaries to compensate for
incorrect image observations; genuinely insufficient length evidence stays unknown.

For every hard requirement, only met or mostly_met passes. partial/unmet/unknown fails.
Price remains code-owned with its existing exact comparison; no approximate price rule.
OR aggregation: any met -> met; otherwise any mostly_met -> mostly_met; otherwise any unknown
-> unknown; otherwise any partial -> partial; otherwise unmet. Preserve every option.
Hard findings mirror judgments: met=matched, mostly_met=mostly_matched,
partial=partial_match, unmet=clear_mismatch, unknown=insufficient_evidence.
Soft conditions remain recorded and do not become Search admission gates.
"""
from fashion_recommendation_v2.search.product_identity import PRODUCT_IDENTITY_RULES
from fashion_recommendation_v2.search.product_identity import PRODUCT_IDENTITY_EXAMPLE
CONDITION_RULES += PRODUCT_IDENTITY_RULES + PRODUCT_IDENTITY_EXAMPLE


# ---- product_semantics_v57 ----

"""Shared v57 satisfaction semantics; historical semantics remain reproducible."""
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import HARD_PASS_STATUSES_v40 as HARD_PASS_STATUSES_product_semantics_v57
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import HARD_FINDING_STATUSES_v40 as HARD_FINDING_STATUSES_product_semantics_v57

@_preserve_function('aggregate_alternatives', 'fashion_recommendation_v2.search.product_semantics_v57')
def aggregate_alternatives_product_semantics_v57(states):
    """Unknown contributes no grade; all unknown (or no evidence) stays unknown."""
    for status in ('met', 'mostly_met', 'partial', 'unmet'):
        if status in states:
            return status
    return 'unknown'
CONDITION_RULES_product_semantics_v57 = """
Judge each exact request independently, preserving polarity, hard/soft and OR values.
Do not count how many different requirements passed to grade one requirement.
Prefer image_observation ONLY for visually assessable facts when differences in wording,
lighting or broad-versus-specific descriptions can be explained by recorded evidence.
Such explainable differences alone do not force unknown. Never invent a reconciliation.
Important conflicts suggesting a different product/variant, e.g. metadata black versus
image red, are unknown with unresolved_conflict. Both sources red versus requested black
is unmet. Nonvisual facts (brand, audience, exact composition, price etc.) need metadata;
image appearance cannot establish them. Keep both sources and their consistency record.
First establish whether evidence is sufficient and whether an important source conflict
remains, then grade satisfaction. mostly_met requires sufficient evidence of a permitted
small difference; it is never a substitute for insufficient evidence or low confidence.
The explicit cropped-length partial exception below does not change this general rule.
Do not add solid-color, single-pattern or exact subtype constraints absent from the request.
For related garment subtypes, judge the user's actual target features: a broad top label
versus a specific top style is not automatically a different-product conflict. Preserve
explicit sleeve/type constraints; a tank and a T-shirt are not universally interchangeable.
A small terminology difference alone neither requires unknown nor guarantees mostly_met.

met: clearly satisfies the request. Black is clearly black; pattern distribution follows
the dedicated pattern criteria below; long length is clearly at the ankle or longer with sufficient
evidence. Agreement of both sources supports met, but missing metadata alone does not
prevent met when visual evidence is clear.
mostly_met: sufficient evidence with a small permitted difference. Black-looking dark
gray/dark navy for black, or black-looking near-navy for navy, is permitted; brighter areas
explained by lighting reflections also qualify. Do not extend these near-color allowances
to arbitrary hues. For mixed colors, stripes or prints, the requested color must be the
visually dominant base color to qualify as mostly_met. Pattern satisfaction follows the distribution and dominance criteria below. For long
length, the hem is clearly below the knee within the calf region, including mid-calf.
partial: related elements exist but exceed the permitted difference: ordinary/light gray
for black, light blue for navy, the requested color present only as a secondary color or
print/trim accent; pattern partial follows the dedicated criteria below. For long length, the hem is around
the knee and not clearly below it.
unmet: clear mismatch: distinctly different colors rather than an allowed near-color or
same-family partial match; dots/stripes without flowers for floral; clearly short/mini
length for long. Preserve negative requests when judging satisfaction.
unknown: insufficient evidence or important unresolved source conflict, not merely a
small difference. Use it when floral cannot be identified, length class cannot be
established, or metadata black versus image red suggests different products/options.

Length evidence: background removal (a cutout) is not photo cropping. A product-only image
or minor edge clipping does not by itself make length unknown. Use visible waistline, lower silhouette and grounded proportions together with valid
listing length evidence; apply the cropped-length exception below when required parts are missing.
Do not infer a wearer's ankle position from garment proportions alone or invent unseen hem.
Record actual clipping/hidden parts honestly in photo observations; condition satisfaction
and photo presentation are separate decisions. Do not use a fixed missing-image percentage.
Judge whether the parts needed to determine length are supported, not the fraction visible.
If the available evidence cannot distinguish the relevant length classes, use unknown
unless the explicit cropped-length partial exception applies. If it can, use the
corresponding satisfaction status, not a confidence downgrade.
Seller labels Long/Maxi/Midi alone do not override sufficiently evidenced observed hem
position or force unknown. If the same product is sufficiently established, grade the
observed length. Additional color/structure conflicts suggesting another option remain
unknown. The image-priority rule never substitutes for evidence of nonvisual attributes.

PATTERN: judge distribution and visual dominance across the sale product, not merely
whether the requested motif exists. met: the requested pattern consistently forms the
overall pattern across the main areas. mostly_met: it dominates the overall impression,
with small differences confined to limited other-pattern or solid areas. partial: other
patterns or solid areas dominate, a major component lacks the requested pattern, or the
motif is only a localized accent. Clear absence of the requested pattern is unmet;
unidentifiable patterns are unknown. Preserve the condition's original polarity.
In pattern image_observation, record additional visible patterns absent from metadata,
their locations, repetition, arrangement, and primary/secondary roles. Distinguish the
product from background and styling garments. An extra pattern alone is not a source
contradiction. Do not grade by motif size or embroidery versus printing alone; preserve
separate requested size/detail conditions. Use a specifically requested area when given;
otherwise evaluate the actual sale composition, including all garments in a sold set.

PRODUCT TYPE: combine listing names with visible structural features. A matching broad
family or one matching detail alone does not establish the requested specific type.
For example, coat alone does not establish trench coat; judge the structural combination.
A clearly different type is unmet; insufficient distinguishing evidence is unknown.
Important conflicts suggesting different products/options retain unknown rather than
being reclassified as a clear mismatch.

COLOR: observe the dominant image color independently before comparing listing names.
Do not invent blended color names just to reconcile sources. Lighting explanations need
actual visual evidence. When the same product is sufficiently established, a gray-leaning
neutral for a beige request is partial. Do not generalize this allowance to all colors;
important product/variant source conflicts remain unknown.

COAT LENGTH: a grounded waist-length hem is short; a hem reaching the hips is in a longer
category than waist-length short. Do not equate this with long skirt/dress boundaries.
Do not invent wearer-relative positions in product-only images. Record visible extent
and hidden/cropped hems explicitly.
CROPPED-LENGTH EXCEPTION: when metadata explicitly supports the requested length (including
negative short exclusion), but cropping hides the hem or necessary length-defining parts
so image confirmation is impossible, grade that length condition partial. Listing length
labels or measurements alone must not yield met/mostly_met in this case. Record source
consistency as visually_indeterminate, not a proven length contradiction. This is a service
exception for unequal confirmation coverage, not evidence that the garment is actually short.
If metadata also lacks sufficient length evidence, use unknown. Mere background removal or
minor clipping that still permits length determination does not trigger this exception.

SEASON: use both listing season information and image_observation. Record visible thickness,
bulk, coverage, layering/construction and decoration, then explain the supported seasonal
impression. Do not infer fiber composition or actual thermal performance. A matching seller
season label alone does not establish met. met: clear suitability for the requested season
supported by the source evidence. mostly_met: positive suitability evidence with a small
seasonal difference, such as slightly greater apparent thickness. partial: a large difference
between the requested season and visible garment construction, even if the seller lists it.
For autumn, slightly heavier-looking construction may support mostly_met; clearly winter-oriented
heavy construction may support partial. Do not fix grades from one material name or fur trim
alone. Insufficient evidence stays unknown; important product/variant conflicts stay unknown.
Missing metadata alone does not prohibit a grounded seasonal image observation or judgment.

OR evidence: check whether the source interpretations are both permitted alternatives.
When the same product AND actual sale composition are sufficiently supported and only the
exact permitted alternative is uncertain, that distinction alone does not make the whole
condition unknown. Assign mostly_met to the evidence-supported allowed interpretation(s),
record the bounded ambiguity, and aggregate normally; do not mark all alternatives unknown
and override the aggregate. Never invent support for an alternative. Preserve unknown for
important uncertainty about product/option identity or actual sale contents. If both
sources establish pants outside the allowed dress/skirt-set alternatives, use unmet;
metadata describing a top but an image showing pants is an unresolved source conflict,
so retain unknown rather than treating it as a clear request mismatch.

Elastic waistband evidence: before judging, inspect all supplied title, description and
structured listing aspects for the target attribute. Do not omit explicit title evidence
merely because a dedicated aspect is absent. Cite the actual supplied source field.
Absence of visible elasticity is not evidence of non-elastic construction. A same-product
listing explicitly stating elastic waist, elasticized waistband or hidden elastic,
without important contrary evidence, supports mostly_met when the image cannot confirm
elastic construction. This specific rule takes precedence over general visual uncertainty
or metadata-only met interpretations for this condition. If image evidence clearly
establishes elastic construction and other evidence does not contradict it, use met.
A visible ordinary waistband, stretchy fabric, or a drawstring alone does not establish
elastic construction. Lack of contrary evidence is not positive evidence; without adequate
positive evidence use unknown. Gathering alone may be caused by a drawstring: distinguish
clear elastic construction from an ambiguous gathered waist.
An explicit same-product elastic/non-elastic contradiction remains unknown unless actual
source context establishes that the negative statement concerns another option/product
or an irrelevant passage. Never dismiss it as minor just to admit a product. Preserve both
claims and their source consistency record; do not invent a reconciliation.
When metadata supports elasticity but the image cannot confirm it, lack of visual
confirmation alone is visually_indeterminate, not a confirmed source contradiction.
Length decision check: apply the stated hem-position boundaries to the recorded evidence.
A clearly below-knee calf-region hem is mostly_met, never unmet or unknown solely because
the seller or observation uses Midi. Do not loosen these boundaries to compensate for
incorrect image observations; insufficient evidence stays unknown except for the
explicit cropped-length partial exception.

For every hard requirement, only met or mostly_met passes. partial/unmet/unknown fails.
Price remains code-owned with its existing exact comparison; no approximate price rule.
OR aggregation: exclude unknown alternatives from grade aggregation, preserving their
recorded judgments and evidence. Among known grades: any met -> met; otherwise any
mostly_met -> mostly_met; otherwise any partial -> partial; otherwise unmet.
If all alternatives are unknown, the condition is unknown. This is not a vote or
fraction of alternatives. E.g. partial + unknown = partial; unmet + unknown = unmet.
Hard findings mirror judgments: met=matched, mostly_met=mostly_matched,
partial=partial_match, unmet=clear_mismatch, unknown=insufficient_evidence.
Soft conditions remain recorded and do not become Search admission gates.
"""
from fashion_recommendation_v2.search.product_identity import PRODUCT_IDENTITY_RULES as PRODUCT_IDENTITY_RULES_product_semantics_v57
from fashion_recommendation_v2.search.product_identity import PRODUCT_IDENTITY_EXAMPLE as PRODUCT_IDENTITY_EXAMPLE_product_semantics_v57
CONDITION_RULES_product_semantics_v57 += PRODUCT_IDENTITY_RULES_product_semantics_v57 + PRODUCT_IDENTITY_EXAMPLE_product_semantics_v57
CONDITION_RULES_product_semantics_v57 += """
OCCASION (v57): occasion is a visually interpretable use/style judgment, not a purely
metadata-only fact. In image_observation.occasion, describe concrete visible cues
(e.g. collar/structure, garment drape, formality, construction and outfit context),
then the supported style/use interpretation. Never invent comfort, performance or
hidden construction. Do not leave occasion null merely because the image cannot
prove a seller's intended use. Null remains correct when no adequate cues are visible.
Listing occasion labels are supporting evidence, never automatic met. Generic 'any
occasion' alone does not establish travel or vacation suitability. Unless the user
specifies otherwise, travel/vacation means outdoor sightseeing/outing, not lounging
at home. Clearly casual outdoor clothing supports mostly_met for travel/vacation;
formal style supports partial; clearly indoor homewear incompatible with the requested
outdoor outing supports unmet. Strong specific visual/contextual support for the
requested use may support met. For casual and daily requests, use the distinct service definitions below. Do not equate 'Casual' with homewear or treat
a broad Casual label and visible homewear as an automatic different-product conflict.
Judge actual visible clothing: a seller's Travel label cannot override clear homewear.
A real product/variant identity conflict stays unknown/unresolved_conflict; insufficient
visual AND listing evidence stays unknown/insufficient_evidence. mostly_met requires
positive evidence, not a confidence downgrade. For each occasion judgment, reason must
connect observations -> style/use interpretation -> requested context -> status.
Record the actual visible cues in the occasion image observation; binding attribute_keys
then supplies image_evidence. Never claim visual evidence solely from metadata labels.
"""
CONDITION_RULES_product_semantics_v57 += """
DAILY AND CASUAL: preserve the requested attribute and value; these service meanings do
not make theme and occasion interchangeable or create extra user requirements.
Daily means understated, simple clothing suitable for repeated everyday wear. Consider
pattern/decorative intensity and the overall visual impression. met: clearly simple and
understated. mostly_met: generally understated with limited pattern or decorative accents.
partial: strong patterns or large decorations dominate, substantially differing from this
daily direction. For example, a small localized accent may be mostly_met; broad repeated
high-contrast patterns dominating the garment may be partial. Pattern names alone never
fix the grade. A known visual mismatch is partial, not unknown merely because taste varies.
Casual means a low-formality, relaxed-looking style, not proven physical comfort or performance.
met: clearly low-formality relaxed styling. mostly_met: retains a casual character with some
added formality. partial: formal structure/details dominate. Slightly polished tailoring on
casual clothing may support mostly_met; strongly suit-like structure/details may support partial.
Do not automatically infer daily suitability from casual styling. Separate the product's own
features from outfit context; other garments/accessories alone cannot determine its grade.
Use unknown for insufficient evidence, not as a substitute for an observable style difference.
"""
