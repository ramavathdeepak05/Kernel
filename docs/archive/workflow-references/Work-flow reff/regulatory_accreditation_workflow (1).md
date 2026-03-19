# Regulatory & Accreditation Module Workflow
### Full Automation Reference — ALIS OS Module E14
#### Model: AI Builds the Evidence Base. Humans Approve and Submit.
#### QUAICU Pvt. Ltd. | quaicu.org | Hyderabad, India | Confidential

---

## Document Map

This is the capstone module of ALIS OS. It consumes from all six upstream modules
and produces accreditation-ready evidence, regulatory submissions, and live
compliance dashboards.

**Connected documents (upstream data sources):**
- `admissions_workflow.md` — enrollment data, diversity metrics, dropout rates, quota compliance
- `academic_operations_workflow.md` — curriculum data, teaching quality, CO-PO attainment (E20), PhD program data (E15)
- `examination_workflow.md` — result statistics, graduation rates, pass %, distinction %
- `student_services_workflow.md` — placement rates, scholarship disbursements, grievance outcomes, alumni career data, student activity, hostel data
- `finance_workflow.md` — expenditure per student, research grants, fee compliance, income/expenditure heads
- `hr_payroll_workflow.md` — faculty qualifications, PhD %, NET/SLET %, research publications (API Cat III via EC-HR-02 discovery), training completion, sanctioned vs. filled positions

**Cross-references to skill files:**
- Edge cases: `references/edge-cases.md` — EC-REG-01, EC-REG-02, EC-REG-03, EC-REG-04
- Build sequence: `ALIS_BUILD_PLAN.md` — all EC-REG are Sprint 3 (P1 — High/Medium/Low impact)
- Data migration pipeline: `references/architecture.md` §27 — go-live blocker, feeds EC-REG-01
- Shadow mode: `references/architecture.md` §28 — parallel operation before go-live
- E15 PhD module: `references/gaps.md` — `phd.degree_awarded` event feeds RA-2 NIRF GO and RA-5 NBA SAR
- E20 OBE/CO-PO: `references/gaps.md` — CO-PO attainment feeds RA-5 NBA SAR directly

---

## Core Operating Principle

**AI builds the evidence base every day — automatically, from live operational data.**
**Humans approve, narrate, and submit. No compliance season scramble.**

The module operates in three simultaneous modes:
- **Continuous Mode:** AI pulls data from all six modules daily, updates all regulatory
  metrics in real time, and flags any metric deteriorating below target thresholds
- **Preparation Mode:** When an accreditation cycle is approaching, AI assembles SSR /
  data templates, pre-fills all quantitative metrics, and generates gap reports for
  metrics that need human narrative or evidence upload
- **Submission Mode:** AI packages the final submission, runs a pre-submission
  checklist, and manages the post-submission cycle (DVV responses, peer team visit
  preparation, compliance calendar)

**The fundamental principle:** Every metric required by every regulatory body is
mapped to a live data source in one of the six upstream modules. The evidence is
never stale because it is never compiled separately — it is harvested continuously.

---

## Actors

| Actor | Scope of Authority | Escalation Path |
|---|---|---|
| IQAC Coordinator | All 8 regulatory domains — primary operator | Registrar → VC |
| Registrar | UGC filings, statutory compliance, AISHE submission | VC |
| Dean / HOD | Department-level data contribution, NAAC criteria narrative, NBA program data | IQAC Coordinator |
| VC / Management | Final approval on all submissions, SSR sign-off, AQAR approval | Board / Governing Body |
| Finance Officer | Financial data certification for NAAC/NIRF (FM-7 integration) | VC |
| Faculty | Research output data, API scores, FDP completion via HR-4 — not a direct actor in this module | HOD → IQAC |

---

## Module Overview — 8 Regulatory Bodies

| # | Body / Framework | Submission Type | Frequency | Primary Source Modules |
|---|---|---|---|---|
| RA-1 | NAAC Accreditation | IIQA → SSR → DVV → AQAR | 5-year cycle + Annual AQAR | All 6 modules |
| RA-2 | NIRF Rankings | Data template submission | Annual (January window) | Admissions, Academics, Exams, Finance, HR |
| RA-3 | UGC Compliance & Annual Returns | Annual returns + compliance declarations | Annual + event-triggered | Finance, HR, Admissions |
| RA-4 | AICTE Approval (if applicable) | Annual Compliance Report + Extension of Approval | Annual (September window) | Admissions, Academics, HR, Finance |
| RA-5 | NBA Accreditation (program-level) | SAR (Self-Assessment Report) + Tier system | 3-year cycle per program | Academics (E20 OBE), Exams, HR, Student Services |
| RA-6 | AISHE Data Submission | Annual AISHE portal data entry | Annual (October–December window) | Admissions, Academics, HR |
| RA-7 | State Regulatory Body | State university / statutory body annual returns | Annual (varies by state) | All 6 modules |
| RA-8 | IQAC | AQAR (Annual Quality Assurance Report) | Annual — July 31 | All 6 modules |

---

## The Evidence Engine — Live Data Harvest from All 6 Modules

This is the foundational design of the Regulatory module. AI does not compile
compliance data at submission time. It harvests it continuously.

### Evidence Source Mapping

| Regulatory Metric | Source Module | Specific Data Point | Update Frequency |
|---|---|---|---|
| Student enrollment (total, category-wise, program-wise) | Admissions | `student.enrolled` events + roll records | Real-time |
| Student-to-faculty ratio | Admissions + HR | Enrolled / sanctioned faculty count | Daily |
| Pass %, first class %, distinction % | Examinations | SGPA/CGPA records, result publication data | Post-result |
| Placement statistics (% placed, avg CTC, sector-wise) | Student Services SS-3 | `offer.received` + placement dashboard | Real-time |
| Graduate employment categorization | Student Services SS-8 | `GraduationEmploymentDeclaration` (EC-REG-04) | On graduation |
| Dropout / attrition rate | Admissions + Exams | `student.cancelled` + backlog history | Monthly |
| Scholarship disbursement (% receiving aid) | SS-4 + Finance FM-2 | `scholarship.disbursed` events | Real-time |
| Faculty qualifications (PhD %, NET/SLET %, experience) | HR HR-1, HR-2 | Employee master + qualification data | Real-time |
| Faculty-to-student ratio (program-wise) | HR + Admissions | `employee_department_assignments` (EC-HR-03) | Daily |
| Research publications (Scopus/SCI/UGC-listed) | HR HR-4 | API Cat III — `PublicationDiscoveryService` (EC-HR-02) | Weekly |
| Patents filed / granted | HR HR-4 | Patent records in employee profile | On submission |
| Sponsored research funding | HR HR-4 + Finance FM-6 | Project grants received | On receipt |
| PhD scholars enrolled / graduated | Academics + Exams | PhD enrollment + `phd.degree_awarded` (E15) | Per event |
| Expenditure per student | Finance FM-7 | Total expenditure / enrolled students | Annual |
| Expenditure on academic activities (%) | Finance FM-7 | Academic budget vs. total budget | Annual |
| Library holdings (books, journals, e-resources) | Student Services SS-2 | Catalogue count + subscriptions | Real-time |
| ICT infrastructure (classrooms, labs, internet) | Infrastructure (manual — gap module) | Asset register | Annual |
| Student grievances resolved (% and timeline) | Student Services SS-5 | `grievance.closed` event data | Real-time |
| Alumni employment outcomes | Student Services SS-8 | `GraduationEmploymentDeclaration` + annual survey | On graduation + annual |
| Faculty training / FDP / UGC mandatory programmes | HR HR-5 | `training.completed` events | Real-time |
| Fee collection vs. sanctioned fee | Finance FM-1 | Fee schedule + collection data | Real-time |
| Hostel occupancy and facilities | Student Services SS-1 | Hostel room records | Real-time |
| Diversity metrics (SC/ST/OBC/Women %) | Admissions + HR | Category-wise enrollment + employee records | Real-time |
| CO-PO attainment levels (program-wise) | Academics (E20 OBE) | `co_attainment_records` table | Weekly |
| Student satisfaction survey scores | Academics + SS-7 internal | Feedback data | Semester |

