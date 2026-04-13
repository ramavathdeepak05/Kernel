"""In-house Learning Management — replaces Moodle LMS stub

Revision ID: 0041
Revises: 0040
Create Date: 2026-03-28

Changes
───────
1. course_materials     — faculty uploads + AI-generated content per course
                          (DRAFT → PUBLISHED → ARCHIVED state machine)
2. assignments          — coursework tasks linked to course outcomes with due dates
                          (DRAFT → PUBLISHED → CLOSED → ARCHIVED)
3. assignment_submissions — student submissions with full grading lifecycle
                          (DRAFT → SUBMITTED → UNDER_REVIEW → GRADED → RETURNED)
4. RLS tenant isolation on all three tables
5. PolicyKey seeds for late-penalty defaults
6. DRAFT prompt seeds for four AI content generation types
"""

from alembic import op


revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. course_materials
    # -------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS course_materials (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id          UUID NOT NULL,
            course_id       UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
            co_id           UUID REFERENCES course_outcomes(id),
            title           VARCHAR(300) NOT NULL,
            material_type   VARCHAR(30) NOT NULL
                CHECK (material_type IN (
                    'LECTURE_NOTES','LESSON_PLAN','QUIZ',
                    'ASSIGNMENT_BRIEF','REFERENCE','VIDEO_LINK','OTHER'
                )),
            content_body    TEXT,
            file_url        TEXT,
            is_ai_generated BOOLEAN NOT NULL DEFAULT FALSE,
            ai_prompt_name  VARCHAR(100),
            ai_prompt_version INT,
            status          VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
                CHECK (status IN ('DRAFT','PUBLISHED','ARCHIVED')),
            visible_to_students BOOLEAN NOT NULL DEFAULT FALSE,
            week_number     INT,
            created_by      UUID NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ,
            published_at    TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_course_materials_course
            ON course_materials(course_id, status)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_course_materials_org
            ON course_materials(org_id, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_course_materials_co
            ON course_materials(co_id) WHERE co_id IS NOT NULL
    """)

    # -------------------------------------------------------------------------
    # 2. assignments
    # -------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id          UUID NOT NULL,
            course_id       UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
            co_id           UUID REFERENCES course_outcomes(id),
            title           VARCHAR(300) NOT NULL,
            description     TEXT NOT NULL,
            max_marks       DECIMAL(6,2) NOT NULL DEFAULT 100,
            passing_marks   DECIMAL(6,2),
            due_date        TIMESTAMPTZ NOT NULL,
            allow_late      BOOLEAN NOT NULL DEFAULT FALSE,
            late_penalty_pct DECIMAL(5,2) DEFAULT 0,
            is_ai_generated BOOLEAN NOT NULL DEFAULT FALSE,
            ai_prompt_name  VARCHAR(100),
            ai_prompt_version INT,
            status          VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
                CHECK (status IN ('DRAFT','PUBLISHED','CLOSED','ARCHIVED')),
            created_by      UUID NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ,
            published_at    TIMESTAMPTZ,
            closed_at       TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_assignments_course
            ON assignments(course_id, status)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_assignments_due_date
            ON assignments(due_date) WHERE status = 'PUBLISHED'
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_assignments_org
            ON assignments(org_id)
    """)

    # -------------------------------------------------------------------------
    # 3. assignment_submissions
    # -------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS assignment_submissions (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id          UUID NOT NULL,
            assignment_id   UUID NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
            student_id      UUID NOT NULL REFERENCES students(id),
            enrollment_id   UUID REFERENCES course_enrollments(id),
            content_text    TEXT,
            file_url        TEXT,
            submitted_at    TIMESTAMPTZ,
            is_late         BOOLEAN NOT NULL DEFAULT FALSE,
            status          VARCHAR(20) NOT NULL DEFAULT 'DRAFT'
                CHECK (status IN (
                    'DRAFT','SUBMITTED','UNDER_REVIEW','GRADED','RETURNED'
                )),
            marks_awarded   DECIMAL(6,2),
            late_deduction  DECIMAL(6,2) DEFAULT 0,
            effective_marks DECIMAL(6,2),
            feedback        TEXT,
            graded_by       UUID,
            graded_at       TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ,
            UNIQUE(assignment_id, student_id)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_submissions_assignment
            ON assignment_submissions(assignment_id, status)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_submissions_student
            ON assignment_submissions(student_id, org_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_submissions_pending_review
            ON assignment_submissions(assignment_id, submitted_at)
            WHERE status = 'SUBMITTED'
    """)

    # -------------------------------------------------------------------------
    # 4. RLS tenant isolation
    # -------------------------------------------------------------------------
    op.execute("ALTER TABLE course_materials ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_course_materials ON course_materials")
    op.execute("""
        CREATE POLICY tenant_isolation_course_materials ON course_materials
            FOR ALL USING (org_id::text = current_setting('alis.current_tenant', true))
    """)

    op.execute("ALTER TABLE assignments ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_assignments ON assignments")
    op.execute("""
        CREATE POLICY tenant_isolation_assignments ON assignments
            FOR ALL USING (org_id::text = current_setting('alis.current_tenant', true))
    """)

    op.execute("ALTER TABLE assignment_submissions ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_assignment_submissions ON assignment_submissions")
    op.execute("""
        CREATE POLICY tenant_isolation_assignment_submissions ON assignment_submissions
            FOR ALL USING (org_id::text = current_setting('alis.current_tenant', true))
    """)

    # -------------------------------------------------------------------------
    # 5. PolicyKey seeds
    # -------------------------------------------------------------------------
    op.execute("""
        INSERT INTO institution_policies
            (id, org_id, key, value, description, category, is_active, created_by)
        SELECT
            gen_random_uuid(),
            id,
            'learning.assignment.late_penalty_pct_default',
            '10'::jsonb,
            'Default % of max_marks deducted per day for late assignment submissions',
            'academics',
            TRUE,
            'system'
        FROM organizations
        WHERE status = 'ACTIVE'
        ON CONFLICT (org_id, key) DO NOTHING
    """)

    op.execute("""
        INSERT INTO institution_policies
            (id, org_id, key, value, description, category, is_active, created_by)
        SELECT
            gen_random_uuid(),
            id,
            'learning.assignment.max_late_days',
            '3'::jsonb,
            'Maximum days past due date that late submissions are accepted',
            'academics',
            TRUE,
            'system'
        FROM organizations
        WHERE status = 'ACTIVE'
        ON CONFLICT (org_id, key) DO NOTHING
    """)

    op.execute("""
        INSERT INTO institution_policies
            (id, org_id, key, value, description, category, is_active, created_by)
        SELECT
            gen_random_uuid(),
            id,
            'learning.auto_begin_review',
            'false'::jsonb,
            'Auto-transition submissions to UNDER_REVIEW on receipt (default: faculty manually begins review)',
            'academics',
            TRUE,
            'system'
        FROM organizations
        WHERE status = 'ACTIVE'
        ON CONFLICT (org_id, key) DO NOTHING
    """)

    # -------------------------------------------------------------------------
    # 6. DRAFT prompt seeds (tenant_id='system'; activated per-org via seed.py)
    # -------------------------------------------------------------------------
    op.execute("""
        INSERT INTO prompt_registry
            (id, tenant_id, name, version, content, format, description,
             status, content_hash, created_by, created_by_role, created_at)
        VALUES
        (
            gen_random_uuid(), 'system', 'learning.lecture_notes', 1,
            $PROMPT$You are an expert academic content creator for {{ course_name }} ({{ course_code }}).

Course Outcomes addressed:
{% for i in range(co_codes | length) %}
- {{ co_codes[i] }}: {{ co_descriptions[i] }} (Bloom level: {{ bloom_levels[i] }})
{% endfor %}

Syllabus topics for this session: {{ syllabus_topics | join(', ') }}

Task: Generate detailed lecture notes for a {{ lecture_duration_minutes | default(60) }}-minute class covering the above topics.

Requirements:
- Structure: Introduction → Core Concepts → Worked Examples → Summary → Review Questions
- Explicitly align each section to the stated Course Outcomes (cite CO codes)
- Use illustrative examples appropriate for undergraduate students
- End with 3–5 review questions tagged to CO codes
- Output as well-structured markdown

Respond ONLY with valid JSON:
{
  "decision": "lecture_notes_generated",
  "confidence_score": 0.9,
  "confidence_tier": "HIGH",
  "state_impact": "Draft",
  "reasoning": "<brief rationale>",
  "generation_type": "lecture_notes",
  "title": "<lecture title>",
  "body": "<full markdown content>",
  "word_count": 0,
  "co_alignment": ["CO1"]
}$PROMPT$,
            'jinja2',
            'Generates lecture notes from CO + syllabus context (Learning module)',
            'DRAFT',
            md5('learning.lecture_notes.v1'),
            'system', 'SYSTEM', NOW()
        ),
        (
            gen_random_uuid(), 'system', 'learning.quiz_questions', 1,
            $PROMPT$You are an assessment designer for {{ course_name }} ({{ course_code }}).

Course Outcomes:
{% for i in range(co_codes | length) %}
- {{ co_codes[i] }}: {{ co_descriptions[i] }} (Bloom level: {{ bloom_levels[i] }})
{% endfor %}

Topics covered: {{ syllabus_topics | join(', ') }}

Task: Generate {{ num_questions | default(10) }} {{ question_type | default('MCQ') }} quiz questions at {{ difficulty | default('MEDIUM') }} difficulty.

Requirements:
- Each question tests one or more Course Outcomes (tag the CO)
- For MCQ: 4 options, one correct answer marked with [CORRECT]
- For SHORT/LONG: provide a model answer outline and marking scheme
- Bloom's level must match the CO descriptor

Respond ONLY with valid JSON:
{
  "decision": "quiz_generated",
  "confidence_score": 0.9,
  "confidence_tier": "HIGH",
  "state_impact": "Draft",
  "reasoning": "<brief rationale>",
  "generation_type": "quiz_questions",
  "title": "Quiz — {{ course_code }}",
  "body": "<numbered questions in markdown>",
  "word_count": 0,
  "co_alignment": ["CO1"]
}$PROMPT$,
            'jinja2',
            'Generates quiz questions from CO + syllabus context (Learning module)',
            'DRAFT',
            md5('learning.quiz_questions.v1'),
            'system', 'SYSTEM', NOW()
        ),
        (
            gen_random_uuid(), 'system', 'learning.assignment_questions', 1,
            $PROMPT$You are a faculty member designing coursework for {{ course_name }} ({{ course_code }}).

Course Outcomes:
{% for i in range(co_codes | length) %}
- {{ co_codes[i] }}: {{ co_descriptions[i] }} (Bloom level: {{ bloom_levels[i] }})
{% endfor %}

Topics: {{ syllabus_topics | join(', ') }}

Task: Generate {{ num_questions | default(3) }} assignment questions, each worth {{ marks_per_q | default(33) }} marks.

Requirements:
- Higher-order thinking required (Analysis / Evaluation / Creation)
- Each question references at least one CO
- Clear instructions and expected deliverables
- Rubric outline per question

Respond ONLY with valid JSON:
{
  "decision": "assignment_generated",
  "confidence_score": 0.9,
  "confidence_tier": "HIGH",
  "state_impact": "Draft",
  "reasoning": "<brief rationale>",
  "generation_type": "assignment_questions",
  "title": "Assignment — {{ course_code }}",
  "body": "<assignment questions and rubric in markdown>",
  "word_count": 0,
  "co_alignment": ["CO1"]
}$PROMPT$,
            'jinja2',
            'Generates assignment questions with rubric from CO + syllabus context',
            'DRAFT',
            md5('learning.assignment_questions.v1'),
            'system', 'SYSTEM', NOW()
        ),
        (
            gen_random_uuid(), 'system', 'learning.lesson_plan', 1,
            $PROMPT$You are a curriculum developer for {{ course_name }} ({{ course_code }}).

Course Outcomes:
{% for i in range(co_codes | length) %}
- {{ co_codes[i] }}: {{ co_descriptions[i] }} (Bloom level: {{ bloom_levels[i] }})
{% endfor %}

Topics for {{ num_weeks | default(1) }} week(s): {{ syllabus_topics | join(', ') }}

Task: Create a detailed lesson plan using the {{ teaching_method | default('lecture') }} method.

Include for each session:
- Session objective mapped to CO
- Content outline in 15-minute blocks
- Teaching activities and resources
- Formative assessment method
- Estimated time per section

Respond ONLY with valid JSON:
{
  "decision": "lesson_plan_generated",
  "confidence_score": 0.9,
  "confidence_tier": "HIGH",
  "state_impact": "Draft",
  "reasoning": "<brief rationale>",
  "generation_type": "lesson_plan",
  "title": "Lesson Plan — {{ course_code }} Week {{ week_number | default(1) }}",
  "body": "<lesson plan in structured markdown>",
  "word_count": 0,
  "co_alignment": ["CO1"]
}$PROMPT$,
            'jinja2',
            'Generates weekly lesson plan from CO + syllabus context',
            'DRAFT',
            md5('learning.lesson_plan.v1'),
            'system', 'SYSTEM', NOW()
        )
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS assignment_submissions CASCADE")
    op.execute("DROP TABLE IF EXISTS assignments CASCADE")
    op.execute("DROP TABLE IF EXISTS course_materials CASCADE")
    op.execute("""
        DELETE FROM institution_policies
        WHERE key IN (
            'learning.assignment.late_penalty_pct_default',
            'learning.assignment.max_late_days',
            'learning.auto_begin_review'
        )
    """)
    op.execute("""
        DELETE FROM prompt_registry
        WHERE name IN (
            'learning.lecture_notes',
            'learning.quiz_questions',
            'learning.assignment_questions',
            'learning.lesson_plan'
        ) AND tenant_id = 'system'
    """)
