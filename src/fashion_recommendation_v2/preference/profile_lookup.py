"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- profile_lookup ----

"""Authenticated read-only profile snapshots shared by consumers; no agent dependencies."""
from copy import deepcopy
from pathlib import Path
import json
from fashion_recommendation_v2.preference.interpretation_references import fingerprint
from fashion_recommendation_v2.preference.interpretation_references import validate_references
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import PreferenceProfileV4
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import InterpretationEvidence

@_preserve_function('freeze_bundle', 'fashion_recommendation_v2.preference.profile_lookup')
def freeze_bundle(raw):
    data = deepcopy(raw)
    if data['status'] == 'not_found':
        if data.get('profile') is not None:
            raise ValueError('not_found cannot contain a profile')
        return dict(status='not_found', profile=None, categories={}, evidence_index={}, frozen=None)
    profile = PreferenceProfileV4.model_validate_json(json.dumps(data['profile']))
    evidence = [InterpretationEvidence.model_validate_json(json.dumps(e)) for e in data['evidence_index'].values()]
    if any((e.user_id != profile.user_id or e.occurred_at > profile.as_of for e in evidence)):
        raise ValueError('Profile evidence owner mismatch')
    if any((k != v['evidence_id'] for k, v in data['evidence_index'].items())):
        raise ValueError('Evidence index key mismatch')
    validate_references(profile.interpretations, evidence, data['categories'])
    expected = 'available' if profile.interpretations else 'empty'
    if data['status'] != expected:
        raise ValueError('Profile lookup status disagrees with stored profile')
    data['frozen'] = dict(profile_version=profile.profile_version, interpretation_version=profile.interpretation_version, as_of=data['profile']['as_of'], content_sha256=fingerprint({k: data[k] for k in ('profile', 'categories', 'evidence_index')}))
    return data

@_preserve_class('FileProfileLookup', 'fashion_recommendation_v2.preference.profile_lookup')
class FileProfileLookup:
    """Explicit evaluation adapter: only these fixed files, never the service DB."""

    def __init__(self, folder):
        self.folder = Path(folder)

    def __call__(self):
        profile = json.loads((self.folder / 'profile.json').read_text())
        prepared = json.loads((self.folder / 'prepared_input.json').read_text())
        evidence = json.loads((self.folder / 'evidence.json').read_text())
        return freeze_bundle(dict(status='available' if profile['interpretations'] else 'empty', profile=profile, categories=prepared['categories'], evidence_index={e['evidence_id']: e for e in evidence}))

@_preserve_class('ServiceProfileLookup', 'fashion_recommendation_v2.preference.profile_lookup')
class ServiceProfileLookup:

    def __init__(self, service, authenticated_user_id):
        self.service, self.user_id = (service, authenticated_user_id)

    def __call__(self):
        from fashion_recommendation_v2.preference.interpretation_references import category
        with self.service.store() as store:
            profile, evidence, snapshots = store.read_profile_evidence_snapshot(self.user_id, now=self.service.clock())
            if profile is None:
                return freeze_bundle(dict(status='not_found'))
            categories = {}
            for snapshot in snapshots.values():
                cid, path = category(snapshot)
                if cid:
                    categories[cid] = dict(description=path)
            return freeze_bundle(dict(status='available' if profile.has_features() else 'empty', profile=profile.model_dump(mode='json'), categories=categories, evidence_index={e.evidence_id: e.model_dump(mode='json') for e in evidence}))
