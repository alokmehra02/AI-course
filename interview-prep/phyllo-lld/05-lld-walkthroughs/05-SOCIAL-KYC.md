# Walkthrough — Social KYC (Consented)

Website: confirm account ownership; case-ready report for lending / immigration / screening.

## Clarify

- Proof = official connect / OAuth, not public handle guess  
- Partial match => NEEDS_REVIEW  

## Design

**Entities:** VerificationCase, ClaimedAccount, ConnectedAccount  

**API:**

```text
POST /v1/kyc/cases
POST /v1/kyc/cases/{id}/claims
POST /v1/kyc/cases/{id}/proofs
GET  /v1/kyc/cases/{id}
```

**Patterns:**

- Facade: KycService  
- State: allowed status transitions  

## Code to write

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class CaseStatus(str, Enum):
    OPEN = "OPEN"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


ALLOWED_TRANSITIONS = {
    CaseStatus.OPEN: {CaseStatus.VERIFIED, CaseStatus.FAILED, CaseStatus.NEEDS_REVIEW},
    CaseStatus.NEEDS_REVIEW: {CaseStatus.VERIFIED, CaseStatus.FAILED},
    CaseStatus.VERIFIED: set(),
    CaseStatus.FAILED: set(),
}


@dataclass
class ClaimedAccount:
    platform: str
    handle: str


@dataclass
class ConnectedAccount:
    platform: str
    handle: str
    external_account_id: str
    connected_at: datetime


@dataclass
class VerificationCase:
    id: str
    applicant_id: str
    claims: list[ClaimedAccount] = field(default_factory=list)
    proofs: list[ConnectedAccount] = field(default_factory=list)
    status: CaseStatus = CaseStatus.OPEN
    verified_at: Optional[datetime] = None
    notes: str = ""


class KycService:
    def __init__(self):
        self._cases: dict[str, VerificationCase] = {}

    def create_case(self, case_id: str, applicant_id: str, claims: list[ClaimedAccount]) -> VerificationCase:
        case = VerificationCase(case_id, applicant_id, claims=claims)
        self._cases[case_id] = case
        return case

    def attach_proof(self, case_id: str, proof: ConnectedAccount) -> VerificationCase:
        self._cases[case_id].proofs.append(proof)
        return self.evaluate(case_id)

    def evaluate(self, case_id: str) -> VerificationCase:
        case = self._cases[case_id]
        if not case.claims:
            return self._transition(case, CaseStatus.FAILED, "no claims")

        proof_keys = {(p.platform, p.handle.lower()) for p in case.proofs}
        matched = sum(
            1 for c in case.claims if (c.platform, c.handle.lower()) in proof_keys
        )

        if matched == len(case.claims):
            case.verified_at = datetime.utcnow()
            return self._transition(case, CaseStatus.VERIFIED, "all claims proved")
        if matched == 0:
            return self._transition(case, CaseStatus.FAILED, "no overlap")
        return self._transition(case, CaseStatus.NEEDS_REVIEW, f"partial {matched}/{len(case.claims)}")

    def _transition(self, case: VerificationCase, new_status: CaseStatus, notes: str) -> VerificationCase:
        if new_status != case.status and new_status not in ALLOWED_TRANSITIONS[case.status]:
            raise ValueError(f"illegal transition {case.status} -> {new_status}")
        case.status = new_status
        case.notes = notes
        return case
```

## Say this

> "Ownership proof needs consented connect. State machine blocks illegal status jumps."
