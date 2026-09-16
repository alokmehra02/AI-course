# Interview Script — Social KYC / Ownership Verification (Consented)

**Website:** Confirm applicant owns declared social accounts; case-ready report.  
**Round:** ~60 min LLD + Python  
**Patterns:** State · Facade

---

## PART 0 — Opening (say)

> “I’ll design Phyllo Social KYC: an applicant claims handles, proves ownership by connecting accounts via official login, and we transition a verification case through a State machine to VERIFIED, FAILED, or NEEDS_REVIEW. Then I’ll code KycService.”

**Restate:**

> “Matching a public handle is weak. Real proof is consented Connect — OAuth shows they control the account. We’ll produce a timestamped case status for lending, hiring, or immigration workflows. OK?”

---

## PART 1 — Clarifiers (ask)

> “1. Proof method — Connect/OAuth mandatory for v1?  
> 2. Partial match behavior — NEEDS_REVIEW?  
> 3. One-time case or continuous monitoring?  
> 4. Report artifact required in v1 or status API enough?”

**Assume:**

> “OAuth/connect proof, partial → NEEDS_REVIEW, one-time case, status + notes enough for interview; PDF report later.”

---

## PART 2 — Requirements (say)

> “Functional: create case with claims, attach ownership proofs, evaluate, get case.  
> Non-functional: illegal state transitions rejected, auditable notes/timestamps, multi-tenant.”

---

## PART 3 — Design + patterns (say)

> “**Facade:** KycService.  
> **State:** explicit ALLOWED_TRANSITIONS so we never jump FAILED → VERIFIED silently.”

Diagram:
```text
OPEN ──► VERIFIED
  │
  ├──► FAILED
  └──► NEEDS_REVIEW ──► VERIFIED / FAILED
```

**Entities:** `VerificationCase`, `ClaimedAccount`, `ConnectedAccount`  
**API:**
```text
POST /v1/kyc/cases
POST /v1/kyc/cases/{id}/claims
POST /v1/kyc/cases/{id}/proofs   # after Connect webhook
GET  /v1/kyc/cases/{id}
GET  /v1/kyc/cases/{id}/report   # stretch
```

**Flow:**
1. Create case OPEN with claimed (platform, handle)  
2. Applicant connects → attach ConnectedAccount proof  
3. Evaluate overlap of claims vs proofs  
4. All match → VERIFIED + verified_at  
5. None → FAILED  
6. Some → NEEDS_REVIEW  

---

## PART 4 — Transition to code (say)

> “I’ll code status enum, transition table, case models, and KycService.evaluate / _transition.”

---

## PART 5 — CODE

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
        case = VerificationCase(case_id, applicant_id, claims=list(claims))
        self._cases[case_id] = case
        return case

    def attach_proof(self, case_id: str, proof: ConnectedAccount) -> VerificationCase:
        case = self._cases[case_id]
        case.proofs.append(proof)
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
            return self._transition(case, CaseStatus.FAILED, "no overlapping ownership proof")
        return self._transition(
            case, CaseStatus.NEEDS_REVIEW, f"partial {matched}/{len(case.claims)}"
        )

    def get(self, case_id: str) -> Optional[VerificationCase]:
        return self._cases.get(case_id)

    def _transition(self, case: VerificationCase, new_status: CaseStatus, notes: str) -> VerificationCase:
        if new_status != case.status and new_status not in ALLOWED_TRANSITIONS[case.status]:
            raise ValueError(f"illegal transition {case.status} -> {new_status}")
        case.status = new_status
        case.notes = notes
        return case