### `regulatory_metrics` — The Central Ledger

All harvested data lands in a single table. Every row carries a provenance flag.
This is the master data store the entire evidence engine reads from.

```sql
CREATE TABLE regulatory_metrics (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL,
    metric_key     TEXT NOT NULL,        -- 'student_enrollment_count', 'pass_percentage', etc.
    academic_year  TEXT NOT NULL,        -- '2021-22', '2022-23', etc.
    value          DECIMAL(15,4),
    data_source    TEXT NOT NULL
        CHECK (data_source IN (
            'live_module',              -- pulled from operational module data
            'legacy_import',            -- migrated from pre-ALIS records
            'manual_entry',             -- IQAC coordinator direct entry
            'estimated'                 -- AI-estimated with low confidence
        )),
    confidence     TEXT DEFAULT 'HIGH'
        CHECK (confidence IN ('HIGH', 'MEDIUM', 'LOW', 'MISSING')),
    evidence_docs  JSONB DEFAULT '[]',   -- attached scanned proofs
    imported_by    UUID,
    verified_by    UUID,                 -- IQAC Coordinator who verified
    notes          TEXT,
    created_at     TIMESTAMPTZ DEFAULT now()
);

-- Gap report view — drives the dashboard Red/Amber/Green rendering
CREATE VIEW regulatory_metrics_gap_report AS
SELECT
    metric_key,
    academic_year,
    value,
    CASE
        WHEN data_source = 'live_module'
            THEN 'VERIFIED'
        WHEN data_source = 'legacy_import' AND verified_by IS NOT NULL
            THEN 'IMPORTED_VERIFIED'
        WHEN data_source = 'legacy_import' AND verified_by IS NULL
            THEN 'IMPORTED_UNVERIFIED'
        WHEN data_source = 'manual_entry'
            THEN 'MANUAL_ENTRY'
        WHEN confidence = 'MISSING'
            THEN 'MISSING'
        ELSE 'UNKNOWN'
    END AS data_quality,
    evidence_docs
FROM regulatory_metrics;
```

**Dashboard rendering rule:** Only `VERIFIED` (live_module) data points render in
green with full confidence. All other sources render with a visible provenance badge.
Missing data points render red with an inline upload button — the IQAC coordinator
can attach scanned legacy documents directly to the metric cell. Every non-`live_module`
data point in the SSR auto-compilation gets a footnote indicating source and confidence.

---

## NAAC Readiness Score Computation

The readiness score is the system's single most important output — it answers
"what NAAC grade would we get if assessed today?". It is computed daily and
displayed as the primary metric on the IQAC dashboard.

### Score Architecture

Each of the 7 NAAC criteria has a weighted target score band. The readiness score
per criterion is computed from the live metrics feeding that criterion.

```python
NAAC_CRITERIA_WEIGHTS = {
    "C1_Curricular_Aspects":                  10.0,   # % of total CGPA
    "C2_Teaching_Learning_Evaluation":         30.0,
    "C3_Research_Innovations_Extension":       20.0,
    "C4_Infrastructure_Learning_Resources":    10.0,
    "C5_Student_Support_Progression":          10.0,
    "C6_Governance_Leadership_Management":     15.0,
    "C7_Institutional_Values_Best_Practices":   5.0,
}

TARGET_CGPA_THRESHOLDS = {
    "A++": 3.76,
    "A+":  3.51,
    "A":   3.26,    # default target — configurable per institution
    "B++": 3.01,
    "B+":  2.76,
}

def compute_naac_readiness_score(tenant_id: UUID, as_of_date: date) -> NAACSelfAssessment:
    scores = {}
    for criterion, weight in NAAC_CRITERIA_WEIGHTS.items():
        raw_metrics = get_live_metrics_for_criterion(criterion, tenant_id, as_of_date)
        criterion_score = compute_criterion_score(raw_metrics, criterion)
        scores[criterion] = CriterionScore(
            raw_score=criterion_score,
            weighted_contribution=criterion_score * (weight / 100.0),
            data_completeness=compute_completeness(raw_metrics),
            amber_flags=[m for m in raw_metrics if m.status == "AMBER"],
            red_flags=[m for m in raw_metrics if m.status == "RED"],
        )
    total_cgpa_estimate = sum(s.weighted_contribution for s in scores.values())
    projected_grade = classify_grade(total_cgpa_estimate)
    return NAACSelfAssessment(
        tenant_id=tenant_id,
        as_of_date=as_of_date,
        criterion_scores=scores,
        total_cgpa_estimate=total_cgpa_estimate,
        projected_grade=projected_grade,
        data_quality_score=compute_overall_data_quality(scores),
    )
```

**Amber / Red threshold rule (configurable per institution):**
- **Amber:** Metric is >10% below the score required for target NAAC grade
- **Red:** Metric is >25% below the score required for target NAAC grade
- A Red flag on any criterion triggers an immediate notification to the VC —
  not just the IQAC dashboard

**Important caveat surfaced in dashboard:** The readiness score is an AI estimate,
not a NAAC assessment. It is computed from the institution's own data and may not
perfectly mirror NAAC's scoring methodology, which includes peer evaluation and
qualitative assessment. The dashboard shows this caveat on every readiness score panel.

---

## RA-1: NAAC Accreditation

**Trigger:** First cycle — institution applies after 6 years of operation and
2 graduated batches. Subsequent cycles — 6 months before accreditation validity
expires. AQAR — Annual (July 31 submission deadline).

### NAAC Assessment Framework (7 Criteria — University Manual)

| Criterion | Key Focus | Weightage | Primary Source Modules |
|---|---|---|---|
| C1: Curricular Aspects | Program design, NEP alignment, CBCS, curriculum revision | 10% | Academics |
| C2: Teaching-Learning & Evaluation | Pedagogy, faculty qualifications, student diversity, assessment methods | 30% | Academics, HR, Admissions, Exams |
| C3: Research, Innovations & Extension | Publications, patents, funded projects, MoUs, extension activities | 20% | HR (API Cat III), Finance (research grants) |
| C4: Infrastructure & Learning Resources | Classrooms, labs, library, ICT, hostel, sports | 10% | SS-2 Library, SS-1 Hostel, manual infra data |
| C5: Student Support & Progression | Scholarships, placement, alumni, grievance, career guidance | 10% | SS-3 Placement, SS-4 Scholarships, SS-5 Grievance, SS-8 Alumni |
| C6: Governance, Leadership & Management | Academic governance, financial management, IQAC, HR policies | 15% | Finance FM-7, HR all domains, IQAC records |
| C7: Institutional Values & Best Practices | Gender equity, environment, inclusivity, best practices | 5% | Admissions (diversity), HR (POSH), SS-5 Grievance |

### NAAC Grading Scale

| CGPA Range | Grade | Status |
|---|---|---|
| 3.76 – 4.00 | A++ | Accredited — Very Good |
| 3.51 – 3.75 | A+ | Accredited — Very Good |
| 3.26 – 3.50 | A | Accredited — Good |
| 3.01 – 3.25 | B++ | Accredited — Good |
| 2.76 – 3.00 | B+ | Accredited — Satisfactory |
| 2.51 – 2.75 | B | Accredited — Satisfactory |
| 2.01 – 2.50 | C | Accredited — Pass |
| Below 1.51 | — | Not Accredited |

