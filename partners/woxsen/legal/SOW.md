# STATEMENT OF WORK
### Exhibit D to the Master Collaboration Agreement

---

| | |
|---|---|
| **Document Ref** | QUAICU-WU-SOW-2026-D |
| **Version** | 3.0 |
| **Effective Date** | _______________ |
| **Parties** | QUAICU Solutions Private Limited ("QUAICU") and Woxsen University ("Woxsen") |
| **Incorporated into** | Master Collaboration Agreement dated _______________ |

---

## 1. Purpose

This Statement of Work ("SOW") defines the scope of collaboration, deliverable ownership,
and acceptance criteria between QUAICU and Woxsen under the Master Collaboration Agreement
("MCA"). It is the sole reference document for determining what constitutes an Accepted
Deliverable for Royalty eligibility under Schedule X of the MCA.

This SOW is a legal execution framework. Technical specifications, timelines, and
task-level detail are maintained in the Parties' shared project management system and
are not incorporated into this SOW.

---

## 2. Definitions

| Term | Meaning |
|---|---|
| **Platform** | ALIS — Autonomous Institution Management System |
| **Background IP** | Intellectual property developed independently by a Party prior to or outside the scope of this SOW |
| **Accepted Deliverable** | A deliverable that has passed the Acceptance process in Section 6 |
| **Pilot** | Controlled deployment of ALIS at Woxsen for live validation prior to Commercial launch |
| **Pilot-Ready Gate** | The technical readiness criteria in Section 7 |
| **Policy DSL** | QUAICU's declarative rule language stored as structured data in the platform database |
| **Domain Inputs** | Institutional policies, rules, content, and data provided by Woxsen to configure Platform behaviour |

---

## 3. Platform Baseline — QUAICU Background IP

The following components were independently developed by QUAICU prior to the Effective Date
and constitute QUAICU's exclusive Background IP. They carry no Royalty obligation.

**Core Platform**
Authentication, role-based access control, workflow engine, AI gateway, audit ledger,
policy engine, and all supporting infrastructure.

**Operational Modules** *(backend complete; frontend partial)*
Admissions, Academics, Examinations, Finance, HR and Staff, Student Services,
Communication Hub, Reporting and Analytics, Alumni and Placement, Dynamic Process Engine.

**Infrastructure**
Database schema, migrations, AI and LLM runtime, file storage, containerised deployment
stack, CI/CD pipeline, and observability scaffolding.

---

## 4. Scope of Collaboration

The Parties shall collaborate to complete the remaining development of the Platform.
QUAICU shall deliver all engineering, architecture, and infrastructure work.
Woxsen shall contribute Domain Inputs, institutional policies, and the deliverables
specified in Sections 4.2 and 4.3 below.

---

### 4.1 QUAICU Sole Deliverables

QUAICU is solely responsible for the following. Woxsen has no deliverable obligations
for these items.

**(a) Platform Hardening** — security, tenant isolation, encryption, authentication
hardening, task reliability, and payment fault tolerance.

**(b) Go-Live Requirements** — data protection compliance, multi-factor authentication,
observability, fee management integrity, communication APIs, external integrations,
data migration tooling, shadow mode, and load testing.

**(c) New Modules** — regulatory and accreditation engine, quota seat matrix, backup and
disaster recovery, accounting exports, and duplicate detection.

**(d) Frontend — QUAICU-owned screens** — application shell, AI copilot rail, shared
component library, and staff dashboards for Registrar, Finance Officer, Exam Controller,
Admissions, and Policy administration.

**(e) Platform Expansion** — PhD and doctoral research module, re-admission and credit
transfer, convocation management, OBE and CO-PO mapping engine, policy authoring agent,
GST e-invoicing, API versioning, multi-campus model, and localisation framework.

---

### 4.2 Co-Developed Deliverables

For the deliverables below, QUAICU builds all code and infrastructure. Woxsen's
obligation is to provide the Domain Inputs that configure Platform behaviour — policies,
rules, content, and data — and to perform UAT sign-off.

**(a) Edge Case Resolvers** — detection and resolution logic across Admissions, Academics,
Examinations, Finance, and Student Services modules. Woxsen seeds the governing rules
as Policy DSL entries and provides anonymised test data.

**(b) Regulatory Module (E14)** — NAAC evidence dashboard, AQAR compiler, NIRF/AISHE/UGC
returns, and accreditation templates. Woxsen provides criterion-to-field mappings, return
formats, statutory deadlines, and IQAC sign-off.

**(c) Research Module (E15)** — doctoral lifecycle management, committee automation,
supervisor allocation, thesis submission, and ethics committee workflow. Woxsen provides
milestone rules, supervisor policies, research area taxonomy, and REC governance rules.

**(d) Convocation Module (E18)** — degree audit, gold medal algorithm, certificate
printing, and seating. Woxsen provides eligibility policy, ceremony workflow, and
programme booklet format.

**(e) Academic Standards (E17, E20)** — re-admission, credit transfer, and OBE/CO-PO
mapping. Woxsen provides re-admission policy, credit transfer rules, CO-PO mappings for
a minimum of five programmes, and NBA attainment targets.

**(f) Policy Library** — Woxsen seeds a minimum of eight active institutional policies
into the Policy DSL before the Pilot-Ready Gate is verified.

---

### 4.3 Woxsen-Owned Frontend Deliverables

