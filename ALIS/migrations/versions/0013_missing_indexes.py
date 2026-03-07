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


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # E01 Core / Auth
    # -------------------------------------------------------------------------
    op.execute("CREATE INDEX IF NOT EXISTS idx_organisations_status ON organisations(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_org_id ON users(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_roles_org_id ON roles(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_workflows_org_id ON workflows(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_approval_requests_org_id ON approval_requests(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_approval_requests_workflow_id ON approval_requests(workflow_id)")

    # -------------------------------------------------------------------------
    # E04 Admissions
    # -------------------------------------------------------------------------
    op.execute("CREATE INDEX IF NOT EXISTS idx_counsellor_embeddings_org_id ON counsellor_embeddings(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_counsellor_embeddings_counsellor_id ON counsellor_embeddings(counsellor_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_lead_merge_log_org_id ON lead_merge_log(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_counsellor_assignments_counsellor_id ON counsellor_assignments(counsellor_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_intake_quality_scores_org_id ON intake_quality_scores(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_intake_quality_scores_batch_id ON intake_quality_scores(batch_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_students_applicant_id ON students(applicant_id)")

    # -------------------------------------------------------------------------
    # P0 Platform
    # -------------------------------------------------------------------------
    op.execute("CREATE INDEX IF NOT EXISTS idx_domain_events_entity_id ON domain_events(entity_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_academic_calendars_org_id ON academic_calendars(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_calendar_phases_calendar_id ON calendar_phases(calendar_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_org_api_keys_created_by ON org_api_keys(created_by)")

    # -------------------------------------------------------------------------
    # E05 Academics
    # -------------------------------------------------------------------------
    op.execute("CREATE INDEX IF NOT EXISTS idx_courses_org_id ON courses(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_courses_status ON courses(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_course_enrollments_status ON course_enrollments(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_faculty_assignments_org_id ON faculty_assignments(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_timetable_slots_org_id ON timetable_slots(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_attendance_sessions_org_id ON attendance_sessions(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_attendance_sessions_course_id ON attendance_sessions(course_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_attendance_records_org_id ON attendance_records(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_attendance_records_status ON attendance_records(status)")

    # -------------------------------------------------------------------------
    # E06 Examinations
    # -------------------------------------------------------------------------
    op.execute("CREATE INDEX IF NOT EXISTS idx_exam_schedules_course_id ON exam_schedules(course_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_exam_schedules_status ON exam_schedules(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_hall_tickets_org_id ON hall_tickets(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_grades_exam_schedule_id ON grades(exam_schedule_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_semester_results_org_id ON semester_results(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_semester_results_status ON semester_results(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_transcripts_org_id ON transcripts(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_transcripts_student_id ON transcripts(student_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_reeval_requests_org_id ON reeval_requests(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_reeval_requests_student_id ON reeval_requests(student_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_reeval_requests_grade_id ON reeval_requests(grade_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_reeval_requests_status ON reeval_requests(status)")

    # -------------------------------------------------------------------------
    # E07 Finance
    # -------------------------------------------------------------------------
    op.execute("CREATE INDEX IF NOT EXISTS idx_fee_structures_program_id ON fee_structures(program_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_fee_structures_created_by ON fee_structures(created_by)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_student_invoices_fee_structure_id ON student_invoices(fee_structure_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_scholarships_org_id ON scholarships(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_scholarships_created_by ON scholarships(created_by)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_scholarship_assignments_org_id ON scholarship_assignments(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_scholarship_assignments_scholarship_id ON scholarship_assignments(scholarship_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_scholarship_assignments_status ON scholarship_assignments(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_fee_waivers_invoice_id ON fee_waivers(invoice_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_fee_waivers_status ON fee_waivers(status)")

    # -------------------------------------------------------------------------
    # E08 HR & Staff
    # -------------------------------------------------------------------------
    op.execute("CREATE INDEX IF NOT EXISTS idx_leave_types_org_id ON leave_types(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_leave_requests_leave_type_id ON leave_requests(leave_type_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_payroll_components_org_id ON payroll_components(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_staff_salary_structures_org_id ON staff_salary_structures(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_staff_salary_structures_staff_id ON staff_salary_structures(staff_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_staff_salary_structures_created_by ON staff_salary_structures(created_by)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_payslips_status ON payslips(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_performance_reviews_org_id ON performance_reviews(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_performance_reviews_reviewer_id ON performance_reviews(reviewer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_performance_reviews_status ON performance_reviews(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_staff_attendance_status ON staff_attendance(status)")

    # -------------------------------------------------------------------------
    # E09 Student Services
    # -------------------------------------------------------------------------
    op.execute("CREATE INDEX IF NOT EXISTS idx_hostel_blocks_org_id ON hostel_blocks(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_hostel_blocks_warden_id ON hostel_blocks(warden_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_hostel_rooms_org_id ON hostel_rooms(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_hostel_rooms_block_id ON hostel_rooms(block_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_hostel_allocations_org_id ON hostel_allocations(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_hostel_complaints_student_id ON hostel_complaints(student_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_hostel_complaints_room_id ON hostel_complaints(room_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_hostel_complaints_assigned_to ON hostel_complaints(assigned_to)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_library_borrowings_org_id ON library_borrowings(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_transport_routes_org_id ON transport_routes(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_transport_assignments_org_id ON transport_assignments(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_transport_assignments_student_id ON transport_assignments(student_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_counselling_sessions_org_id ON counselling_sessions(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_counselling_referrals_org_id ON counselling_referrals(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_counselling_referrals_student_id ON counselling_referrals(student_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_counselling_referrals_status ON counselling_referrals(status)")

    # -------------------------------------------------------------------------
    # E10 Communication Hub
    # -------------------------------------------------------------------------
    op.execute("CREATE INDEX IF NOT EXISTS idx_notification_logs_org_id ON notification_logs(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_in_app_notifications_org_id ON in_app_notifications(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_announcements_created_by ON announcements(created_by)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_announcement_reads_announcement_id ON announcement_reads(announcement_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_announcement_reads_user_id ON announcement_reads(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_bulk_message_jobs_org_id ON bulk_message_jobs(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_bulk_message_jobs_status ON bulk_message_jobs(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_bulk_message_jobs_created_by ON bulk_message_jobs(created_by)")

    # -------------------------------------------------------------------------
    # E11 Reporting
    # -------------------------------------------------------------------------
    op.execute("CREATE INDEX IF NOT EXISTS idx_saved_reports_created_by ON saved_reports(created_by)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_export_jobs_status ON export_jobs(status)")

    # -------------------------------------------------------------------------
    # E12 Alumni & Placement
    # -------------------------------------------------------------------------
    op.execute("CREATE INDEX IF NOT EXISTS idx_alumni_profiles_student_id ON alumni_profiles(student_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_alumni_profiles_status ON alumni_profiles(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_job_applications_org_id ON job_applications(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_job_applications_job_id ON job_applications(job_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_job_applications_applicant_id ON job_applications(applicant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_job_applications_status ON job_applications(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_recruitment_drives_status ON recruitment_drives(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_recruitment_drives_created_by ON recruitment_drives(created_by)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_drive_registrations_org_id ON drive_registrations(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_drive_registrations_drive_id ON drive_registrations(drive_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_drive_registrations_student_id ON drive_registrations(student_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_drive_registrations_status ON drive_registrations(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_alumni_connections_org_id ON alumni_connections(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_alumni_connections_requester_id ON alumni_connections(requester_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_alumni_connections_target_id ON alumni_connections(target_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_alumni_connections_status ON alumni_connections(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mentorship_requests_org_id ON mentorship_requests(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mentorship_requests_mentor_id ON mentorship_requests(mentor_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mentorship_requests_status ON mentorship_requests(status)")

    # -------------------------------------------------------------------------
    # E13 Dynamic Process Engine
    # -------------------------------------------------------------------------
    op.execute("CREATE INDEX IF NOT EXISTS idx_process_definitions_created_by ON process_definitions(created_by)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_process_steps_org_id ON process_steps(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_process_instances_process_id ON process_instances(process_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_process_step_logs_org_id ON process_step_logs(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_process_step_logs_step_id ON process_step_logs(step_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_process_step_logs_status ON process_step_logs(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_process_form_submissions_org_id ON process_form_submissions(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_process_form_submissions_instance_id ON process_form_submissions(instance_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_process_form_submissions_step_id ON process_form_submissions(step_id)")


def downgrade() -> None:
    indexes = [
        "idx_organisations_status",
        "idx_users_org_id", "idx_roles_org_id",
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