### NAAC Process Stages

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 1.1 | AQAR Continuous Compilation | Year-round: compiles AQAR data from all 6 modules. Updates quantitative metrics monthly. Flags metrics below target. Generates AQAR draft by June 30. All metrics sourced from `regulatory_metrics` table with provenance flags. | IQAC Coordinator reviews and adds qualitative narrative (1,000–1,500 words per criterion per NAAC format). VC approves. | AQAR submitted to NAAC portal by July 31. Published on institution website. | Annual — July 31 deadline |
| 1.2 | IIQA Preparation | On decision to apply: compiles IIQA data (institution profile, programs, faculty count, infrastructure). Pre-fills all quantitative fields from live module data. Runs eligibility check (6 years operation, 2 batches graduated). | Registrar reviews. VC signs declaration. IQAC Coordinator submits. | IIQA submitted. Registration fee processed via Finance FM-4. | 15 days before window closes |
| 1.3 | SSR Quantitative Compilation | On IIQA acceptance: pulls all quantitative metric data for 5-year lookback from `regulatory_metrics` table. Populates NAAC data templates for all 7 criteria. Uses EC-REG-01 provenance flags to surface data quality gaps. Computes preliminary CGPA estimate (self-assessment). Generates gap report: metrics needing evidence documents or human narrative. | IQAC Coordinator reviews gap report. Assigns criteria-wise narrative writing to Deans/HODs. | SSR quantitative section complete. Gap report distributed. | Within 30 days of IIQA acceptance |
| 1.4 | SSR Qualitative Narrative | AI drafts criterion-wise qualitative narrative using SWOC framework (Strengths-Weaknesses-Opportunities-Challenges). Pre-fills known institutional achievements from event logs (last 5 years). Provides 1,000–1,500 word drafts per criterion per NAAC format. | Dean/HOD refines narrative per criterion. IQAC Coordinator consolidates. VC approves final SSR. | SSR qualitative section complete. | 45 days (parallel writing across criteria) |
| 1.5 | Evidence Document Packaging | Generates criterion-wise evidence index. Downloads and bundles from all modules: result sheets (Exams), appointment letters (HR), fee receipts (Finance), placement offer letters (SS-3), scholarship records (SS-4), grievance closure reports (SS-5), training certificates (HR-5), CO-PO attainment data (Academics E20). Creates named PDF/folder structure per NAAC evidence numbering convention. | IQAC Coordinator verifies evidence package. Adds physical documents (infrastructure photos, lab certifications) manually. | Evidence package complete. Criterion-wise hyperlinked index generated. | 15 days |
| 1.6 | SSR Submission | Runs pre-submission checklist: all mandatory metrics filled, evidence documents linked, word count within limits, declaration format correct. Uses active `regulatory_report_templates` record (EC-REG-02) — never cached. Generates submission-ready SSR. | VC signs declaration. IQAC Coordinator uploads to NAAC portal. | `naac.ssr_submitted` event. Submission timestamp recorded. | Before NAAC deadline |
| 1.7 | DVV Response Management | NAAC sends Data Validation and Verification queries (7-day statutory window). AI parses DVV queries, identifies which module data is questioned, retrieves raw evidence from `regulatory_metrics` table with provenance. Drafts response with supporting evidence. | IQAC Coordinator reviews and approves DVV responses. Submits within 7-day window. | DVV responses submitted. Pre-qualifier score calculated by NAAC. | 7 days per DVV round (statutory) |
| 1.8 | Student Satisfaction Survey (SSS) | Coordinates SSS via student portal. Manages reminder sequence to achieve ≥70% response rate (NAAC minimum). Compiles results. Generates SSS outcome report. | IQAC Coordinator monitors response rates. Escalates if below 50% after initial send. | SSS completed. Results submitted to NAAC. | Per NAAC schedule (post-DVV) |
| 1.9 | Peer Team Visit Preparation | Generates peer team visit pack: institution profile, criterion-wise achievement summary, campus tour schedule, department visit schedule, faculty and student interaction schedules, evidence room index. Briefing documents for VC, Deans, IQAC. | VC leads peer team reception. IQAC Coordinator manages all visit logistics. Dean/HOD present department briefs. Internal mock peer team session 2 weeks before. | Visit pack distributed. Mock session conducted. | 30 days before visit |
| 1.10 | Post-Accreditation Compliance | On grade award: updates institution profile with grade, validity period, next cycle trigger date. Sets AQAR reminder for next July. Sets preparation mode trigger (6 months before validity expiry). Publishes grade on institution website (UGC self-disclosure mandate). | VC communicates grade to Board. | Grade published. `accreditation.renewed` event. Next cycle calendar set. | Within 7 days of grade announcement |

---

## RA-2: NIRF Rankings

**Trigger:** Annual — NIRF data submission window opens November–December.

### NIRF Parameter Framework

| Parameter | Weightage | Sub-metrics | Source Module |
|---|---|---|---|
| Teaching, Learning & Resources (TLR) | 30% | Faculty count, PhD faculty %, student-faculty ratio, expenditure per student | HR, Finance, Admissions |
| Research & Professional Practice (RP) | 30% | Publications (Scopus/SCI), citations, patents, sponsored research, PhD graduates | HR API Cat III, Finance (grants), E15 PhD module |
| Graduation Outcomes (GO) | 20% | PhD awarded, graduation rate, placement rate, higher studies % | Exams, SS-3 Placement, `GraduationEmploymentDeclaration` (EC-REG-04) |
| Outreach & Inclusivity (OI) | 10% | SC/ST/OBC/Women student %, differently abled %, economically disadvantaged %, outreach programs | Admissions, SS-4 Scholarships, SS-6 Events |
| Perception (PR) | 10% | Academic peer perception, employer perception (third-party survey) | External — manual input |

**GO parameter note (EC-REG-04):** The Graduation Outcomes parameter requires
accurate placement/higher studies/entrepreneurship categorization. The
`GraduationEmploymentDeclaration` mandatory decision tree (see below) is what
makes NIRF GO data auditable. Without it, self-reported data is unverifiable.

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 2.1 | Year-Round Metric Tracking | Continuously updates NIRF dashboard with all 5 parameter scores from live module data. Shows projected NIRF score and year-on-year delta. Flags parameters with declining scores with specific improvement actions. | IQAC Coordinator reviews quarterly NIRF performance report. | Live NIRF score estimate available. Quarterly improvement report generated. | Continuous (auto) |
| 2.2 | Annual Data Compilation | On window opening: auto-populates NIRF data template using active `regulatory_report_templates` record (EC-REG-02). Cross-references research publications with Scopus/Web of Science databases. Computes all sub-metric scores. For GO parameter: reads from `graduation_employment_declarations` table (EC-REG-04). | IQAC Coordinator reviews template. Finance Officer certifies financial data. VC approves submission. | NIRF data template complete. | 10 days after window opens |
| 2.3 | Submission & Verification | Runs completeness check on data template. Flags missing or anomalous values. Generates submission summary with year-on-year comparison. | IQAC Coordinator submits on NIRF portal. VC signs digital declaration. | `nirf.submitted` event. Confirmation recorded. | Before window closes (typically December) |
| 2.4 | Ranking Outcome Tracking | On ranking announcement: records rank, score, parameter-wise performance. Compares with previous year. Generates gap analysis: parameters improved, declined, specific metrics to target. | VC reviews ranking outcome. Shares with Board. | Ranking outcome stored. Next year improvement plan generated. | Within 7 days of release |

### EC-REG-04 — Ambiguous Graduate Employment Categorization (P1 — Sprint 3)

**Trigger:** Student graduates and joins family business. NIRF requires specific
proof categories. The system doesn't know whether to classify this as placement,
entrepreneurship, higher studies, or unemployed. Wrong classification fails the
external DVV audit.

**What breaks:** NIRF placement rate is incorrect. DVV finds discrepancies.
Rankings are penalised. Alumni portal is created with wrong data on record.

**Fix: Mandatory `GraduationEmploymentDeclaration` decision tree**

The declaration cannot be bypassed. The Alumni portal account is not created and
the degree certificate is not downloadable until the declaration is submitted.
This is enforced as a prerequisite gate in the `AlumniTransitionSaga`
(see `student_services_workflow.md` SS-8).

