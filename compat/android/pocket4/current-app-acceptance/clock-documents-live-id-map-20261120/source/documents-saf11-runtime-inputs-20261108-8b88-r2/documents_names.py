"""Fresh SAF11 names and exact original 87-byte payload expression.

Constructing this value creates no filesystem, package, grant or Main authority.
"""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

QUALIFICATION=Path('/home/alex/work/pocket4-android-final/qualification')
OLD_RUNS=frozenset({'69814e80ea71f485','eeff7aa90e47139a'})

@dataclass(frozen=True)
class SAFNames:
    run_id:str
    evidence_root:Path
    def __post_init__(self):
        if type(self.run_id) is not str or re.fullmatch('[0-9a-f]{16}',self.run_id) is None or self.run_id in OLD_RUNS:
            raise ValueError('NEW_SAF11_FIXTURE_NAME_REQUIRED')
        if (not isinstance(self.evidence_root,Path) or self.evidence_root.parent!=QUALIFICATION
                or re.fullmatch('business-documents-saf-case-[0-9a-f]{32}',self.evidence_root.name) is None):
            raise ValueError('NEW_SAF11_EVIDENCE_ROOT_REQUIRED')
        if len(self.PAYLOAD)!=87:raise ValueError('ORIGINAL_87_BYTE_SAF_PAYLOAD_LENGTH')
    def require_kind(self,kind):
        if kind!='saf11':raise ValueError('EXACT_SAF11_SCOPE_REQUIRED')
        self.__post_init__()
    @property
    def RUN(self):return self.run_id
    @property
    def ROOT(self):return self.evidence_root
    @property
    def PACKAGE(self):return 'org.droidloom.qa.saf.r12.n'+self.RUN
    @property
    def FOLDER(self):return 'Pocket4_SAF_r12_'+self.RUN
    @property
    def CREATED(self):return 'created-'+self.RUN+'.txt'
    @property
    def PROVIDER(self):return 'provider-'+self.RUN+'.txt'
    @property
    def FILES(self):return 'files-ui-'+self.RUN+'.txt'
    @property
    def NAMES(self):return frozenset((self.CREATED,self.PROVIDER,self.FILES))
    @property
    def PAYLOAD(self):return ('Pocket4 SAF fixture '+self.RUN+'\n中文 café 😀 — ContentResolver round trip.\n').encode('utf-8')
    @property
    def PAYLOAD_SHA(self):return hashlib.sha256(self.PAYLOAD).hexdigest()
    @property
    def APP_LABEL(self):return 'Pocket4 Owned SAF '+self.RUN[:8]
    @property
    def CLIENT_ACTIVITY(self):return self.PACKAGE+'.SafActivity'
    @property
    def CLIENT(self):return self.PACKAGE,self.CLIENT_ACTIVITY
    @property
    def CLIENT_ROUTE(self):return self.CLIENT
