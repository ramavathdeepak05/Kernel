"""
0013 — Missing indexes on hot-path columns (Hardening C)

Adds indexes on:
- org_id / tenant_id columns (tenant isolation filter — every query)
- FK _id columns without indexes (JOIN targets)
- status columns (common WHERE filter)

These were omitted from 0001–0012.
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def _safe_index(index_name: str, table: str, column: str) -> str:
    """Returns a DO block that creates the index only if the column exists."""
    return f"""
DO $$ BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = '{table}' AND column_name = '{column}'
  ) THEN
    EXECUTE 'CREATE INDEX IF NOT EXISTS {index_name} ON {table}({column})';
  END IF;
END $$"""


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # E01 Core / Auth
    # -------------------------------------------------------------------------
    op.execute(_safe_index("idx_organisations_status", "organisations", "status"))
    op.execute(_safe_index("idx_users_tenant_id", "users", "tenant_id"))
    op.execute(_safe_index("idx_roles_org_id", "roles", "org_id"))
    op.execute(_safe_index("idx_workflows_org_id", "workflows", "org_id"))
    op.execute(_safe_index("idx_workflows_status", "workflows", "status"))
    op.execute(_safe_index("idx_approval_requests_org_id", "approval_requests", "org_id"))
    op.execute(_safe_index("idx_approval_requests_workflow_id", "approval_requests", "workflow_id"))

    # -------------------------------------------------------------------------
    # E04 Admissions
    # -------------------------------------------------------------------------
    op.execute(_safe_index("idx_counsellor_embeddings_org_id", "counsellor_embeddings", "org_id"))
    op.execute(_safe_index("idx_counsellor_embeddings_counsellor_id", "counsellor_embeddings", "counsellor_id"))
    op.execute(_safe_index("idx_lead_merge_log_org_id", "lead_merge_log", "org_id"))
    op.execute(_safe_index("idx_counsellor_assignments_counsellor_id", "counsellor_assignments", "counsellor_id"))
    op.execute(_safe_index("idx_intake_quality_scores_org_id", "intake_quality_scores", "org_id"))
    op.execute(_safe_index("idx_intake_quality_scores_batch_id", "intake_quality_scores", "batch_id"))
    op.execute(_safe_index("idx_students_applicant_id", "students", "applicant_id"))

    # -------------------------------------------------------------------------
    # P0 Platform
    # -------------------------------------------------------------------------
    op.execute(_safe_index("idx_domain_events_entity_id", "domain_events", "entity_id"))
    op.execute(_safe_index("idx_academic_calendars_org_id", "academic_calendars", "org_id"))
    op.execute(_safe_index("idx_calendar_phases_calendar_id", "calendar_phases", "calendar_id"))
    op.execute(_safe_index("idx_org_api_keys_created_by", "org_api_keys", "created_by"))

    # -------------------------------------------------------------------------
    # E05 Academics
    # -------------------------------------------------------------------------
    op.execute(_safe_index("idx_courses_org_id", "courses", "org_id"))
    op.execute(_safe_index("idx_courses_status", "courses", "status"))
    op.execute(_safe_index("idx_course_enrollments_status", "course_enrollments", "status"))
    op.execute(_safe_index("idx_faculty_assignments_org_id", "faculty_assignments", "org_id"))
    op.execute(_safe_index("idx_timetable_slots_org_id", "timetable_slots", "org_id"))
    op.execute(_safe_index("idx_attendance_sessions_org_id", "attendance_sessions", "org_id"))
    op.execute(_safe_index("idx_attendance_sessions_course_id", "attendance_sessions", "course_id"))
    op.execute(_safe_index("idx_attendance_records_org_id", "attendance_records", "org_id"))
    op.execute(_safe_index("idx_attendance_records_status", "attendance_records", "status"))

    # -------------------------------------------------------------------------
    # E06 Examinations
    # -------------------------------------------------------------------------
    op.execute(_safe_index("idx_exam_schedules_course_id", "exam_schedules", "course_id"))
    op.execute(_safe_index("idx_exam_schedules_status", "exam_schedules", "status"))
    op.execute(_safe_index("idx_hall_tickets_org_id", "hall_tickets", "org_id"))
    op.execute(_safe_index("idx_grades_exam_schedule_id", "grades", "exam_schedule_id"))
    op.execute(_safe_index("idx_semester_results_org_id", "semester_results", "org_id"))
    op.execute(_safe_index("idx_semester_results_status", "semester_results", "status"))
    op.execute(_safe_index("idx_transcripts_org_id", "transcripts", "org_id"))
    op.execute(_safe_index("idx_transcripts_student_id", "transcripts", "student_id"))
    op.execute(_safe_index("idx_reeval_requests_org_id", "reeval_requests", "org_id"))
    op.execute(_safe_index("idx_reeval_requests_student_id", "reeval_requests", "student_id"))
    op.execute(_safe_index("idx_reeval_requests_grade_id", "reeval_requests", "grade_id"))
    op.execute(_safe_index("idx_reeval_requests_status", "reeval_requests", "status"))

    # -------------------------------------------------------------------------
    # E07 Finance
    # -------------------------------------------------------------------------
    op.execute(_safe_index("idx_fee_structures_program_id", "fee_structures", "program_id"))
    op.execute(_safe_index("idx_fee_structures_created_by", "fee_structures", "created_by"))
    op.execute(_safe_index("idx_student_invoices_fee_structure_id", "student_invoices", "fee_structure_id"))
    op.execute(_safe_index("idx_payments_status", "payments", "status"))
    op.execute(_safe_index("idx_scholarships_org_id", "scholarships", "org_id"))
    op.execute(_safe_index("idx_scholarships_created_by", "scholarships", "created_by"))
    op.execute(_safe_index("idx_scholarship_assignments_org_id", "scholarship_assignments", "org_id"))
    op.execute(_safe_index("idx_scholarship_assignments_scholarship_id", "scholarship_assignments", "scholarship_id"))
    op.execute(_safe_index("idx_scholarship_assignments_status", "scholarship_assignments", "status"))
    op.execute(_safe_index("idx_fee_waivers_invoice_id", "fee_waivers", "invoice_id"))
    op.execute(_safe_index("idx_fee_waivers_status", "fee_waivers", "status"))

    # -------------------------------------------------------------------------
    # E08 HR & Staff
    # -------------------------------------------------------------------------
    op.execute(_safe_index("idx_leave_types_org_id", "leave_types", "org_id"))
    op.execute(_safe_index("idx_leave_requests_leave_type_id", "leave_requests", "leave_type_id"))
    op.execute(_safe_index("idx_payroll_components_org_id", "payroll_components", "org_id"))
    op.execute(_safe_index("idx_staff_salary_structures_org_id", "staff_salary_structures", "org_id"))
    op.execute(_safe_index("idx_staff_salary_structures_staff_id", "staff_salary_structures", "staff_id"))
    op.execute(_safe_index("idx_staff_salary_structures_created_by", "staff_salary_structures", "created_by"))
    op.execute(_safe_index("idx_payslips_status", "payslips", "status"))
    op.execute(_safe_index("idx_performance_reviews_org_id", "performance_reviews", "org_id"))
    op.execute(_safe_index("idx_performance_reviews_reviewer_id", "performance_reviews", "reviewer_id"))
    op.execute(_safe_index("idx_performance_reviews_status", "performance_reviews", "status"))
    op.execute(_safe_index("idx_staff_attendance_status", "staff_attendance", "status"))

    # -------------------------------------------------------------------------
    # E09 Student Services
    # -------------------------------------------------------------------------
    op.execute(_safe_index("idx_hostel_blocks_org_id", "hostel_blocks", "org_id"))
    op.execute(_safe_index("idx_hostel_blocks_warden_id", "hostel_blocks", "warden_id"))
    op.execute(_safe_index("idx_hostel_rooms_org_id", "hostel_rooms", "org_id"))
    op.execute(_safe_index("idx_hostel_rooms_block_id", "hostel_rooms", "block_id"))
    op.execute(_safe_index("idx_hostel_allocations_org_id", "hostel_allocations", "org_id"))
    op.execute(_safe_index("idx_hostel_complaints_student_id", "hostel_complaints", "student_id"))
    op.execute(_safe_index("idx_hostel_complaints_room_id", "hostel_complaints", "room_id"))
    op.execute(_safe_index("idx_hostel_complaints_assigned_to", "hostel_complaints", "assigned_to"))
    op.execute(_safe_index("idx_library_borrowings_org_id", "library_borrowings", "org_id"))
    op.execute(_safe_index("idx_transport_routes_org_id", "transport_routes", "org_id"))
    op.execute(_safe_index("idx_transport_assignments_org_id", "transport_assignments", "org_id"))
    op.execute(_safe_index("idx_transport_assignments_student_id", "transport_assignments", "student_id"))
    op.execute(_safe_index("idx_counselling_sessions_org_id", "counselling_sessions", "org_id"))
    op.execute(_safe_index("idx_counselling_referrals_org_id", "counselling_referrals", "org_id"))
    op.execute(_safe_index("idx_counselling_referrals_student_id", "counselling_referrals", "student_id"))
    op.execute(_safe_index("idx_counselling_referrals_status", "counselling_referrals", "status"))

    # -------------------------------------------------------------------------
    # E10 Communication Hub
    # -------------------------------------------------------------------------
    op.execute(_safe_index("idx_notification_logs_org_id", "notification_logs", "org_id"))
    op.execute(_safe_index("idx_in_app_notifications_org_id", "in_app_notifications", "org_id"))
    op.execute(_safe_index("idx_announcements_created_by", "announcements", "created_by"))
    op.execute(_safe_index("idx_announcement_reads_announcement_id", "announcement_reads", "announcement_id"))
    op.execute(_safe_index("idx_announcement_reads_user_id", "announcement_reads", "user_id"))
    op.execute(_safe_index("idx_bulk_message_jobs_org_id", "bulk_message_jobs", "org_id"))
    op.execute(_safe_index("idx_bulk_message_jobs_status", "bulk_message_jobs", "status"))
    op.execute(_safe_index("idx_bulk_message_jobs_created_by", "bulk_message_jobs", "created_by"))

    # -------------------------------------------------------------------------
    # E11 Reporting
    # -------------------------------------------------------------------------
    op.execute(_safe_index("idx_saved_reports_created_by", "saved_reports", "created_by"))
    op.execute(_safe_index("idx_export_jobs_status", "export_jobs", "status"))

    # -------------------------------------------------------------------------
    # E12 Alumni & Placement
    # -------------------------------------------------------------------------
    op.execute(_safe_index("idx_alumni_profiles_student_id", "alumni_profiles", "student_id"))
    op.execute(_safe_index("idx_alumni_profiles_status", "alumni_profiles", "status"))
    op.execute(_safe_index("idx_job_applications_org_id", "job_applications", "org_id"))
    op.execute(_safe_index("idx_job_applications_job_id", "job_applications", "job_id"))
    op.execute(_safe_index("idx_job_applications_applicant_id", "job_applications", "applicant_id"))
    op.execute(_safe_index("idx_job_applications_status", "job_applications", "status"))
    op.execute(_safe_index("idx_recruitment_drives_status", "recruitment_drives", "status"))
    op.execute(_safe_index("idx_recruitment_drives_created_by", "recruitment_drives", "created_by"))
    op.execute(_safe_index("idx_drive_registrations_org_id", "drive_registrations", "org_id"))
    op.execute(_safe_index("idx_drive_registrations_drive_id", "drive_registrations", "drive_id"))
    op.execute(_safe_index("idx_drive_registrations_student_id", "drive_registrations", "student_id"))
    op.execute(_safe_index("idx_drive_registrations_status", "drive_registrations", "status"))
    op.execute(_safe_index("idx_alumni_connections_org_id", "alumni_connections", "org_id"))
    op.execute(_safe_index("idx_alumni_connections_requester_id", "alumni_connections", "requester_id"))
    op.execute(_safe_index("idx_alumni_connections_target_id", "alumni_connections", "target_id"))
    op.execute(_safe_index("idx_alumni_connections_status", "alumni_connections", "status"))
    op.execute(_safe_index("idx_mentorship_requests_org_id", "mentorship_requests", "org_id"))
    op.execute(_safe_index("idx_mentorship_requests_mentor_id", "mentorship_requests", "mentor_id"))
    op.execute(_safe_index("idx_mentorship_requests_status", "mentorship_requests", "status"))

    # -------------------------------------------------------------------------
    # E13 Dynamic Process Engine
    # -------------------------------------------------------------------------
    op.execute(_safe_index("idx_process_definitions_created_by", "process_definitions", "created_by"))
    op.execute(_safe_index("idx_process_steps_org_id", "process_steps", "org_id"))
    op.execute(_safe_index("idx_process_instances_process_id", "process_instances", "process_id"))
    op.execute(_safe_index("idx_process_step_logs_org_id", "process_step_logs", "org_id"))
    op.execute(_safe_index("idx_process_step_logs_step_id", "process_step_logs", "step_id"))
    op.execute(_safe_index("idx_process_step_logs_status", "process_step_logs", "status"))
    op.execute(_safe_index("idx_process_form_submissions_org_id", "process_form_submissions", "org_id"))
    op.execute(_safe_index("idx_process_form_submissions_instance_id", "process_form_submissions", "instance_id"))
    op.execute(_safe_index("idx_process_form_submissions_step_id", "process_form_submissions", "step_id"))


def downgrade() -> None:
    indexes = [
        "idx_organisations_status",
        "idx_users_tenant_id", "idx_roles_org_id",
        "idx_workflows_org_id", "idx_workflows_status",
        "idx_approval_requests_org_id", "idx_approval_requests_workflow_id",
        "idx_counsellor_embeddings_org_id", "idx_counsellor_embeddings_counsellor_id",
        "idx_lead_merge_log_org_id", "idx_counsellor_assignments_counsellor_id",
        "idx_intake_quality_scores_org_id", "idx_intake_quality_scores_batch_id",
        "idx_students_applicant_id",
        "idx_domain_events_entity_id", "idx_academic_calendars_org_id",
        "idx_calendar_phases_calendar_id", "idx_org_api_keys_created_by",
        "idx_courses_org_id", "idx_courses_status",
        "idx_course_enrollments_status",
        "idx_faculty_assignments_org_id", "idx_timetable_slots_org_id",
        "idx_attendance_sessions_org_id", "idx_attendance_sessions_course_id",
        "idx_attendance_records_org_id", "idx_attendance_records_status",
        "idx_exam_schedules_course_id", "idx_exam_schedules_status",
        "idx_hall_tickets_org_id", "idx_grades_exam_schedule_id",
        "idx_semester_results_org_id", "idx_semester_results_status",
        "idx_transcripts_org_id", "idx_transcripts_student_id",
        "idx_reeval_requests_org_id", "idx_reeval_requests_student_id",
        "idx_reeval_requests_grade_id", "idx_reeval_requests_status",
        "idx_fee_structures_program_id", "idx_fee_structures_created_by",
        "idx_student_invoices_fee_structure_id", "idx_payments_status",
        "idx_scholarships_org_id", "idx_scholarships_created_by",
        "idx_scholarship_assignments_org_id", "idx_scholarship_assignments_scholarship_id",
        "idx_scholarship_assignments_status",
        "idx_fee_waivers_invoice_id", "idx_fee_waivers_status",
        "idx_leave_types_org_id", "idx_leave_requests_leave_type_id",
        "idx_payroll_components_org_id",
        "idx_staff_salary_structures_org_id", "idx_staff_salary_structures_staff_id",
        "idx_staff_salary_structures_created_by",
        "idx_payslips_status",
        "idx_performance_reviews_org_id", "idx_performance_reviews_reviewer_id",
        "idx_performance_reviews_status", "idx_staff_attendance_status",
        "idx_hostel_blocks_org_id", "idx_hostel_blocks_warden_id",
        "idx_hostel_rooms_org_id", "idx_hostel_rooms_block_id",
        "idx_hostel_allocations_org_id",
        "idx_hostel_complaints_student_id", "idx_hostel_complaints_room_id",
        "idx_hostel_complaints_assigned_to",
        "idx_library_borrowings_org_id", "idx_transport_routes_org_id",
        "idx_transport_assignments_org_id", "idx_transport_assignments_student_id",
        "idx_counselling_sessions_org_id",
        "idx_counselling_referrals_org_id", "idx_counselling_referrals_student_id",
        "idx_counselling_referrals_status",
        "idx_notification_logs_org_id", "idx_in_app_notifications_org_id",
        "idx_announcements_created_by",
        "idx_announcement_reads_announcement_id", "idx_announcement_reads_user_id",
        "idx_bulk_message_jobs_org_id", "idx_bulk_message_jobs_status",
        "idx_bulk_message_jobs_created_by",
        "idx_saved_reports_created_by", "idx_export_jobs_status",
        "idx_alumni_profiles_student_id", "idx_alumni_profiles_status",
        "idx_job_applications_org_id", "idx_job_applications_job_id",
        "idx_job_applications_applicant_id", "idx_job_applications_status",
        "idx_recruitment_drives_status", "idx_recruitment_drives_created_by",
        "idx_drive_registrations_org_id", "idx_drive_registrations_drive_id",
        "idx_drive_registrations_student_id", "idx_drive_registrations_status",
        "idx_alumni_connections_org_id", "idx_alumni_connections_requester_id",
        "idx_alumni_connections_target_id", "idx_alumni_connections_status",
        "idx_mentorship_requests_org_id", "idx_mentorship_requests_mentor_id",
        "idx_mentorship_requests_status",
        "idx_process_definitions_created_by", "idx_process_steps_org_id",
        "idx_process_instances_process_id",
        "idx_process_step_logs_org_id", "idx_process_step_logs_step_id",
        "idx_process_step_logs_status",
        "idx_process_form_submissions_org_id", "idx_process_form_submissions_instance_id",
        "idx_process_form_submissions_step_id",
    ]
    for idx in indexes:
        op.execute(f"DROP INDEX IF EXISTS {idx}")
