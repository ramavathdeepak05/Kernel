# Academic Operations Workflow
### Full Automation Reference — ALIS OS Module E05
#### Model: AI Executes Everything. Actors Approve.
#### QUAICU Pvt. Ltd. | quaicu.org | Hyderabad, India | Confidential

---

## Document Map

This document covers the full Academic Operations module (E05) of ALIS OS.

**Connected documents:**
- `admissions_workflow.md` — upstream source of all student enrollment events
- `examination_workflow.md` — downstream consumer of attendance, IA marks, and question papers
- `student_services_workflow.md` — shares mentorship risk signals and event data
- `hr_payroll_workflow.md` — faculty timetable assignments and CAS appraisal data
- `regulatory_accreditation_workflow.md` — consumes OBE attainment data and academic metrics
- `finance_workflow.md` — shares academic calendar blackout dates; consumes dues clearance signals

**Cross-references to skill files:**
- Edge cases: `references/edge-cases.md` — EC-ACA-01 through EC-ACA-04
- OBE architecture: `references/architecture.md` §33
- Offline PWA: `references/gaps.md` — Offline / Low-Bandwidth PWA section
- Build sequence: `ALIS_BUILD_PLAN.md` — Sprint 3 (EC cases), Sprint 9 (E20 OBE)

---

## Core Operating Principle

Every task in this module is initiated, drafted, generated, scheduled, or executed by AI.
Humans — Faculty, HOD, Registrar, Students — act exclusively as **approvers** at defined gates.

```
DEFAULT FLOW FOR EVERY TASK:

  AI generates / executes
        │
        ▼
  Delivered to Actor's approval queue
        │
        ├── Actor approves  ──► Published / Executed
        ├── Actor edits     ──► AI updates, re-queued
        └── Actor rejects   ──► AI re-generates with reason, re-queued
```

If an Actor does not act within the defined SLA window, the system either:
- **Auto-approves** (low-stakes: attendance reports, reminders, progress updates), or
- **Escalates** to the next role up (high-stakes: question papers, grade cards, progression decisions)

No task is blocked waiting indefinitely for a human. The system keeps moving.

Every SLA timer uses an **absolute deadline timestamp** stored at task creation time.
Never use `workflow.sleep(timedelta)` — this drifts. Use `timeout = deadline - workflow.now()`.
See EC-CROSS-04 in `references/edge-cases.md` for full implementation.

---

## Approver Map

| Content / Action | Approver | Escalates To (if no action) |
|------------------|----------|------------------------------|
| Academic calendar | Registrar | Academic Council |
| Course-to-faculty mapping | HOD | Dean |
| Course outline (week plan) | Faculty | HOD |
| Lecture PPTs | Faculty | Auto-published to faculty-only view |
| Student course handbook | Faculty | HOD |
| Program handbook | HOD | Academic Council |
| Assignments + rubrics | Faculty | Auto-published after SLA |
| IA question paper | Faculty → HOD | Exam Cell |
| Timetable | Registrar | Dean |
| Substitution request | HOD | Registrar |
| Attendance alerts (student) | — | Auto-sent, no approval needed |
| Parent communication (at-risk) | Mentor (Faculty) | HOD sends directly |
| Progress report | — | Auto-sent, no approval needed |
| IA marks review | Faculty | HOD (if SLA breached) |
| Grade moderation | HOD | Exam Cell |
| End-sem results | Registrar | — |
| Progression decisions | Academic Committee | — |
| Document issuance (transcript, etc.) | Registrar | — |
| Shortage / ineligibility letter | Registrar | — |
| CO definition (per course) | Faculty | HOD |
| CO-PO mapping | HOD | Academic Committee |
| CO attainment targets | HOD | Dean |
| Mass bunk confirmation | HOD | Registrar |
| Global recalibration (campus closure) | Registrar | Dean |
| Faculty handover package | HOD | Dean |

---

## How This Connects to the Admissions Module

The moment a student's status = `Enrolled` in the Admissions module, an event fires.
The Academic module listens and bootstraps everything automatically. No manual handoff.

```
ADMISSIONS MODULE                        ACADEMIC MODULE
─────────────────                        ───────────────
Enrollment Complete
  │
  ├── Student ID + Roll No. generated
  ├── Program + Specialization confirmed
  ├── Batch + Intake year confirmed
  └── Electives chosen (if captured)
  │
  └──► EVENT: student.enrolled
            │
            ├── Student record created in SIS
            ├── Batch + Section auto-assigned
            ├── Mentor auto-assigned
            ├── LMS account provisioned
            ├── Timetable slot reserved
            ├── Risk baseline built from admissions data
            ├── OBE course enrollments created (E20)
            └── All module pipelines initialized
```

**Late joiner handling (EC-ADM-02):**
State counseling batches arrive 6–10 weeks after the main batch. The standard enrollment
pipeline cannot generate a working schedule for a partially-elapsed semester.
See `references/edge-cases.md` EC-ADM-02 for the `CatchUpCohortWorkflow` implementation.
Key rule: past sessions are pre-marked `EXCUSED_LATE_JOINER` — excluded from the
attendance eligibility denominator. This is enforced in the `attendance_eligibility`
policy DSL, not in application code.

**Data passed from Admissions → Academics at enrollment:**

| Field | Used For |
|-------|----------|
| Student ID / Roll No. | Master key across all academic records |
| Full name | All documents, certificates, ID card |
| Program + Specialization | Curriculum assignment, course mapping |
| Intake year + Semester | Academic calendar alignment |
| Category (SC/ST/OBC/EWS) | Scholarship tracking, reservation reporting |
| Email + phone | All notifications |
| Parent/guardian contact | Attendance alerts, mentorship comms |
| Entrance score + 12th marks | Mentorship risk baseline (Day 1 profiling) |
| Hostel assignment (Y/N) | Warden notification, risk weight |
| Elective preferences | LMS course shell enrollment |

---

## Pipeline Overview

