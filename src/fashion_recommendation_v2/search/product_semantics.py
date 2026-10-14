"""Role-consolidated implementation; service contracts and behavior are preserved."""
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