if __name__ == "__main__":
    svc = KycService()
    svc.create_case(
        "case_1",
        "appl_1",
        [ClaimedAccount("instagram", "MayaMakes"), ClaimedAccount("youtube", "MayaTech")],
    )
    svc.attach_proof(
        "case_1",
        ConnectedAccount("instagram", "mayamakes", "ig_1", datetime.utcnow()),
    )
    mid = svc.get("case_1")
    assert mid is not None and mid.status == CaseStatus.NEEDS_REVIEW
    svc.attach_proof(
        "case_1",
        ConnectedAccount("youtube", "MayaTech", "yt_1", datetime.utcnow()),
    )
    done = svc.get("case_1")
    assert done is not None and done.status == CaseStatus.VERIFIED
```

### Say while coding

> “Handle compare is case-insensitive.”  
> “State table blocks illegal jumps.”  
> “Facade keeps API simple: create, attach_proof, get.”  
> “verified_at supports case-ready audit.”

---

## PART 5B — Logic explained (say this if they ask “how does verification decide?”)

### Core idea

```text
claims  = what applicant says they own   (platform, handle)
proofs  = what Connect/OAuth proved      (platform, handle, external_account_id)
match   = same platform + same handle (case-insensitive)
```

> “Public handle matching alone is weak — anyone can type @maya. Proof comes from official account connect.”

### `evaluate` decision table

```text
matched = number of claims that appear in proof_keys

if no claims           → FAILED
if matched == all      → VERIFIED  (+ set verified_at)
if matched == 0        → FAILED
if 0 < matched < all   → NEEDS_REVIEW
```

**Example:**
- Claims: IG `@MayaMakes`, YT `@MayaTech`  
- Proof only IG `@mayamakes` → matched 1/2 → **NEEDS_REVIEW**  
- Add YT proof → matched 2/2 → **VERIFIED**

### Why case-insensitive handles?

> “Users type MayaMakes; platform returns mayamakes. Lowercasing avoids false NEEDS_REVIEW.”

### `ALLOWED_TRANSITIONS` (State pattern)

```text
OPEN         → VERIFIED | FAILED | NEEDS_REVIEW
NEEDS_REVIEW → VERIFIED | FAILED
VERIFIED     → (none)
FAILED       → (none)
```

> “Terminal states don’t silently flip. If we need to reopen, create a **new case** — keeps audit history clean for lending/immigration.”

### `_transition` guard

```text
if new_status != current AND new_status not in ALLOWED[current]:
  raise ValueError
else set status + notes
```

> “Notes store why we decided — ‘partial 1/2’ — useful for case-ready reporting.”

### When do we call `evaluate`?

> “After every `attach_proof`. First proof may land NEEDS_REVIEW; later proof can promote to VERIFIED. That matches real Connect flows where accounts are linked one-by-one.”

### Facade responsibilities

| Method | Does |
|--------|------|
| `create_case` | OPEN + store claims |
| `attach_proof` | append proof + re-evaluate |
| `get` | read model for API |

> “Callers don’t manipulate status enums directly — they go through the service so transitions stay legal.”

### What we intentionally don’t do in v1

> “No continuous monitoring here — that’s screening. No PDF renderer — status + notes + timestamps are enough to show the LLD; report export is an extension.”

---

## PART 6 — Edge cases (say)

> “No claims → FAILED.  
> Re-evaluate after each proof.  
> Terminal states VERIFIED/FAILED don’t transition further without new case.  
> Privacy: retain proofs per policy; GDPR delete path.  
> Continuous monitoring = screening product, not this KYC core.”

---

## PART 7 — Follow-ups

| Q | Say |
|---|-----|
| Why not public handle match only? | Anyone can claim @maya; Connect proves control |
| State vs just setting status? | Prevents inconsistent history and bugs |
| Cross-platform identity? | Same case binds multiple platform proofs to one applicant |

---

## PART 8 — Close (say)

> “Social KYC is a Facade over claimed vs connected accounts with an explicit State machine. Coded partial and full verification paths with audit timestamps — ownership via consented connect, not public guesswork.”

---

## Timebox

| Min | Do |
|-----|-----|
| 0–8 | Clarify |
| 8–20 | Design + state diagram |
| 20–50 | Code |
| 50–60 | Edges + close |
