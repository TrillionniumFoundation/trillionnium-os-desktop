"""Names and exact payload bytes for a new Documents features fixture.

This value object is not a Main/task/installation authorization. The future
case entry must bind it to a newly qualified Main and its exact once-only plan.
Import and construction do not create paths, helpers, grants, or UI actions.
"""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from types import MappingProxyType

OLD_RUNS = frozenset({'eeff7aa90e47139a', '69814e80ea71f485'})
FINAL_QUALIFICATION = Path('/home/alex/work/pocket4-android-final/qualification')


@dataclass(frozen=True)
class FeaturesNames:
    run_id: str
    evidence_root: Path

    def __post_init__(self):
        if not isinstance(self.run_id, str) or re.fullmatch('[0-9a-f]{16}', self.run_id) is None or self.run_id in OLD_RUNS:
            raise ValueError('EXPLICIT_NEW_DOCUMENTS_FIXTURE_NAME_REQUIRED')
        root = self.evidence_root
        if (not isinstance(root, Path) or root.parent != FINAL_QUALIFICATION
                or re.fullmatch('business-documents-case-[0-9a-f]{32}', root.name) is None):
            raise ValueError('EXPLICIT_NEW_CASE_EVIDENCE_LOCATION_REQUIRED')
        if (len(self.ALPHA_BYTES), len(self.BETA_BYTES)) != (59, 118):
            raise ValueError('ORIGINAL_FEATURE_PAYLOAD_BYTE_LENGTHS_CHANGED')

    def require_kind(self, kind):
        if kind != 'features10':
            raise ValueError('FEATURES10_NAME_BINDING_REQUIRED')
        self.__post_init__()

    @property
    def RUN(self):
        return self.run_id

    @property
    def ROOT(self):
        return self.evidence_root

    @property
    def PACKAGE(self):
        return 'org.droidloom.qa.documents.r12.n' + self.RUN

    @property
    def FOLDER(self):
        return 'Pocket4_DocFeatures_r12_' + self.RUN

    @property
    def SOURCE(self):
        return 'source-' + self.RUN

    @property
    def COPIES(self):
        return 'copies-' + self.RUN

    @property
    def ALPHA(self):
        return 'alpha-' + self.RUN + '.txt'

    @property
    def BETA(self):
        return 'beta-' + self.RUN + '.txt'

    @property
    def APP_LABEL(self):
        return 'Pocket4 Owned Documents ' + self.RUN[:8]

    @property
    def CLIENT_ACTIVITY(self):
        return self.PACKAGE + '.FeaturesActivity'

    @property
    def CLIENT(self):
        return self.PACKAGE, self.CLIENT_ACTIVITY

    @property
    def ALPHA_BYTES(self):
        return ('Pocket4 Documents ' + self.RUN + ' alpha\n中文 café 😀\n').encode('utf-8')

    @property
    def BETA_BYTES(self):
        return ('Pocket4 Documents ' + self.RUN + ' beta\n中文 café 😀\n'
                'Two generated payloads distinguish a correct copy and move.\n').encode('utf-8')

    @property
    def ALPHA_SHA(self):
        return hashlib.sha256(self.ALPHA_BYTES).hexdigest()

    @property
    def BETA_SHA(self):
        return hashlib.sha256(self.BETA_BYTES).hexdigest()

    @property
    def PAYLOAD(self):
        return MappingProxyType({self.ALPHA: (len(self.ALPHA_BYTES), self.ALPHA_SHA),
                                 self.BETA: (len(self.BETA_BYTES), self.BETA_SHA)})

    @property
    def ALLOWED_DIRS(self):
        return frozenset((self.SOURCE, self.COPIES))

    @property
    def ALLOWED_FILES(self):
        return frozenset(self.PAYLOAD) | frozenset(d + '/' + n for d in self.ALLOWED_DIRS for n in self.PAYLOAD)