```python
class GraduationEmploymentStatus(str, Enum):
    PLACED_EMPLOYED           = "placed_employed"           # joining a company
    HIGHER_STUDIES            = "higher_studies"            # continuing education
    ENTREPRENEURSHIP_OWN      = "entrepreneurship_own"      # own startup
    ENTREPRENEURSHIP_FAMILY   = "entrepreneurship_family"   # family business
    GOVERNMENT_EXAM_PREP      = "government_exam_prep"      # UPSC/SSC/banking prep
    NOT_SEEKING_YET           = "not_seeking_yet"           # gap year / personal
    SEEKING_EMPLOYMENT        = "seeking_employment"        # actively looking

class GraduationEmploymentDeclaration(BaseModel):
    student_id: UUID
    status: GraduationEmploymentStatus
    # Conditional required fields — enforced by validation:
    employer_name: str | None          # required if PLACED_EMPLOYED
    employer_cin: str | None           # required if PLACED_EMPLOYED
    offer_letter_url: str | None       # required if PLACED_EMPLOYED
    ctc_lpa: Decimal | None            # required if PLACED_EMPLOYED
    institution_name: str | None       # required if HIGHER_STUDIES
    program: str | None                # required if HIGHER_STUDIES
    startup_name: str | None           # required if ENTREPRENEURSHIP_OWN
    startup_cin_or_gstin: str | None   # required if ENTREPRENEURSHIP_OWN
    family_business_gstin: str | None  # required if ENTREPRENEURSHIP_FAMILY
    declaration_date: date
    student_digital_signature: str     # signed on graduation clearance portal

# Deterministic NIRF/NAAC categorization — no ambiguity possible after declaration
NIRF_CATEGORY_MAP = {
    GraduationEmploymentStatus.PLACED_EMPLOYED:         "placed",
    GraduationEmploymentStatus.HIGHER_STUDIES:          "higher_studies",
    GraduationEmploymentStatus.ENTREPRENEURSHIP_OWN:    "entrepreneurship",
    GraduationEmploymentStatus.ENTREPRENEURSHIP_FAMILY: "entrepreneurship",
    GraduationEmploymentStatus.GOVERNMENT_EXAM_PREP:    "other",
    GraduationEmploymentStatus.NOT_SEEKING_YET:         "not_placed",
    GraduationEmploymentStatus.SEEKING_EMPLOYMENT:      "not_placed",
}
```

**Revoked offers:** Students whose offers were revoked via `OfferRevocationWorkflow`
(EC-SS-02 in `student_services_workflow.md`) must re-submit the declaration at
graduation. `PlacementOfferStatus.REVOKED_BY_EMPLOYER` is never counted as
`placed_employed` in NIRF GO.

---

## RA-3: UGC Compliance & Annual Returns

**Trigger:** Annual return window (typically June–August). Event-triggered for
new programs, fee revision, or governance changes.

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 3.1 | UGC Annual Return Compilation | Pulls from all modules: student enrollment (category-wise), faculty positions (sanctioned vs. filled from HR), program details, financial summary (income/expenditure from FM-7), infrastructure. Pre-populates UGC annual return format using active `regulatory_report_templates` record (EC-REG-02). | Registrar reviews and certifies. VC signs declaration. | UGC Annual Return data ready. | 15 days before deadline |
| 3.2 | Fee Compliance Verification | Checks current fee structure is within UGC fee regulations (no unpermitted fee hike). Verifies fee published on website before admissions (UGC mandate). Generates fee compliance certificate. Cross-references FM-1 fee schedule vs. published fee structure. | Registrar countersigns fee compliance certificate. | Fee compliance certified. Evidence document generated. | Annual (before admissions) |
| 3.3 | Faculty Position Compliance | Generates faculty position report: sanctioned vs. filled per department and program. Flags vacancies >20% of sanctioned strength (UGC audit risk). Tracks NET/PhD compliance % for teaching appointments. Reads from `employee_department_assignments` (EC-HR-03) for correct program-wise attribution. | VC reviews faculty gap report. HOD justifies vacancies. | Faculty compliance report. Vacancy reduction plan if gap >20%. | Quarterly (auto) |
| 3.4 | UGC Self-Disclosure Compliance | Maintains mandatory UGC self-disclosure data on institution website: fee structure, faculty list with qualifications, hostel fees, scholarship details, placement data. AI auto-updates website-linked disclosures whenever source data changes in any module. | Registrar verifies disclosure is current and complete. | Website disclosures always current. Compliance log maintained. | Real-time (auto-update) |
| 3.5 | New Program Approval | On new program launch: generates UGC application documents (program rationale, curriculum, faculty list, infrastructure evidence, fee structure). Bundles supporting documents from Academics and HR. | VC signs application. IQAC Coordinator submits to UGC portal. | UGC program approval submitted. Tracking number recorded. | Per launch timeline |
| 3.6 | Annual Return Submission | Packages final UGC annual return. Runs pre-submission checklist. | Registrar submits on UGC portal. VC countersigns declaration. | UGC Annual Return submitted. Confirmation recorded. | Per UGC deadline |

---

## RA-4: AICTE Approval (Technical Programs)

**Trigger:** Annual — Extension of Approval window (typically September–November).
Applicable only if institution offers AICTE-regulated programs (Engineering,
Management, Pharmacy, Architecture).

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 4.1 | AICTE Compliance Dashboard | Tracks all AICTE conditions: faculty positions (1:15 norm for UG Engineering — not configurable), faculty qualifications per program, intake vs. enrollment, infrastructure (labs, equipment, area per student), fee compliance. Shows real-time compliance status per condition. Flags non-compliance 90 days in advance. | IQAC Coordinator monitors dashboard. Escalates non-compliance to VC. | Live AICTE compliance status. Non-compliance flagged early. | Continuous (auto) |
| 4.2 | Annual Compliance Report (ACR) Preparation | Compiles ACR from: HR (faculty data, qualifications per program), Admissions (enrollment vs. intake), Academics (curriculum revision status), Finance (expenditure on labs and infrastructure). Pre-fills all AICTE portal fields using active template (EC-REG-02). | Dean reviews program-level data. VC approves. | ACR data compiled. Ready for portal submission. | 15 days before window opens |
| 4.3 | Extension of Approval (EoA) Application | Generates EoA application: institution profile, program-wise compliance status, faculty positions, infrastructure declarations. Attaches NAAC grade certificate, UGC approval letters, fee compliance certificate from FM-1. | Registrar submits on AICTE portal. VC signs declaration. | EoA application submitted. Tracking recorded. | Per AICTE window (September–November) |
| 4.4 | AICTE Inspection Preparation | If AICTE schedules inspection: generates readiness report — criteria-wise compliance status, documents ready, gaps to address. Schedules preparation activities. | Dean + IQAC Coordinator manage inspection. VC receives daily readiness report. | Inspection readiness report. Evidence documents compiled. | 30 days before inspection |

---

## RA-5: NBA Accreditation (Program-Level)

**Trigger:** Program applies for NBA after 2 graduating batches. Re-accreditation
triggered 6 months before 3-year validity expires.

**NBA Tier System:**
- **Tier I:** Programs in institutions with NAAC A/A+ — NBA evaluates only program outcomes
- **Tier II:** All other programs — comprehensive self-assessment across 7 criteria