| # | Module | AI Does | Approver |
|---|--------|---------|----------|
| 1 | Academic Calendar | Drafts calendar, flags conflicts, cascades changes | Registrar |
| 2 | Curriculum & Course Mapping | Maps courses to faculty, balances workload | HOD |
| 3 | Course Content Generation | Generates PPTs, outlines, handbooks | Faculty |
| 4 | Assignment & Assessment Drafting | Drafts assignments, papers, rubrics | Faculty + HOD |
| 5 | Timetable & Classroom Management | Generates conflict-free timetable | Registrar |
| 6 | Attendance Management | Creates sessions, sends alerts, computes eligibility | — (fully auto) |
| 7 | Mentorship & Student Support | Scores risk, drafts interventions, schedules meetings | Mentor (Faculty) |
| 8 | Internal Assessment & Grading | Auto-grades, computes scores, flags anomalies | Faculty + HOD |
| 9 | End-Semester Examination | Manages logistics, computes results | Registrar |
| 10 | Progression & Records | Computes progression, generates all documents | Registrar |
| 11 | OBE / CO-PO Mapping (E20) | AI-assisted CO generation, attainment computation | Faculty + HOD |

---

## Module 1 — Academic Calendar

**AI Does:**
- Drafts the full academic year calendar based on: minimum teaching day requirements
  (AICTE: 90 days/semester), previous year's calendar as template, public holidays
  (state + national)
- Maps semester start/end, teaching weeks, IA windows, exam block, result dates, convocation
- Flags conflicts (e.g., exam block overlapping a holiday cluster)
- When a change is made mid-year, AI cascades the impact: teaching week count updates,
  affected sessions flagged, faculty notified of displaced sessions — automatically

**Global Recalibration (EC-ACA-01):**
When an unplanned campus closure occurs (bandh, flood, power failure), a single
Registrar command triggers `GlobalRecalibrationWorkflow`. See the edge case section
below for full implementation. Key rules:
- `EXCUSED_DISRUPTION` attendance status is excluded from eligibility denominator
- Pre-locked exam dates (CoE-approved schedule) are immovable — solver flags conflicts
  but does not override them
- Registrar sees a preview before confirming: "This shifts 847 sessions, 234 deadlines.
  3 exam dates are pre-locked and cannot move."

**Approver — Registrar:**
- Reviews the draft calendar
- Edits if needed (AI re-generates affected sections on any change)
- Approves → calendar published to all roles, all downstream modules initialized

**What calendar approval triggers (auto, no human needed):**
- Timetable sessions on affected dates flagged for rescheduling
- Faculty notified of displaced classes
- Students notified of revised schedule
- IA and exam windows locked into system

---

## Module 2 — Curriculum & Course Mapping

**AI Does:**
- Pulls the program curriculum from the system (courses, credits, L-T-P structure)
- Pulls enrolled batch data from Admissions (programs, batch sizes, elective preferences)
- Generates a suggested course-to-faculty mapping considering: faculty specialization
  tags, previous semester loads, max credit load per norms (16–20 credits/semester),
  declared unavailability
- Produces a workload report per faculty (credits assigned, hours/week, overload flags)
- Creates LMS course shells for each course
- Enrolls students into course shells automatically from Admissions data
- Sends faculty their course assignment notifications
- For OBE programs: initializes CO-PO framework for each new course (see Module 11)

**Adjunct / Industry Faculty (EC-ACA-04):**
Visiting and industry faculty submit availability week-by-week — they cannot commit
to fixed recurring weekly slots. The timetable solver uses an **Ad-Hoc Scheduling Zone**
for these faculty, bypassing weekly pattern constraints and treating their availability
as hard constraints instead. See `references/edge-cases.md` EC-ACA-04 for solver config.

**Approver — HOD:**
- Reviews the suggested mapping
- Adjusts any assignments if needed (AI re-checks constraints on any change)
- Approves → assignments locked, faculty formally notified, LMS shells activated

**What HOD approval triggers (auto):**
- Faculty receive course brief and are queued into content review (Module 3)
- AI begins generating course content for every approved course immediately
- OBE: CO generation prompt sent to faculty for each newly assigned course (Module 11)

---

## Module 3 — Course Content Generation

**AI Does — for every assigned course:**

### Course Outline
- Parses the official syllabus (uploaded or selected from the syllabus library)
- Extracts: units, topics, sub-topics, learning outcomes
- Maps topics to teaching weeks based on credit hours
- Generates a week-by-week plan: Week → Topics → Learning Outcome → Teaching Method
  → Assessment Link → CO Mapping (for OBE programs)

```
Week 1  | Introduction to [Topic]     | LO1: Define and explain...  | Lecture + Discussion | CO1
Week 2  | [Sub-topic A + B]           | LO2: Apply...               | Case Study           | CO2, CO3
Week 8  | IA1 Revision                | —                           | Revision Session     | —
Week 9  | IA1 Assessment              | —                           | Internal Test        | CO1–CO3
```

### Lecture Slide Decks (PPTs)
- Generates one complete slide deck per lecture in the course outline
- Slide structure per deck: Title → Learning Objectives → Content (3–6 slides) →
  Real-World Application → Summary → Discussion Questions → References
- Sources: uploaded syllabus, textbook references, optionally web-fetched current examples
- All decks use the institution's approved template (color, logo, font — set once)
- Exported as .pptx, stored in course folder on LMS

**AI-generated duplicate detection:**
If multiple faculty members generate content for similar course codes (e.g., all
B.Tech Year 1 Maths sections), AI runs a cosine similarity check against previously
generated outlines within the same tenant using the pgvector index. Similarity > 0.85
surfaces a "Similar content detected" flag — faculty can accept or diverge. This is a
quality signal, not a block.

### Student Course Handbook
- Assembled entirely from data already in the system
- Contains: course overview, faculty contact + office hours, prerequisite knowledge,
  textbooks, week-by-week plan, assessment pattern, grading scale, academic integrity
  policy, IA coverage, self-study resources, CO list (for OBE programs)
- Scheduled for auto-release to students on semester start date

### Program Handbook (per new batch)
- Triggered by: new batch enrollment confirmed in Admissions module
- Contains: program overview, vision + mission, program outcomes (POs), semester-wise
  structure, faculty directory, facilities, rules, scholarships, placement, grievance
- Generated once per batch intake, delivered to all enrolled students

**Approver — Faculty (per course):**
- Reviews course outline, adjusts topic sequencing, adds custom sessions
- Reviews slide decks, edits content, adds diagrams or local examples
- Approves course handbook for student release
- HOD can view any course content and flag syllabus misalignment