Woxsen is responsible for the following frontend screens. All screens must integrate with
QUAICU's existing API layer and component library without architectural modification.

- Faculty dashboard
- Student dashboard
- HOD dashboard
- NAAC and Regulatory dashboard
- Parent and Guardian portal user interface
- Telugu localisation strings for all student and parent-facing screens

All Woxsen frontend deliverables require UAT sign-off from a minimum of five end-users
per role before submission for acceptance.

---

## 5. Woxsen Obligations

### 5.1 Data and Access

Woxsen shall provide the following within 15 business days of the Effective Date:

- Anonymised student and faculty records sufficient for platform configuration and testing
- Course catalogue and fee transaction history covering a minimum of two academic years
- Read access to Woxsen's existing SIS or ERP for shadow mode divergence measurement
- An on-premises environment meeting the hardware specification separately provided by QUAICU

### 5.2 Domain Inputs

Woxsen shall provide written policies, rules, and workflow documentation for all
Woxsen-owned deliverables within 20 business days of the Effective Date. Delay in
providing Domain Inputs extends Woxsen's corresponding delivery milestone by an equal
number of business days, without penalty to either Party.

### 5.3 Engineering Resources

Woxsen shall maintain adequate qualified engineering and domain resources throughout
the collaboration to fulfil its obligations under this SOW. All Woxsen contributors
must complete QUAICU's Platform onboarding programme before making their first commit.

### 5.4 IP Assignment

Before any contributor's first commit, Woxsen must execute IP Assignment Agreements
for each contributing individual, per Clause 4.5 of the MCA.

---

## 6. Acceptance

### 6.1 Submission Package

For each Woxsen-owned deliverable, Woxsen submits the following to QUAICU:

| Item | Requirement |
|---|---|
| (a) Git commit SHA | Exact commit reference for the deliverable |
| (b) Contribution evidence | Pull request links and authored commit ranges |
| (c) Test suite | Full suite passing with no regressions |
| (d) Sovereignty Test log | Core workflows passing on a network-isolated instance |
| (e) UAT sign-off | Required for all frontend deliverables |
| (f) Domain expert sign-off | Required for E14, E15, E18, and E20 deliverables |

### 6.2 Review and Remedy

QUAICU completes acceptance review within **15 business days** of a complete submission.
A rejected deliverable is accompanied by a written Rejection Report identifying specific
deficiencies. Woxsen has **15 business days** to remediate and resubmit. A second
rejection escalates to the Steering Committee per Clause 8.1 of the MCA.

### 6.3 Performance Thresholds

All deliverables must maintain the following thresholds when integrated into the Platform:

| Metric | Threshold |
|---|---|
| API uptime | 99.5% or above over any 30-day period |
| API response latency (p95) | Under 300 ms at 500 concurrent users |
| System error rate | Under 1% over any 24-hour period |
| Sovereignty Test | Pass on a network-isolated instance |

---

## 7. Pilot-Ready Gate

Pilot deployment at Woxsen is not authorised until the following conditions are formally
verified and signed off by both Parties. This Gate defines readiness criteria and does
not restrict QUAICU's right to initiate Pilot deployment in accordance with the MCA.

- [ ] All QUAICU sole deliverables (Section 4.1) — accepted
- [ ] All co-developed deliverables (Section 4.2) — accepted
- [ ] All frontend screens (Section 4.3) — accepted
- [ ] Woxsen policy library — minimum eight policies seeded
- [ ] Shadow mode — divergence below 2% for five consecutive days
- [ ] Load test — p95 under 300 ms; error rate under 1%

Transition from Pilot to Commercial deployment requires a separate written addendum
executed by both Parties, per Clause 6.5 of the MCA.

---

## 8. Royalty Eligibility

Only the deliverables listed below are eligible for Royalty consideration under Schedule X
of the MCA, when formally accepted as Accepted Deliverables:

| Code | Eligible Deliverable |
|---|---|
| E14 | Regulatory and Accreditation — Woxsen-owned Domain Inputs and stories |
| E15 | PhD and Doctoral Research — Woxsen-owned Domain Inputs and stories |
| E17 | Re-admission and Credit Transfer — Woxsen-owned Domain Inputs and rules |
| E18 | Convocation Management — Woxsen-owned Domain Inputs and stories |
| E20 | OBE and CO-PO Mapping — Woxsen-owned Domain Inputs and stories |
| FE | Frontend screens owned by Woxsen per Section 4.3 |
| PF | Telugu localisation strings |

The Platform Baseline (Section 3), all QUAICU Sole Deliverables (Section 4.1), and all
QUAICU-owned frontend screens (Section 4.1(d)) constitute QUAICU Background IP and
carry no Royalty obligation.

---

## Signatures

By signing below, each Party confirms that this Exhibit D is incorporated into the Master
Collaboration Agreement and governs all development obligations and Royalty determination
for the duration of the collaboration.

&nbsp;

**For QUAICU SOLUTIONS PRIVATE LIMITED**

| | |
|---|---|
| Name | ___________________________ |
| Title | ___________________________ |
| Signature | ___________________________ |
| Date | ___________________________ |

&nbsp;

**For WOXSEN UNIVERSITY**

| | |
|---|---|
| Name | ___________________________ |
| Title | ___________________________ |
| Signature | ___________________________ |
| Date | ___________________________ |

---

*Exhibit D — Statement of Work v3.0 | QUAICU Solutions Private Limited × Woxsen University | March 2026*