**OBE dependency:** NBA SAR is fundamentally dependent on CO-PO attainment data
from the Academic Operations module E20 OBE/CO-PO system. Without E20 built
and populated, the NBA SAR quantitative section cannot be compiled. The
`co_attainment_records` table (see `academic_operations_workflow.md` Module 11)
is the primary data source for all NBA criteria.

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 5.1 | Program OBE Tracking | Continuously monitors: CO definitions per course, PO attainment scores from `co_attainment_records` (Exams module — direct assessment), CO-PO mapping completeness, syllabus revision cycle. Alerts when any program's CO attainment drops below 60% (configurable). Fires `naac.criterion_red` if attainment drops significantly. | HOD reviews OBE compliance report quarterly. Faculty update CO-PO mappings. | OBE compliance score per program. Attainment data ready for NBA SAR. | Continuous (auto) |
| 5.2 | SAR Preparation | Compiles NBA SAR from: Academics (curriculum, CO-PO, syllabus from E20), Exams (attainment levels, result analysis), HR (faculty qualifications per program — using `employee_department_assignments` for shared faculty split), Student Services (placement, higher studies from EC-REG-04 declarations), Finance (budget per program). Pre-fills all quantitative metrics. | Dean/HOD adds qualitative narratives. IQAC Coordinator consolidates. VC approves. | SAR quantitative section complete. Gap report for narratives. | 45 days of preparation |
| 5.3 | SAR Submission & Visit Preparation | Packages SAR with all evidence. Generates NBA-format evidence index. Prepares program-specific exhibit room index. | IQAC Coordinator submits on NBA portal. Dean leads visit preparation. | SAR submitted. Visit readiness pack generated. | Per NBA deadline |
| 5.4 | Post-Accreditation Monitoring | On NBA accreditation: tracks compliance with conditions. Sets re-accreditation trigger. Updates OBE dashboard to maintain accreditation-level performance. | HOD monitors OBE performance against commitments. | NBA accreditation status tracked. | Continuous |

---

## RA-6: AISHE Data Submission

**Trigger:** Annual — AISHE submission window (October–December, Ministry of Education).

**AISHE Data Categories:**
Institution profile, student enrollment (program/year/category/gender), faculty
(teaching posts — sanctioned/filled/qualifications), non-teaching staff, programs
offered, infrastructure, financial data (income/expenditure), examination results.

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 6.1 | AISHE Data Compilation | On window opening: pulls all AISHE data fields from source modules using `regulatory_metrics` table. Student enrollment from Admissions. Faculty from HR. Financial from Finance FM-7. Exam results from Examinations. Infrastructure from asset register. Pre-fills AISHE portal or downloadable format using active template (EC-REG-02). | Registrar reviews. Cross-checks for anomalies. | AISHE data template complete. | 7 days after window opens |
| 6.2 | Validation & Submission | Runs internal validation: totals, category-wise breakdowns sum to totals, flags >20% year-on-year variation for review. Generates validation report. | Registrar resolves flagged items. VC approves. Registrar submits on AISHE portal. | AISHE data submitted. AISHE code updated. Confirmation recorded. | Before AISHE deadline (typically December) |

---

## RA-7: State Regulatory Body Compliance

**Trigger:** Annual returns to state statutory body (Telangana: TSCHE or affiliating
university where applicable). Event-triggered for new programs, fee changes, admissions.

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 7.1 | State Compliance Calendar | Maintains state-specific deadlines: annual return dates, fee regulation approvals, admission quota compliance (state vs. management quota), reservation roster. Sends reminders 30 days before each deadline. | IQAC Coordinator monitors. Registrar manages state communications. | State compliance calendar active. Auto-reminders sent. | Ongoing |
| 7.2 | Annual Return to State Body | Compiles state annual return: enrollment (state quota vs. management quota), faculty list, fee structure (approved vs. charged), infrastructure. Cross-references state-approved intake and fee. | Registrar certifies. VC signs. | State annual return submitted. Compliance documented. | Per state deadline |
| 7.3 | Reservation Roster Compliance | Tracks SC/ST/OBC/EWS reservation compliance in: student admissions (Admissions module), faculty appointments (HR module), non-teaching staff (HR). Generates roster per state rules. Flags if any category falls below mandated %. | Registrar reviews roster. VC approves corrective action. | Reservation roster current. Shortfall alerts generated. | Quarterly (auto) |
| 7.4 | Fee Regulation Compliance | Verifies fees charged match state-approved fee structure (for states with Fee Regulatory Committee). Auto-compares FM-1 fee schedule against state-approved fee. Flags overcharge. | Registrar resolves discrepancies. Finance Officer certifies. | Fee compliance certified. Evidence maintained. | Before each admission cycle |

---

## RA-8: IQAC — Internal Quality Assurance Cell

**Trigger:** IQAC operates continuously. AQAR submitted to NAAC by July 31 annually.

**IQAC Mandate (UGC guidelines):** Every NAAC-accredited institution must maintain
an IQAC. AQAR submission annually is a condition of accreditation continuity.
Minimum 2 IQAC meetings per year (UGC guideline — not configurable).

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 8.1 | Real-Time Quality Dashboard | Maintains live IQAC dashboard: all NAAC 7-criteria metrics updated daily. Colour-coded (Green/Amber/Red) per metric. Trend charts (3-year rolling). Projected NAAC CGPA from `compute_naac_readiness_score()` (see above). Red flags trigger immediate VC notification. | IQAC Coordinator reviews dashboard weekly. Escalates Red metrics to VC. | Live quality dashboard. Weekly quality digest to VC. | Daily (auto) |
| 8.2 | IQAC Meeting Management | Schedules mandatory IQAC meetings (minimum 2/year). Generates agenda from dashboard Red/Amber items. Records minutes digitally. Tracks action items with owner and absolute deadline. Sends breach reminders on pending action items. | IQAC Coordinator chairs. VC / Dean / Registrar attend. External members participate. | Minutes recorded. Action items tracked. | 2 mandatory meetings/year + ad hoc |
| 8.3 | Best Practices Documentation | Identifies institutional initiatives qualifying as NAAC Best Practices (innovative, impactful, replicable, student-centric). Auto-drafts write-ups from event/programme records in SS-6 (Student Clubs), Academics, and HR modules. | IQAC Coordinator selects and finalises. Dean contributes narratives. | 2 best practices documented per year (NAAC requirement). | Annual |
| 8.4 | Student Satisfaction Survey (Internal) | Conducts internal SSS every semester via student portal. Compiles results. Benchmarks against previous semester. Generates faculty-level and department-level feedback reports (anonymised). | IQAC Coordinator shares results with Dean/HOD. HOD shares with faculty. Results feed HR-4 Appraisal Stage 4.3. | SSS results compiled. Faculty feedback reports distributed. | Each semester end |
| 8.5 | AQAR Compilation & Submission | Year-round: maintains running AQAR. By June 30: finalises quantitative data. Generates criterion-wise narrative drafts (1,000–1,500 words per criterion). Packages AQAR per NAAC format. | IQAC Coordinator finalises narratives. VC approves. Registrar submits to NAAC portal. | AQAR submitted by July 31. Published on institution website. | July 31 (absolute) |
| 8.6 | Accreditation Readiness Score | Runs `compute_naac_readiness_score()` daily. Computes trajectory (improving/declining per criterion). Generates monthly readiness report for VC. Triggers preparation mode 18 months before accreditation cycle start. | VC reviews monthly readiness report. Dean acts on criterion-level Red/Amber. | Monthly NAAC readiness report. Preparation mode activated at 18-month mark. | Monthly (auto) |

---

## EC-REG-01 — Legacy Physical Data (P1 — Sprint 3)

**Trigger:** NAAC requires a 5-year lookback. ALIS was installed 18 months ago.
The previous 3.5 years of data exists only in physical files and unstructured Excel
sheets. The AI dashboard shows Red for historical metrics — not because performance
was poor, but because data doesn't exist in the system.

**What breaks:** Misleading negative NAAC readiness signal. Evidence compilation
impossible without manual intervention. The 5-year SSR quantitative section has
gaps that NAAC will query during DVV.

**Fix: Data Imputation Flags + structured legacy import pipeline**

The `regulatory_metrics` table (shown above) is the fix. The `data_source` and
`confidence` fields are the critical additions. Every metric the system cannot source
from a live module is explicitly marked — not silently zeroed.

The **legacy import pipeline** (go-live blocker §27 in `references/architecture.md`)
handles the structured ingestion of historical data:
- Three-phase pipeline: validate → dry-run → commit. Never skips validation.
- CSV templates per entity type (historical_attendance, exam_results, etc.)
  downloadable from the admin console