**What faculty approval triggers (auto):**
- Course outline locks as the official teaching plan
- Approved PPTs available in faculty portal
- Handbook auto-released to students on semester start date
- Assignment and assessment drafting begins for the approved outline (Module 4)
- OBE: CO definitions submitted to Module 11 for CO-PO mapping

---

## Module 4 — Assignment & Assessment Drafting

**AI Does — for every course:**

### Assignments
- For each week/topic in the approved outline, generates: 2–3 practice problems or
  short questions, 1 application-based assignment (case study, problem set, design
  brief, coding challenge, or reflective prompt)
- All assignments mapped to Bloom's taxonomy level — distribution set by faculty once
  per course (e.g., 20% recall, 50% application, 30% analysis)
- Each assignment brief includes: problem statement, instructions, format, word/page
  limit, marks, submission deadline (auto-populated from calendar)
- For OBE programs: each assignment is tagged to the COs it addresses

### IA Question Papers (IA1, IA2, IA3)
- Faculty specifies once per IA: topics covered, paper pattern (MCQ / short / long /
  mix), total marks, duration, Bloom's distribution, CO mapping (for OBE)
- AI generates a complete question paper: instructions, section breakup, marks per
  question, CO tag per question
- Every generated question also added to a permanent question bank — tagged by course,
  topic, Bloom's level, difficulty, type, CO — reusable across batches
- End-semester paper draft similarly CO-tagged for attainment computation

### Rubrics
- Generated for every assignment, project, presentation, and viva
- Structure: Criteria × Performance Levels (Excellent / Good / Satisfactory / Poor)
  with descriptors per cell
- Attached to the assignment automatically; students see rubric before submitting

### End-Semester Question Paper
- AI drafts based on full syllabus coverage, unit weightage, university-prescribed
  pattern, and CO distribution
- Encrypted and stored; released only on exam day automatically
- Each question carries a CO tag used for attainment computation post-evaluation

**Approver — Faculty (assignments + rubrics):**
- Reviews, edits, approves
- Auto-published after SLA if no action (48–72 hours, configurable)

**Approver — Faculty → HOD (IA question papers):**
- Faculty approves first
- HOD reviews for pattern compliance, syllabus coverage, and CO coverage
- Locked after HOD approval — no edits possible after this point
- Paper released automatically on exam day, no manual step

**What approval triggers (auto):**
- Approved assignments scheduled and released on their assigned dates
- Submission reminders sent to students at T-2 days and T-1 day
- Rubrics attached and visible to students from the moment the assignment releases
- CO tags flow to Module 11 for attainment tracking

---

## Module 5 — Timetable & Classroom Management

**AI Does:**
- Generates a conflict-free timetable across all courses, faculty, sections, rooms,
  and credit hours using a constraint satisfaction solver (Google OR-Tools)
- Hard constraints enforced (cannot be violated): no double-booking of faculty/rooms/
  sections, lab sessions only in lab rooms, section size ≤ room capacity
- Soft constraints optimized: faculty preference slots, spread heavy-credit courses
  across the week, cluster teaching days, avoid fragmented single-session days
- Generates four views from one master: Master (Registrar), Program (HOD),
  Faculty (individual), Student (individual)
- Generates printable room occupancy schedule

**Important:** The timetable is generated by a constraint solver — not an LLM.
Natural language (faculty preference descriptions) is translated into structured
constraints by the AI layer, then passed to the solver. The solver generates;
the AI explains and communicates. See `references/architecture.md` §9 for the
LLM task class routing that applies here (`EXTRACTION` for constraint parsing,
`DRAFTING` for explanation — never `REASONING` for the solve itself).

**Mid-semester (AI handles automatically):**

**Substitution:**
Faculty raises flag → AI identifies an available qualified substitute → suggests
to HOD → on approval, timetable updated, students notified. Substitute must be
from a different department than the absent faculty's section where possible.

**Faculty Attrition (EC-ACA-02):**
When a faculty member separates mid-semester, the system detects `INSTRUCTOR_MISSING`
on their assigned courses and triggers `CourseHandoverWorkflow`. Key actions:
- AI freezes all auto-releases (IA papers, assignments) from the departing faculty
- AI generates a `CourseHandoverPackage`: snapshot of course state, completed sessions,
  pending assessments, student marks to date
- LMS course shell ownership transferred to HOD
- All timetable sessions for next 2 weeks flagged `SUBSTITUTE_REQUIRED` in red
- HOD must assign a replacement within 48h SLA; escalates to Dean if breached
- `EmergencySeperationOverride` compresses knowledge transfer to 48h when needed
See `references/edge-cases.md` EC-ACA-02 for the full workflow.

**Room change:** Registrar inputs new room → AI updates all views, notifies all parties.

**Approver — Registrar:**
- Reviews the generated timetable
- Adjusts if needed (AI re-checks constraints on any manual change)
- Approves → timetable published to all portals, all faculty and students notified

**What Registrar approval triggers (auto):**
- Every timetable slot becomes a pre-created attendance session (Module 6)
- Faculty receive their teaching schedule
- Students receive class schedule via email and portal

---

## Module 6 — Attendance Management

**This module is fully automated. No approval gate except shortage letters.**

**AI Does:**
- Pre-creates an attendance session for every timetable slot — no manual session
  creation ever
- Supports multiple marking modes:

| Mode | How It Works |
|------|-------------|
| Portal / mobile (standard) | Faculty opens session, marks each student |
| PWA / offline mode | Faculty marks offline; syncs when online (see below) |
| OTP / QR code | AI generates session code; students self-mark within 5-minute window; GPS check flags off-campus devices |
| Biometric sync | AI pulls hardware data and reconciles automatically |

- Computes attendance % per student per course after every session
- Projects semester-end attendance based on remaining sessions
- Computes eligibility status: on track / at risk / ineligible

**Offline Attendance Marking (PWA — new in v1.1):**
Many Indian campuses have intermittent connectivity. Faculty cannot reliably use
the portal on 2G networks. The attendance marking screen is a Progressive Web App
with local-first storage.

Architecture: `web/src/views/AttendanceMarking/` uses IndexedDB (via Dexie) for
offline mark storage and a background sync worker that pushes marks to
`POST /api/v1/attendance/bulk-sync` when connectivity restores.

Marks stored offline carry a local UUID and `markedAt` ISO timestamp. The bulk-sync
endpoint is idempotent — duplicate submissions for the same `sessionId + studentId`
are silently ignored (last-write wins within the session window).