- Legacy imported rows land in `regulatory_metrics` with `data_source = 'legacy_import'`
  and `verified_by = NULL` until the IQAC Coordinator verifies them

**Dashboard behaviour for missing / legacy data:**
- Missing metric: renders red with an inline upload button — IQAC coordinator can
  attach scanned legacy documents directly to the metric cell
- Legacy unverified: renders amber with "Imported — pending IQAC verification" badge
- Legacy verified: renders yellow with "Imported — verified" badge
- Live module: renders green — no badge needed

**SSR compilation behaviour:**
Every non-`live_module` data point in the SSR auto-compilation gets a footnote:
`"Data source: legacy import. Original document: [link]. Verified by: [name]."` This
gives NAAC DVV assessors full transparency rather than discovering gaps themselves.

---

## EC-REG-02 — Regulatory Format Changes — OTA Template Updates (P1 — Sprint 3)

**Trigger:** UGC or AICTE changes the column headers or required metrics for their
annual return 2 weeks before the deadline. The hardcoded report generator produces
a non-compliant output.

**What breaks:** Submission rejected or requires emergency manual reformatting.
Compliance deadline missed. Code deployment required during active compliance season.

**Fix: Versioned template schema with OTA update channel**

```sql
CREATE TABLE regulatory_report_templates (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    body             TEXT NOT NULL,
    regulatory_body  TEXT NOT NULL
        CHECK (regulatory_body IN ('NAAC', 'NIRF', 'UGC', 'AICTE', 'AISHE', 'NBA')),
    report_type      TEXT NOT NULL,   -- 'SSR' | 'AQAR' | 'annual_return' | 'nirf_data' | 'EoA'
    version          TEXT NOT NULL,   -- '2024-25' | '2025-26'
    effective_from   DATE NOT NULL,
    effective_until  DATE,
    column_mapping   JSONB NOT NULL,  -- maps ALIS metric keys to regulatory column names
    required_fields  JSONB NOT NULL,  -- mandatory fields for this version
    validation_rules JSONB,           -- field-level validation
    template_url     TEXT,            -- downloadable blank template from regulatory body
    is_active        BOOLEAN DEFAULT true,
    published_by     TEXT,            -- 'quaicu_ota' | 'admin'
    created_at       TIMESTAMPTZ DEFAULT now()
);
```

The `column_mapping` JSONB is the critical decoupling. When NIRF renames
"Number of faculty" to "Total sanctioned teaching posts," QUAICU pushes an OTA
update to this table — no code deployment required:

```python
async def generate_regulatory_report(
    regulatory_body: str,
    report_type: str,
    tenant_id: str,
    academic_year: str,
) -> ReportOutput:
    # Always fetch the active template at runtime — never cache this
    template = await get_active_template(regulatory_body, report_type)

    mapped_data = {}
    for alis_key, regulatory_col in template.column_mapping.items():
        metric = await get_metric(alis_key, tenant_id, academic_year)
        mapped_data[regulatory_col] = metric.value

    missing = [
        f for f in template.required_fields
        if f not in mapped_data or mapped_data[f] is None
    ]
    if missing:
        return ReportOutput(
            status="INCOMPLETE", missing_fields=missing, data=mapped_data
        )

    return ReportOutput(status="READY", data=mapped_data)
```

**OTA update channel:** QUAICU pushes template updates via a signed JSON payload
(HMAC-SHA256 signed by QUAICU's private key). Institutions pull on a configurable
schedule. The admin console shows the last template sync timestamp per regulatory body.
Institutions receive a 7-day advance notice before any template version is deprecated.

---

## EC-REG-03 — Faculty API Score Ghosting (P1 — Sprint 3)

**Trigger:** Faculty publish papers but don't log them in the HR module. The NAAC
live dashboard drops to Red for research output — not because research is poor,
but because data is missing.

**What breaks:** Misleading NAAC readiness score. Decision-makers believe the
institution has a research problem when it's a data hygiene problem. NIRF RP
(Research & Professional Practice) score suffers.

**Fix: Active publication discovery (Celery Beat — weekly per faculty member)**

This is the Regulatory module's scheduled consumption of the same
`PublicationDiscoveryService` defined in EC-HR-02 (`hr_payroll_workflow.md`).
The HR module owns the discovery logic. The Regulatory module schedules it.

```python
class PublicationDiscoveryScheduler:
    """Celery Beat task — runs weekly per faculty member per tenant."""

    async def discover_and_draft(self, faculty_id: UUID, tenant_id: UUID):
        faculty = await get_employee(faculty_id, tenant_id)

        # Query external sources in parallel
        scopus_task  = scopus_api.search(
            author=faculty.full_name,
            affiliation=faculty.institution_domain,
        )
        orcid_task   = (
            orcid_api.get_works(faculty.orcid_id)
            if faculty.orcid_id else asyncio.sleep(0)
        )
        scholar_task = google_scholar.search(
            faculty.full_name, faculty.email_domain
        )

        scopus_pubs, orcid_pubs, scholar_pubs = await asyncio.gather(
            scopus_task, orcid_task, scholar_task,
            return_exceptions=True
        )

        # Deduplicate by DOI across all three sources
        all_pubs = deduplicate_by_doi([
            *safe_result(scopus_pubs),
            *safe_result(orcid_pubs),
            *safe_result(scholar_pubs),
        ])

        # Only surface publications not yet in HR module
        known_dois = await get_logged_publication_dois(faculty_id, tenant_id)
        new_pubs   = [p for p in all_pubs if p.doi not in known_dois]

        if new_pubs:
            await create_publication_drafts(faculty_id, tenant_id, new_pubs)
            # Consolidated notification — one weekly digest, not per-paper spam
            await notify_faculty_pending_verification(faculty_id, len(new_pubs))
```

Faculty receives a consolidated weekly notification: "We found N publications that
may be yours. Click to verify." Each draft shows title, journal, year, index (Scopus/
SCI/UGC-listed), and suggested API Category III points. One click confirms —
zero manual data entry burden.

On faculty verification: `regulatory_metrics` for `research_publications_count`
updates automatically. The NAAC C3 and NIRF RP scores update on the dashboard
within the next daily harvest cycle.

**Feature flag:** `hr.publication_discovery` — requires Scopus API key per
institution. Without API key: system falls back to ORCID-only discovery and
flags the gap on the admin console.

---

## Regulatory Report Template Coverage

The `regulatory_report_templates` table must have active records for all of
the following on go-live. QUAICU maintains these and pushes OTA updates.

| Regulatory Body | Report Type | Current Version Key | Primary Metric Mapping |
|---|---|---|---|
| NAAC | SSR (7 criteria) | `NAAC_SSR_2024` | C1–C7 criterion scores → live module metrics |
| NAAC | AQAR | `NAAC_AQAR_2024` | All 7 criteria quantitative fields |
| NAAC | IIQA | `NAAC_IIQA_2024` | Institution profile, eligibility data |
| NIRF | Data template | `NIRF_2024-25` | TLR, RP, GO, OI, PR parameter fields |
| UGC | Annual return | `UGC_RETURN_2024` | Enrollment, faculty, fee, infrastructure |
| AICTE | ACR | `AICTE_ACR_2024` | Faculty norms, enrollment vs. intake, labs |
| AICTE | EoA application | `AICTE_EOA_2024` | Program-wise compliance declaration |
| NBA | SAR (Tier I) | `NBA_SAR_T1_2024` | CO-PO attainment, program outcomes |
| NBA | SAR (Tier II) | `NBA_SAR_T2_2024` | All 7 NBA criteria quantitative + narrative |
| AISHE | Annual data | `AISHE_2024` | Enrollment, faculty, infra, financial data |

---

## Live Regulatory Dashboard

Single unified dashboard — visible to IQAC Coordinator, Registrar, Dean, and VC
based on role access. All panels read from `regulatory_metrics` table.

| Panel | Content | Update Frequency |
|---|---|---|
| NAAC Readiness Score | Criterion-wise score (C1–C7), overall CGPA estimate, Red/Amber/Green per criterion | Daily |
| NIRF Score Estimate | 5-parameter scores, projected rank range, year-on-year delta | Daily |
| AISHE Readiness | All AISHE data fields — filled % and last update timestamp | Daily |
| UGC Compliance Status | Annual return status, fee compliance, faculty position compliance, self-disclosure | Real-time |
| AICTE Compliance | Program-wise compliance, faculty norms (1:15), infrastructure norms | Real-time |
| NBA OBE Status | Program-wise CO-PO attainment from `co_attainment_records`, SAR readiness % | Weekly |
| State Compliance | Reservation roster, fee compliance, state return status | Real-time |
| Upcoming Deadlines | All regulatory deadlines next 90 days with days-remaining counter | Daily |
| Evidence Health | % required evidence documents present, current vs. expired or missing | Weekly |
| Data Quality Report | Distribution of `regulatory_metrics` by `data_source` — % live vs. legacy vs. missing | Weekly |
| Template Version Status | Active template version per regulatory body, last OTA sync timestamp | Daily |
| Key Metrics Trend | 3-year trend for top 20 metrics that drive NAAC + NIRF scores | Monthly |

---

## Cross-Module Integration Map

The Regulatory module is a consumer. It reads from all 6 upstream modules and
writes back compliance status events.

### Inbound — What Regulatory Reads

| Data Pull | Source Module | Regulatory Use | Frequency |
|---|---|---|---|
| Student enrollment, category breakdown | Admissions | NAAC C2, NIRF TLR+OI, AISHE, UGC return | Real-time |
| Faculty records, qualifications, PhD %, NET % | HR HR-1, HR-2 | NAAC C2+C6, NIRF TLR, AISHE, AICTE | Real-time |
| `employee_department_assignments` (EC-HR-03) | HR | Faculty-to-student ratio per program for AICTE norms | Daily |
| Research publications, patents, grants | HR HR-4 (API Cat III + EC-HR-02 discovery) | NAAC C3, NIRF RP | Weekly |
| Training completion, FDP, UGC mandatory programmes | HR HR-5 | NAAC C6, UGC faculty development | Real-time |
| Result statistics, graduation rate | Examinations | NAAC C2, NIRF GO, AISHE | Post-result |
| PhD scholars enrolled / degrees awarded | Academics + E15 PhD module | NAAC C3, NIRF RP, NBA SAR | Per event |
| CO-PO attainment levels | Academics E20 OBE | NBA SAR — all criteria | Weekly |
| Placement data, `GraduationEmploymentDeclaration` | SS-3 + SS-8 (EC-REG-04) | NAAC C5, NIRF GO | On graduation + real-time |
| Scholarship disbursement, % aided | SS-4 + Finance FM-2 | NAAC C5, NIRF OI | Real-time |
| Grievance data, resolution rates, UGC compliance | SS-5 (`grievance.closed`) | NAAC C5+C6, UGC compliance | Real-time |
| Library holdings, e-resources | SS-2 Library | NAAC C4, AISHE | Real-time |
| Student activity events, participation hours | SS-6 Events | NAAC C7 | Annual |
| Alumni career data | SS-8 (`GraduationEmploymentDeclaration`) | NAAC C5, NIRF GO | Annual |
| Financial statements, expenditure heads | Finance FM-7 | NAAC C6, NIRF TLR, AISHE, UGC return | Monthly |
| Fee collection vs. approved fee | Finance FM-1 | UGC + State fee compliance | Real-time |
| Hostel occupancy, facilities | SS-1 Hostel | NAAC C4, AISHE | Real-time |
| Student feedback scores | Academics + IQAC internal SSS | NAAC C2, HR-4 Appraisal | Semester |

### Outbound — Events Written Back to Upstream Modules

| Event | Fired By | Consumed By | Purpose |
|---|---|---|---|
| `naac.criterion_red` | RA-8 IQAC Dashboard | Dean + VC Dashboard | Criterion below threshold — immediate attention |
| `naac.ssr_submitted` | RA-1 Stage 1.6 | Registrar records | SSR submission confirmation |
| `nirf.submitted` | RA-2 Stage 2.3 | Registrar records | Annual ranking data submitted |
| `accreditation.renewed` | RA-1 Stage 1.10 | All modules (institutional profile) | NAAC grade renewed — validity period updated |
| `compliance.deadline_approaching` | All RA modules | IQAC + Registrar | 90/30/7-day advance on any regulatory deadline |
| `nba.obe_below_threshold` | RA-5 Stage 5.1 | Academics (OBE dashboard) + HOD | CO-PO attainment below 60% — curriculum action needed |

---

## SLA & Escalation Matrix

| Domain | Task | Actor | SLA | Breach Escalation |
|---|---|---|---|---|
| NAAC | AQAR submission | IQAC Coordinator | July 31 (absolute) | VC takes direct ownership; Registrar submits |
| NAAC | SSR preparation (post-IIQA) | IQAC + All Deans | 90 days | VC constitutes emergency SSR task force |
| NAAC | DVV response | IQAC Coordinator | 7 days (NAAC statutory) | VC approves emergency response team |
| NAAC | Criterion narrative writing | Dean/HOD | 45 days | IQAC Coordinator drafts with AI; Dean approves |
| NAAC | Legacy data import (EC-REG-01) | IQAC Coordinator | Before SSR compilation | Registrar escalates; VC briefed on data gaps |
| NIRF | Annual data submission | IQAC Coordinator | Per NIRF window | Registrar submits with available data |
| UGC | Annual return | Registrar | Per UGC deadline | VC submits directly |
| UGC | Faculty vacancy gap >20% | VC + HOD | Quarterly review | Board informed; recruitment accelerated |
| UGC | Website self-disclosure update | IQAC Coordinator | 7 days after any data change | Registrar auto-notified by system |
| AICTE | Extension of Approval | Registrar | Per AICTE window (September) | VC intervenes; legal counsel on standby |
| AICTE | Faculty norm breach (1:15) | Dean + HR Officer | 30 days | Dean reviews; emergency recruitment initiated |
| NBA | OBE compliance (CO-PO <60%) | HOD | 30 days post-detection | Dean reviews; curriculum revision triggered |
| AISHE | Annual submission | Registrar | Per MoE deadline (December) | Registrar submits with available data |
| State | Reservation roster compliance | Registrar | Quarterly review | VC notified; HR recruitment adjusted |
| IQAC | IQAC meetings (minimum 2/year) | IQAC Coordinator | Per UGC guideline | VC mandates meeting if missed |
| IQAC | Monthly readiness report | IQAC Coordinator | 5th of each month | Auto-generated even without coordinator action |
| All | OTA template sync | QUAICU platform | Within 24 hours of QUAICU push | Admin console alert; manual template override |

---

## What Actors Never Do (AI Handles Completely)

**Evidence Building:**
- Pull student enrollment statistics from Admissions for any regulatory submission
- Extract faculty qualification data from HR for NAAC, NIRF, AICTE, UGC
- Compute student-faculty ratios, PhD faculty %, expenditure per student
- Pull placement statistics from SS-3 for NAAC C5 and NIRF GO
- Extract scholarship data from SS-4 and Finance for NAAC C5 and NIRF OI
- Discover faculty publications via ORCID/Scopus/Google Scholar (EC-REG-03)
- Pull grievance resolution rates from SS-5 for NAAC C5 and C6
- Download result statistics from Examinations for NAAC C2 and NIRF GO
- Pull CO-PO attainment from Academics E20 for NBA SAR
- Pull `GraduationEmploymentDeclaration` records for NIRF GO (EC-REG-04)
- Extract financial expenditure from Finance FM-7 for NAAC C6 and NIRF TLR