UI indicator: teal dot = online, amber = syncing, red = offline (pending marks).

**Feature flag:** `academics.offline_attendance_pwa` — off by default.
Enable via: `feature_flags.set("academics.offline_attendance_pwa", true, tenant_id)`

**Mass Bunk Detection (EC-ACA-03):**
Before sending any parent alert, the system runs a mass anomaly check:

```python
MASS_BUNK_THRESHOLD = 0.20  # < 20% session attendance halts individual alerts

if session.present_count / session.total_enrolled < MASS_BUNK_THRESHOLD:
    # Halt all 60+ individual parent alerts
    # Fire single HOD notification only
    publish DomainEvent("attendance.mass_bunk_detected", {
        "session_id": session.id,
        "attendance_pct": session_attendance_pct,
        "student_count": session.total_enrolled,
    })
```

HOD receives: "60 students absent in CS601 (10:00 AM). Mass event suspected.
No parent alerts sent. Please investigate and confirm."

HOD actions:
- **Confirm as mass bunk** → session marked `MASS_EXCUSED`, no alerts sent
- **Deny** → individual alerts sent retroactively to all absent students' parents

See `references/edge-cases.md` EC-ACA-03 for full implementation.

**Automated alerts (AI sends directly — no approval):**

| Threshold | Alert Sent To | Channel |
|-----------|---------------|---------| 
| Below 85% any course | Student | Portal + SMS |
| Below 80% any course | Student + Parent | Email + SMS |
| Below 75% any course | Student + Parent + Mentor | Email + SMS |
| Below 65% (critical) | Student + Parent + HOD + Registrar | Email + SMS |
| 3 consecutive absences | Mentor | Portal notification |

Note: All alerts above are suppressed if the session is flagged `MASS_EXCUSED`
or if the student carries `EXCUSED_LATE_JOINER` or `EXCUSED_DISRUPTION` status.

**AI auto-generates and delivers:**
- Daily attendance summary per course → Faculty + HOD (portal)
- Weekly digest → Faculty
- Monthly report → Registrar
- Pre-exam eligibility list → Exam Cell (at end of teaching weeks)
- Shortage letters for ineligible students → drafted and queued for Registrar approval

**Approver — Registrar (shortage letters only):**
- Reviews AI-drafted shortage letters
- Approves → auto-dispatched to student and parent

---

## Module 7 — Mentorship & Student Support

**AI Does:**
- Assigns every enrolled student a mentor at the moment of enrollment (from the
  Admissions event), distributing the batch evenly across available faculty mentors
- Builds a risk profile per student starting on Day 1 using admissions data as the
  baseline, enriched continuously with live signals

**Risk Score Inputs:**

| Signal | Weight | Source |
|--------|--------|--------|
| Attendance < 75% any course | High | Module 6 |
| IA score < 40% any course | High | Module 8 |
| 3+ consecutive absences | Medium | Module 6 |
| Low entrance score / 12th marks | Medium | Admissions |
| First-generation college student | Low | Admissions |
| Hostel resident (away from family) | Low | Admissions |
| 2+ assignment non-submissions | Medium | LMS |
| 7+ days without LMS login | Low | LMS |
| CO attainment below 40% in any CO | Medium | Module 11 (OBE) |

**Risk levels:** Green (on track) / Amber (needs monitoring) / Red (urgent intervention)

**For each mentorship cycle, AI:**
- Schedules the mandatory monthly mentor-mentee meeting (calendar invites sent to both)
- Prepares a pre-meeting briefing for the mentor: attendance trend, IA scores,
  assignment completion, risk trajectory, previous session notes — all pre-filled
- Sends reminder to mentor 48 hours before meeting
- After the meeting: pre-fills the session log with known data; mentor adds
  qualitative observations and approves
- Drafts next steps and follow-up actions from the meeting notes

**AI drafts all outgoing communications:**
- Parent alert letters (triggered at Amber/Red): student data pre-filled
- Counselor referral notes (when mentor flags "needs counselor")
- HOD escalation summaries (for Red-level students with no logged intervention in 7 days)

**SLA timers use absolute deadlines, not relative sleeps.**
Every approval task deadline is stored as a `TIMESTAMPTZ` at creation.
The Temporal workflow computes `timeout = deadline - workflow.now()` on resume.
See EC-CROSS-04 in `references/edge-cases.md`.

**Approver — Mentor (Faculty):**
- Reviews and sends AI-drafted parent communications
- Completes the meeting log (AI pre-fills, mentor adds observations)
- Approves counselor referral

**Auto-escalation (no approval needed):**
- Mentor misses meeting SLA → HOD notified
- Red-level student, no intervention logged in 7 days → HOD + Dean notified
- HOD steps in and sends parent communication directly if mentor SLA is breached

---

## Module 8 — Internal Assessment & Grading

**AI Does:**

**Before each IA:**
- Sends reminder to faculty to confirm readiness (based on calendar)
- Generates seating arrangement for offline IAs
- Creates the IA attendance session

**During / after the IA:**
- MCQ / objective: auto-graded against answer key immediately on submission
- Descriptive answers: AI scores per rubric with justification per answer —
  queued for faculty review with a `confidence_score` (0.0–1.0)
  - If `confidence_score < 0.6`: faculty sees only the rubric; AI score is hidden
    to prevent anchoring bias. Faculty grades independently first.
  - If faculty deviation from AI score > 20% of max marks: `faculty_override_reason`
    is required (a dropdown with structured categories)
  - If faculty confirms > 95% of AI scores without override across a semester:
    the pattern is flagged for HOD audit (possible rubber-stamping signal)
- Projects and assignments on LMS: AI evaluates against rubric, flags borderline cases

**Hard rule: AI-generated exam scores are DRAFT status only.**
`AnswerEvaluationRecord.ai_draft_score` is never promoted to final without
faculty confirmation. `faculty_final_score` is the only value that flows to
result computation. See `references/edge-cases.md` EC-EXM-05.

**After marks are confirmed:**
- Validates: marks within range, no blanks, statistical check
- Flags to HOD if: >80% of students scored below 50%, or distribution is unusually
  skewed
- Computes running internal score per student (all IA components weighted)
- Generates grade distribution report: mean, median, highest, lowest, % pass,
  % distinction → Faculty + HOD