**Compliance Monitoring:**
- Run NAAC readiness score computation (`compute_naac_readiness_score()`) daily
- Flag any metric falling below Amber/Red thresholds for target NAAC grade
- Send regulatory deadline reminders 90/30/7 days in advance
- Update UGC mandatory website disclosures whenever source data changes
- Track reservation roster compliance across admissions and faculty
- Monitor AICTE faculty norms (1:15) as HR records update
- Track CO-PO attainment levels weekly for NBA programs
- Check `regulatory_report_templates` for active template versions before every report run
- Fetch OTA template updates from QUAICU's secure channel

**Document Assembly:**
- Pre-populate NAAC SSR quantitative sections from 5-year lookback data
- Generate criterion-wise evidence index with hyperlinks to source documents
- Draft AQAR/SSR qualitative narratives (for human refinement)
- Package DVV response documents from source module evidence
- Compile AISHE data template from source modules
- Generate state compliance data for annual returns
- Assemble peer team visit preparation pack
- Generate `regulatory_metrics_gap_report` view and surface to dashboard

---

## Configurable Parameters

| Domain | Parameter | Default |
|---|---|---|
| NAAC | Target NAAC grade | A (CGPA 3.26–3.50) |
| NAAC | Criterion Amber threshold | 10% below target grade score |
| NAAC | Criterion Red threshold | 25% below target grade score |
| NAAC | Preparation mode trigger | 18 months before cycle end |
| NAAC | SSR preparation window | 90 days quantitative + 45 days qualitative |
| NIRF | NIRF category for submission | Universities (default) |
| NIRF | Publication database source | Scopus API (configurable; manual upload fallback) |
| UGC | Faculty vacancy gap alert threshold | 20% of sanctioned strength |
| UGC | Self-disclosure update SLA | 7 days after source data change |
| AICTE | Faculty norm — student-faculty ratio | 1:15 for UG Engineering (AICTE mandate — not configurable) |
| NBA | OBE attainment alert threshold | 60% CO-PO attainment |
| NBA | Re-accreditation trigger | 6 months before 3-year validity expiry |
| AISHE | Submission reminder | 14 days before window close |
| State | Reservation roster review frequency | Quarterly |
| IQAC | IQAC meeting minimum frequency | 2 per year (UGC mandate — not configurable) |
| IQAC | NAAC readiness report frequency | Monthly |
| All | Regulatory deadline advance reminder | 90 days / 30 days / 7 days |
| EC-REG-01 | Legacy data confidence display | Amber for unverified import; Yellow for verified import |
| EC-REG-02 | OTA template pull schedule | Daily (configurable) |
| EC-REG-03 | Publication discovery frequency | Weekly (Celery Beat) |
| EC-REG-03 | Publication discovery sources | Scopus + ORCID + Google Scholar (configurable per API key availability) |

---

## Notification Map

| Domain | Trigger | Recipients | Channel |
|---|---|---|---|
| NAAC | Criterion score falls to Amber | IQAC Coordinator + Dean + VC | Email + Dashboard |
| NAAC | Criterion score falls to Red | VC (urgent) | Email + SMS |
| NAAC | AQAR submission due (30 days) | IQAC Coordinator + Registrar | Email |
| NAAC | DVV query received | IQAC Coordinator + VC | Email + SMS (urgent) |
| NAAC | Peer team visit date confirmed | VC + All Deans + IQAC | Email |
| NAAC | NAAC grade announced | VC + Board | Email + Dashboard |
| NIRF | Submission window opens | IQAC Coordinator + Registrar | Email |
| NIRF | Ranking released | VC + All Deans | Email + Dashboard |
| UGC | Faculty vacancy gap >20% | VC + HOD | Email + Dashboard |
| UGC | Website disclosure out of date (>7 days) | Registrar | Email |
| AICTE | EoA window opens (60 days advance) | IQAC Coordinator + Registrar | Email |
| AICTE | Faculty norm breach (program-level) | Dean + HOD + HR Officer | Email + Dashboard |
| NBA | CO-PO attainment below 60% | HOD + Dean | Email + Dashboard |
| NBA | SAR submission due (60 days) | IQAC Coordinator + Dean | Email |
| AISHE | Submission window opens | Registrar + IQAC Coordinator | Email |
| State | Compliance deadline (30 days) | Registrar + IQAC Coordinator | Email |
| State | Reservation roster shortfall | Registrar + VC + HR Officer | Email |
| EC-REG-01 | Legacy data gap detected — metric missing | IQAC Coordinator | Dashboard (inline upload prompt) |
| EC-REG-01 | Imported data pending IQAC verification | IQAC Coordinator | Email (weekly batch) |
| EC-REG-02 | New regulatory template version available | Admin + IQAC Coordinator | Email + Admin console |
| EC-REG-02 | Template version deprecated (7 days advance) | Admin + IQAC Coordinator | Email |
| EC-REG-03 | New faculty publications found (weekly) | Faculty member | Email + Portal (HR module) |
| IQAC | Monthly readiness report ready | VC + Dean + Registrar | Email |
| IQAC | IQAC meeting due (none in 6 months) | IQAC Coordinator + VC | Email |
| All | Regulatory deadline calendar (90 days) | IQAC Coordinator + Registrar | Weekly email digest |

---

## The Data Flywheel

Every operational action in Modules 1–6 generates data. The Regulatory module
harvests that data continuously. The evidence base is never stale.

```
Module 1 (Admissions)       → enrollment data, diversity metrics, dropout rates
Module 2 (Academics)        → curriculum data, teaching quality, CO-PO attainment (E20)
Module 3 (Examinations)     → result statistics, graduation rates, PhD output (E15)
Module 4 (Student Services) → placement rates (EC-REG-04), scholarship data,
                              grievance outcomes, alumni employment
Module 5 (Finance)          → expenditure per student, research funding, fee compliance
Module 6 (HR & Payroll)     → faculty qualifications, research output (EC-REG-03/HR-02),
                              training data, sanctioned vs. filled positions
                ↓
Module 7 (Regulatory)       → live evidence base
                            → NAAC readiness score (daily)
                            → NIRF data template (annual)
                            → UGC annual returns
                            → AICTE ACR + EoA
                            → NBA SAR (with E20 CO-PO data)
                            → AISHE submission
                            → State returns
                            → AQAR (annual, July 31)
```

### Compliance Coverage Summary

| Regulatory Body | Metrics Auto-Sourced | Human Effort Required |
|---|---|---|
| NAAC (7 criteria) | All quantitative metrics from 5-year lookback; legacy data via EC-REG-01 pipeline | Qualitative narrative (1,000–1,500 words/criterion), VC sign-off |
| NIRF (5 parameters) | TLR, RP, GO (via EC-REG-04), OI — fully auto (except Perception) | Perception parameter (external survey), VC declaration |
| UGC Annual Return | All data fields from source modules; OTA template updates via EC-REG-02 | Registrar certification + VC sign-off |
| AICTE ACR / EoA | Faculty, enrollment, infrastructure metrics | Dean program-level review, VC declaration |
| NBA SAR | OBE/CO-PO from E20, faculty per program (EC-HR-03 split), placement (EC-REG-04) | Criterion narratives, Dean/HOD review |
| AISHE | All data fields from source modules | Registrar final review and portal submission |
| State Body | Enrollment, fee, roster, faculty data; fee compliance vs. FM-1 | Registrar certification, VC sign-off |
| IQAC / AQAR | All quantitative data — continuously maintained; EC-REG-03 publications auto-discovered | Qualitative narrative (AI draft, IQAC refines), VC approval |

---

*Document version: 2.0 | March 2026*
*Connected to: admissions_workflow.md → academic_operations_workflow.md →*
*examination_workflow.md → student_services_workflow.md → finance_workflow.md →*
*hr_payroll_workflow.md → regulatory_accreditation_workflow.md*
*Full institutional lifecycle: Lead Captured → Graduated → Alumni Engaged → Accredited*
*QUAICU Pvt. Ltd. | quaicu.org | Hyderabad, India | Confidential*