- For OBE: computes CO attainment from this IA round (marks per question × CO weight)
  and updates `co_attainment_records` in Module 11

**Mid-semester progress report (auto, after IA2 — no approval needed):**
- Generated per student: attendance %, IA1 + IA2 scores, assignment completion,
  risk level, mentor note summary, CO attainment summary (OBE programs)
- Sent to: student, parent, mentor

**Approver — Faculty:**
- Reviews AI scoring for descriptive/rubric-based work
- Accepts or overrides per question
- Submits final marks

**Approver — HOD:**
- Reviews flagged grade distributions
- Approves moderation if needed
- Locks marks → results published to student portal automatically

---

## Module 9 — End-Semester Examination

This module coordinates with the Examination module (E06). The Academic module's role
is to supply: attendance data, IA marks, question papers, and faculty evaluator assignments.
The Examination module manages the end-semester lifecycle. See `examination_workflow.md`.

**AI Does (Academic module's contribution to examinations):**

**Pre-examination:**
- Generates eligibility list (attendance ≥ 75%, no dues, no disciplinary hold) —
  pulled from Module 6, Finance, Student Affairs automatically
- Generates hall tickets per student
- Generates seating arrangement
- Generates invigilator duty chart

**Examination day:**
- Attendance session created per exam; invigilator marks in system
- Malpractice flag raised by invigilator → AI logs incident, notifies Exam Cell +
  Registrar, triggers disciplinary workflow

**Post-examination:**
- Answer scripts assigned to evaluators (not the student's own faculty — blind evaluation)
- Evaluator enters marks; AI flags outliers for double evaluation
- AI combines internal marks (Module 8) + end-sem marks → final score → grade
- SGPA and CGPA computed per student
- Grade cards generated as PDFs
- CO attainment updated in Module 11 using final marks × question CO mapping

**Approver — Registrar:**
- Reviews generated results before publishing
- Approves → results published, grade cards downloadable, parent notification sent

---

## Module 10 — Progression, Records & Degree

**AI Does:**

**Progression (end of each semester):**
- Applies configured rules to every student's record: pass all → promote, backlog
  ≤ N → promote with backlog, backlog > N → detained, CGPA below minimum →
  academic probation
- Generates the full progression list
- Generates an exception list for human review: edge cases, borderline students,
  pending dues, pending disciplinary outcomes

**Document generation:**

| Document | Trigger | Gate |
|----------|---------|------|
| Grade Card | Results declared | Auto → student portal |
| Progress Report (mid-sem) | After IA2 | Auto → student + parent |
| Provisional Transcript | Student request | Registrar approves |
| Official Transcript | Graduation / transfer | Registrar approves |
| Degree Certificate | Clearance complete | Registrar approves |
| Migration Certificate | Student request | Registrar approves |
| Character Certificate | Student request | HOD approves |
| Shortage Letter | Attendance breach | Registrar approves |
| Detention Letter | Progression rule breach | Registrar approves |

**Degree audit (continuous, fully automated):**
- Tracks every student's progress against degree requirements each semester
- Flags unmet credits or incomplete courses every semester
- Runs final audit before graduation: credits, backlogs, dues, disciplinary record,
  OBE graduation requirements (for programs with CO attainment mandates)
- Sends clearance requests to Library, Hostel, Finance, Exam Cell — tracks responses

**Approver — Academic Committee:**
- Reviews exception list
- Makes final call on detained / probation cases

**Approver — Registrar:**
- Approves all document issuance
- Confirms final graduation list

---

## Module 11 — OBE / CO-PO Mapping (E20)

**Status: NOT BUILT — Sprint 9 in build plan.**
**Reference:** `references/architecture.md` §33, `references/gaps.md` E20 section.

Outcome-Based Education is mandatory for NBA accreditation. Every course must have
defined Course Outcomes (COs), every program must have defined Program Outcomes (POs),
and every assessment must map to specific COs.

### Schema

```sql
CREATE TABLE course_outcomes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL,
    course_id   UUID NOT NULL,
    co_code     TEXT NOT NULL,       -- 'CO1', 'CO2', etc.
    description TEXT NOT NULL,
    bloom_level TEXT NOT NULL        -- 'Remember'|'Understand'|'Apply'|'Analyse'|'Evaluate'|'Create'
);

CREATE TABLE program_outcomes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL,
    program_id  UUID NOT NULL,
    po_code     TEXT NOT NULL,       -- 'PO1' through 'PO12' (NBA standard)
    description TEXT NOT NULL
);

CREATE TABLE co_po_mapping (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL,
    co_id        UUID NOT NULL REFERENCES course_outcomes(id),
    po_id        UUID NOT NULL REFERENCES program_outcomes(id),
    correlation  INTEGER NOT NULL CHECK (correlation IN (1,2,3)),  -- 1=Low,2=Med,3=High
    UNIQUE(co_id, po_id)
);

CREATE TABLE co_attainment_records (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    co_id               UUID NOT NULL,
    semester            TEXT NOT NULL,
    direct_attainment   DECIMAL(5,2),   -- from exam marks (80% weight)
    indirect_attainment DECIMAL(5,2),   -- from student feedback survey (20% weight)
    final_attainment    DECIMAL(5,2),   -- weighted sum
    target_attainment   DECIMAL(5,2),   -- set by department (typically 60%)
    target_met          BOOLEAN GENERATED ALWAYS AS (final_attainment >= target_attainment) STORED
);
```

### AI-Assisted CO Generation

When a faculty member is assigned a course and the syllabus is on file, the AI
generates suggested COs before the faculty has to open the form. This eliminates
the blank-page problem that causes CO definition to be done poorly or skipped.

```
AI input:  official syllabus text
AI output: {
  "co_code": "CO1",
  "description": "Apply the principles of normalization to design efficient relational schemas",
  "bloom_level": "Apply",
  "topics_covered": ["1NF", "2NF", "3NF", "BCNF"],
  "suggested_assessment_types": ["problem_set", "design_exercise"]
}
```

Faculty reviews each suggested CO, edits the description or Bloom level, and approves.
HOD reviews the complete CO set for the course before locking.

**Task class: `GENERATION`** — routes to `llama3.1:8b` via the LLM router.
Never use `qwen2.5:1.5b` (EXTRACTION tier) for CO generation — the quality will be
insufficient for NBA audit purposes.

### CO-PO Mapping

After COs are approved, HOD maps each CO to the relevant POs with a correlation
score (1=Low, 2=Medium, 3=High) using a matrix interface. The AI pre-fills
suggested correlations based on keyword matching between CO descriptions and
standard NBA PO definitions. HOD adjusts and confirms.

### Attainment Computation

After every exam, CO attainment is automatically computed:

1. Each question in the paper carries a CO tag (set during paper creation in Module 4)
2. For each student: `co_score[CO_n] = sum(marks_on_questions_tagged_CO_n)`
3. `co_attainment[CO_n] = students_scoring_above_50%_on_CO_n / total_students × 100`
4. `direct_attainment = weighted average of co_attainment across all assessment types`
5. `indirect_attainment = average student feedback score for this course (from Module 7)`
6. `final_attainment = (direct_attainment × 0.80) + (indirect_attainment × 0.20)`

**Target attainment threshold** (configurable, default 60%):
If `final_attainment < target_attainment`, a flag is raised to HOD with a summary
of which students are below threshold on which COs. This feeds into the academic
risk module and the NBA SAR in the Regulatory module (E14).

### PO Attainment

PO attainment is derived from CO attainment using the CO-PO mapping correlation weights.
Computed semester-end, stored in `regulatory_metrics`, surfaced in the NBA dashboard.

### Approver Map for OBE

| Action | Approver | SLA |
|--------|----------|-----|
| CO definition (per course) | Faculty | 10 days after course assignment |
| CO set review | HOD | 5 days after faculty submission |
| CO-PO mapping | HOD | Before semester start |
| CO attainment targets | HOD | Before IA1 window |
| CO attainment report (post-exam) | Auto-generated | No approval — informational |

---

## Edge Cases — Production Failures & Fixes

The four edge cases below are P1 priority — implement in Sprint 3.
Full implementation specs are in `references/edge-cases.md`.

### EC-ACA-01 | Global Campus Disruption (P1 — Sprint 2)

**Trigger:** Unplanned campus closure — bandh, flood, power failure — with 40+ timetable
sessions already created for the next 2 days.

**What breaks:** 40+ attendance sessions have no faculty. Assignments have imminent
deadlines. Teaching week count drops below AICTE minimum.

**Fix: `GlobalRecalibrationWorkflow` (Temporal)**

```python
@workflow.defn
class GlobalRecalibrationWorkflow:
    @workflow.run
    async def run(self, req: RecalibrationRequest):
        # Step 1: Validate. Never override CoE-locked exam dates.
        affected_sessions = await workflow.execute_activity(
            identify_affected_sessions,
            args=[req.tenant_id, req.closure_start, req.closure_end]
        )
        locked_conflicts = [s for s in affected_sessions if s.is_exam_locked]
        if locked_conflicts:
            await workflow.execute_activity(
                notify_registrar_of_locked_conflicts, args=[locked_conflicts]
            )

        # Step 2: Generate preview. Registrar must confirm before execution.
        preview = await workflow.execute_activity(
            generate_recalibration_preview, args=[req, affected_sessions]
        )
        # "This shifts 847 sessions, 234 deadlines. 3 exam dates cannot move."
        confirmed = await workflow.wait_for_signal("registrar_confirmed", timeout=timedelta(hours=2))
        if not confirmed:
            return  # Registrar did not confirm — no changes made

        # Step 3: Execute. Mark cancelled sessions, shift future schedule forward.
        for session in affected_sessions:
            await workflow.execute_activity(
                mark_session_excused, args=[session.id, "EXCUSED_DISRUPTION", req.tenant_id]
            )
        await workflow.execute_activity(
            rerun_timetable_solver_for_catchup, args=[req]
        )
        await workflow.execute_activity(audit_recalibration, args=[req])
```

The `EXCUSED_DISRUPTION` status is enforced in the `attendance_eligibility` policy DSL
(not in application code) — excluded from eligibility denominator identically to
`EXCUSED_LATE_JOINER`.

### EC-ACA-02 | Faculty Attrition Mid-Semester (P1 — Sprint 2)

**Trigger:** A faculty member resigns, is terminated, or is hospitalized mid-semester,
leaving courses without an instructor.

**What breaks:** The timetable has their sessions for 10+ weeks. LMS shells are owned
by their account. IA papers scheduled for auto-release are linked to their approval.

**Fix: `CourseHandoverWorkflow` (Temporal)**

Key actions on `employee.separation_initiated`:
1. AI freezes all auto-releases on the departing faculty's courses
2. AI generates a `CourseHandoverPackage`: course state, sessions completed,
   pending assessments, student marks to date — snapshot at the moment of separation
3. LMS shell ownership transferred to HOD immediately
4. All timetable sessions for next 2 weeks flagged `SUBSTITUTE_REQUIRED` in red
5. HOD assigned 48h SLA to name a replacement; escalates to Dean on breach

```python
class CourseHandoverPackage(BaseModel):
    course_id: UUID
    faculty_id: UUID
    sessions_completed: int
    sessions_remaining: int
    pending_ia_papers: list[UUID]    # frozen — HOD must re-approve before release
    pending_assignments: list[UUID]  # frozen — HOD must re-approve before release
    marks_entered_to_date: dict      # {student_id: {ia1: score, ia2: score}}
    lms_access_transferred_to: UUID  # HOD's user ID
    snapshot_at: datetime
```

### EC-ACA-03 | Mass Bunk — False Positive Alert Prevention (P1 — Sprint 2)

**Trigger:** An entire section is absent from a session (college bus breakdown, power
outage in a building, student event clash). The individual alert pipeline would send
60+ parent alerts for a systemic event, not individual misconduct.

**Fix: Mass Anomaly Filter**

```python
MASS_BUNK_THRESHOLD = 0.20  # configurable per institution

async def process_attendance_alerts(session_id: UUID, tenant_id: UUID):
    session = await get_session(session_id, tenant_id)
    attendance_pct = session.present_count / session.total_enrolled

    if attendance_pct < MASS_BUNK_THRESHOLD:
        # Halt all individual alerts. Fire single HOD notification.
        await domain_event_bus.publish(DomainEvent(
            event_type="attendance.mass_bunk_detected",
            tenant_id=str(tenant_id),
            payload={
                "session_id": str(session_id),
                "attendance_pct": attendance_pct,
                "student_count": session.total_enrolled,
            }
        ))
        return  # Do not proceed to individual alert loop

    # Normal path — send individual alerts where thresholds breached
    for student in session.absent_students:
        await compute_and_send_attendance_alerts(student.id, session.course_id, tenant_id)
```

HOD confirmation workflow:
- Confirm mass bunk → session marked `MASS_EXCUSED` (pending Registrar approval)
- Deny → individual alerts sent retroactively

### EC-ACA-04 | Adjunct / Industry Faculty Variable Scheduling (P2 — Sprint 3)

**Trigger:** Visiting and industry faculty cannot commit to fixed weekly recurring slots.
The solver either rejects their assignment or generates unworkable slots.

**Fix: Ad-Hoc Scheduling Zone**

```python
class FacultySchedulingType(str, Enum):
    REGULAR = "regular"     # standard weekly recurring constraints
    AD_HOC  = "ad_hoc"      # visiting/adjunct — availability-driven, not pattern-driven

# In the timetable solver config:
for faculty in course.assigned_faculty:
    if faculty.scheduling_type == FacultySchedulingType.AD_HOC:
        solver.add_hard_constraint(
            FacultyAvailabilityConstraint(
                faculty_id=faculty.id,
                available_slots=faculty.declared_available_slots,
                constraint_type="HARD_AVAILABILITY"
                # Bypass weekly pattern checks entirely
            )
        )
```

Adjunct faculty submit availability week-by-week via the faculty portal.
The solver treats these as hard constraints — the same weight as room capacity
and section double-booking — not soft preferences.

---

## Complete System Flow

```
[ADMISSIONS MODULE] ──► EVENT: student.enrolled
                                │
          ┌─────────────────────┴──────────────────────┐
          │         ACADEMIC MODULE INITIALIZES         │
          └─────────────────────┬──────────────────────┘
                                │
          ┌─────────────────────▼──────────────────────┐
          │  Module 1: Calendar                        │
          │  AI drafts ──► Registrar approves          │
          │  EC-ACA-01: GlobalRecalibrationWorkflow    │
          └─────────────────────┬──────────────────────┘
                                │
          ┌─────────────────────▼──────────────────────┐
          │  Module 2: Course Mapping                  │
          │  AI maps ──► HOD approves                  │
          │  EC-ACA-04: Ad-Hoc Zone for adjunct        │
          └─────────────────────┬──────────────────────┘
                                │
          ┌─────────────────────▼──────────────────────┐
          │  Module 3: Content Generation              │
          │  AI generates PPTs / outlines / handbooks  │
          │  ──► Faculty approves per course           │
          │  Similarity check: pgvector dedup          │
          └─────────────────────┬──────────────────────┘
                                │
          ┌─────────────────────▼──────────────────────┐
          │  Module 4: Assessments                     │
          │  AI drafts assignments / papers / rubrics  │
          │  CO tags on every question (OBE)           │
          │  ──► Faculty approves ──► HOD approves IAs │
          └─────────────────────┬──────────────────────┘
                                │
          ┌─────────────────────▼──────────────────────┐
          │  Module 5: Timetable                       │
          │  AI (OR-Tools solver) generates            │
          │  ──► Registrar approves                    │
          │  EC-ACA-02: CourseHandoverWorkflow         │
          └─────────────────────┬──────────────────────┘
                                │
                    ════════════▼═════════════
                       SEMESTER IN PROGRESS
                    ══════════════════════════
                                │
          ┌─────────────────────▼──────────────────────┐
          │  Module 6: Attendance                      │
          │  Sessions → Marking (online + offline PWA) │
          │  EC-ACA-03: Mass Bunk Filter               │
          │  Alerts → Reports                          │
          │  Shortage letters ──► Registrar approves   │
          └─────────────────────┬──────────────────────┘
                                │
          ┌─────────────────────▼──────────────────────┐
          │  Module 7: Mentorship                      │
          │  Risk scoring (incl. CO attainment)        │
          │  Briefings → Draft comms                   │
          │  ──► Mentor approves outgoing comms        │
          └─────────────────────┬──────────────────────┘
                                │
          ┌─────────────────────▼──────────────────────┐
          │  Module 8: Internal Assessment             │
          │  Auto-grade → AI DRAFT only (EC-EXM-05)   │
          │  CO attainment updated per IA round        │
          │  ──► Faculty reviews ──► HOD locks         │
          └─────────────────────┬──────────────────────┘
                                │
          ┌─────────────────────▼──────────────────────┐
          │  Module 9: End-Semester Exam               │
          │  Eligibility → Hall tickets → Results      │
          │  CO attainment updated (final)             │
          │  ──► Registrar approves publish            │
          └─────────────────────┬──────────────────────┘
                                │
          ┌─────────────────────▼──────────────────────┐
          │  Module 10: Progression & Records          │
          │  AI computes → documents generated         │
          │  ──► Academic Committee (exceptions)       │
          │  ──► Registrar (all document issuance)     │
          └─────────────────────┬──────────────────────┘
                                │
          ┌─────────────────────▼──────────────────────┐
          │  Module 11: OBE / CO-PO (E20)              │
          │  AI generates COs → Faculty approves       │
          │  HOD maps CO-PO → Attainment computed      │
          │  ──► Feeds Regulatory E14 (NBA SAR)        │
          └─────────────────────────────────────────────┘
```

---

## Notification Map

| Event | Student | Faculty | HOD | Registrar | Parent |
|-------|---------|---------|-----|-----------|--------|
| Enrolled → module initialized | Email + Portal | Email (mentor assigned) | — | — | Email |
| Timetable published | Email + Portal | Email | Portal | — | — |
| New course material available | Portal | — | — | — | — |
| Assignment posted | Portal + SMS | — | — | — | — |
| Assignment deadline T-2 | SMS | — | — | — | — |
| Attendance < 85% | SMS + Portal | — | — | — | — |
| Attendance < 75% | SMS + Email | Email (mentor) | Email | Email | SMS + Email |
| 3 consecutive absences | — | Email (mentor) | — | — | — |
| Mass bunk detected | — | — | Email (single alert) | — | — |
| Risk level → Amber | Portal | Email (mentor) | — | — | — |
| Risk level → Red | Email + SMS | Email (mentor) | Email | — | Email + SMS |
| Mentorship meeting reminder | Portal | Email + SMS | — | — | — |
| IA result published | Portal + SMS | — | — | — | — |
| Progress report (mid-sem) | Email + Portal | — | — | — | Email |
| Hall ticket ready | Email + Portal | — | — | — | — |
| End-sem results published | Email + Portal | — | — | — | Email |
| Detained / backlog | Email + Portal | Email (mentor) | Email | Email | Email |
| Document ready (on request) | Email + Portal | — | — | — | — |
| CO attainment below target | — | Email | Email (HOD summary) | — | — |
| Faculty course handover required | — | Email (departing + HOD) | Email (urgent) | — | — |
| Campus recalibration triggered | Email + Portal | Email | Email | Email (preview) | — |

---

## SLA Defaults (Configurable per Institution)

| Approval Gate | SLA Window | If Breached |
|---------------|-----------|-------------|
| Course outline (Faculty) | 5 working days after semester setup | Escalates to HOD |
| PPT review (Faculty) | 3 days per deck (batched) | Auto-published to faculty-only view |
| Assignment approval (Faculty) | 48 hours | Auto-published to students |
| IA paper — Faculty | 7 days before IA date | Escalates to HOD |
| IA paper — HOD | 3 days before IA date | Escalates to Exam Cell |
| Marks entry (Faculty) | 5 days after IA | Escalates to HOD |
| Marks moderation (HOD) | 3 days after faculty submission | Escalates to Exam Cell |
| Results approval (Registrar) | 3 days after moderation | Escalates to Dean |
| Document issuance (Registrar) | 3 working days after request | Student notified of delay |
| Mentor meeting log | 24 hours after meeting | HOD notified |
| Parent communication (Mentor) | 48 hours after AI draft | HOD sends directly |
| CO definition (Faculty) | 10 days after course assignment | Escalates to HOD |
| CO-PO mapping (HOD) | Before semester start | Escalates to Academic Committee |
| Faculty handover confirmation (HOD) | 48 hours after separation event | Escalates to Dean |
| Mass bunk confirmation (HOD) | 24 hours after detection | Auto-dismissed; alerts sent retroactively |
| Global recalibration confirmation (Registrar) | 2 hours after preview sent | Workflow cancelled; no changes made |

**All SLA timers use absolute deadline timestamps stored at task creation.**
Never compute `sleep(duration)` in Temporal workflows. See EC-CROSS-04.

---

## What Actors Never Do (AI Handles Completely)

- Create attendance sessions
- Schedule or draft mentorship meeting invites
- Draft parent alerts or shortage notices
- Compute attendance percentages or exam eligibility
- Build or update risk profiles
- Generate grade distribution or analytics reports
- Calculate SGPA / CGPA
- Create LMS course shells or enroll students into courses
- Generate hall tickets, seating arrangements, or invigilator charts
- Assign roll numbers (handled in Admissions module)
- Send routine notifications, reminders, or deadline nudges
- Assemble transcripts, grade cards, or degree certificates
- Track degree audit progress
- Generate CO suggestions from syllabus text
- Compute CO attainment scores after each assessment
- Derive PO attainment from CO-PO mapping weights
- Tag questions with CO codes in the question bank
- Check for content similarity across course outlines
- Sync offline attendance marks when connectivity restores

---

## Domain Events — Fired and Consumed

**Fired by Academic module:**

| Event | Consumed By | Payload |
|-------|-------------|---------|
| `attendance.session_created` | — (internal) | session_id, course_id, faculty_id, scheduled_at |
| `attendance.mass_bunk_detected` | HOD dashboard | session_id, attendance_pct, student_count |
| `attendance.threshold_breached` | Student Services (mentorship) | student_id, course_id, current_pct, threshold |
| `marks.ia_locked` | Examinations | course_id, batch_id, ia_number, average_score |
| `progression.computed` | Registrar dashboard | batch_id, semester, promote_count, detain_count |
| `co_attainment.updated` | Regulatory E14 (NBA) | co_id, semester, final_attainment, target_met |
| `academics.faculty_activity_summary` | HR (CAS appraisal) | faculty_id, semester, lectures_delivered, students_mentored |

**Consumed by Academic module:**

| Event | Source | Action |
|-------|--------|--------|
| `student.enrolled` | Admissions | Initialize all academic pipelines for student |
| `student.cancelled` | Admissions | Freeze student record, mark sessions retrospectively |
| `employee.separation_initiated` | HR | Trigger CourseHandoverWorkflow |
| `student.dues_cleared` | Finance | Update exam eligibility flag |
| `hostel.checkin` | Student Services | Update risk baseline (hostel residency flag) |
| `risk.score_red` | Mentorship (internal) | Trigger counseling referral via Student Services |
| `academic_calendar.updated` | Calendar (internal) | Cascade session and deadline changes |

---

## Configuration Parameters

| Parameter | Default | Configurable |
|-----------|---------|-------------|
| Minimum teaching days per semester | 90 (AICTE mandate) | No |
| Attendance threshold for eligibility | 75% | Yes |
| Condonation range | 65–74% with valid reason | Yes |
| Mass bunk threshold (suppresses individual alerts) | 20% | Yes |
| AI confidence threshold (hide AI score from evaluator) | 0.60 | Yes |
| Faculty override reason required (AI deviation) | >20% of max marks | Yes |
| CO target attainment threshold | 60% | Yes |
| CO attainment weight: direct vs indirect | 80:20 | Yes |
| Offline PWA feature flag | Disabled | Yes |
| Content similarity alert threshold | 0.85 cosine similarity | Yes |
| Adjunct scheduling: ad-hoc zone | Disabled by default | Yes |
| Risk signal: LMS inactivity threshold | 7 days | Yes |
| Risk signal: consecutive absence alert | 3 sessions | Yes |
| SLA: course outline submission | 5 working days | Yes |
| SLA: IA paper — HOD review | 3 days before IA | Yes |
| SLA: mentor meeting log | 24 hours | Yes |

---

*Document version: 2.0 | March 2026*
*Connected to: admissions_workflow.md → academic_operations_workflow.md →*
*examination_workflow.md → student_services_workflow.md → finance_workflow.md →*
*hr_payroll_workflow.md → regulatory_accreditation_workflow.md*
*Full student lifecycle: Lead Captured → Graduated*
*QUAICU Pvt. Ltd. | quaicu.org | Hyderabad, India | Confidential*
