/**
 * Role Configuration — single source of truth per ALIS_FRONTEND_SPEC.md §4
 *
 * Controls what each role sees: nav items, agent chips, display metadata.
 * This file is consumed by IconNav, AgentRail, and RoleDashboard.
 */

// ── Types ──────────────────────────────────────────────────────

export type FrontendRole =
  | 'SUPER_ADMIN'
  | 'REGISTRAR'
  | 'DEAN'
  | 'HOD'
  | 'FACULTY'
  | 'STUDENT'
  | 'FINANCE_OFFICER'
  | 'COE'
  | 'HR_MANAGER';

export const BACKEND_ROLE_MAP: Record<string, FrontendRole> = {
  SUPER_ADMIN:      'SUPER_ADMIN',
  ADMIN:            'SUPER_ADMIN',
  REGISTRAR:        'REGISTRAR',
  DEAN:             'DEAN',
  HOD:              'HOD',
  FACULTY:          'FACULTY',
  STUDENT:          'STUDENT',
  FINANCE_OFFICER:  'FINANCE_OFFICER',
  COE:              'COE',
  EXAM_CONTROLLER:  'COE',
  HR_MANAGER:       'HR_MANAGER',
};

// ── Nav ──────────────────────────────────────────────────────

export interface NavItem {
  icon: string;
  label: string;
  path: string;
  badge?: number;
}

export interface NavSection {
  section: string;
  items: NavItem[];
}

export const ROLE_NAV: Record<FrontendRole, NavSection[]> = {
  SUPER_ADMIN: [
    { section: 'Platform', items: [
      { icon: 'LayoutDashboard', label: 'Dashboard',           path: '/dashboard' },
      { icon: 'Building2',       label: 'Institution',         path: '/settings' },
      { icon: 'Users',           label: 'Users & Roles',       path: '/admin/team' },
      { icon: 'Sliders',         label: 'Policy Studio',       path: '/admin/policies' },
    ]},
    { section: 'Modules', items: [
      { icon: 'GraduationCap',   label: 'Admissions',          path: '/admissions' },
      { icon: 'BookOpen',        label: 'Academics',           path: '/academics' },
      { icon: 'ClipboardList',   label: 'Examinations',        path: '/examinations' },
      { icon: 'Wallet',          label: 'Finance',             path: '/finance' },
      { icon: 'Users2',          label: 'HR & Payroll',        path: '/hr' },
      { icon: 'Heart',           label: 'Student Services',    path: '/students' },
      { icon: 'BarChart3',       label: 'Regulatory',          path: '/regulatory' },
    ]},
    { section: 'System', items: [
      { icon: 'Activity',        label: 'Audit & Reports',     path: '/reports' },
      { icon: 'Zap',             label: 'Workflows',           path: '/workflows' },
    ]},
  ],

  REGISTRAR: [
    { section: 'Admissions', items: [
      { icon: 'LayoutDashboard', label: 'Dashboard',           path: '/dashboard' },
      { icon: 'Inbox',           label: 'Application Queue',   path: '/admissions' },
      { icon: 'CheckCircle',     label: 'Eligibility',         path: '/admissions' },
      { icon: 'ListOrdered',     label: 'Merit List',          path: '/admissions' },
      { icon: 'UserCheck',       label: 'Enrollment',          path: '/admissions' },
    ]},
    { section: 'Academic', items: [
      { icon: 'Calendar',        label: 'Academic Calendar',   path: '/academics' },
      { icon: 'Clock',           label: 'Timetable',           path: '/academics' },
      { icon: 'BarChart2',       label: 'Results',             path: '/examinations' },
      { icon: 'FileText',        label: 'Document Issuance',   path: '/academics' },
    ]},
    { section: 'Compliance', items: [
      { icon: 'Shield',          label: 'NAAC / NIRF',         path: '/regulatory' },
      { icon: 'FileArchive',     label: 'UGC Returns',         path: '/regulatory' },
      { icon: 'ScrollText',      label: 'Audit Ledger',        path: '/reports' },
    ]},
  ],

  DEAN: [
    { section: 'Oversight', items: [
      { icon: 'LayoutDashboard', label: 'Dashboard',           path: '/dashboard' },
      { icon: 'BarChart3',       label: 'Dept Reports',        path: '/reports' },
      { icon: 'UserPlus',        label: 'Faculty Appts',       path: '/recruitment' },
      { icon: 'BookOpen',        label: 'Curriculum',          path: '/academics' },
      { icon: 'ArrowUpCircle',   label: 'Escalations',         path: '/dashboard' },
    ]},
    { section: 'Student Affairs', items: [
      { icon: 'Award',           label: 'Scholarships',        path: '/students' },
      { icon: 'AlertTriangle',   label: 'Disciplinary',        path: '/students' },
      { icon: 'MessageCircle',   label: 'Grievances',          path: '/students' },
    ]},
    { section: 'Regulatory', items: [
      { icon: 'Shield',          label: 'NAAC Criteria',       path: '/regulatory' },
      { icon: 'Star',            label: 'NBA Program',         path: '/regulatory' },
    ]},
  ],

  HOD: [
    { section: 'Department', items: [
      { icon: 'LayoutDashboard', label: 'Dashboard',           path: '/dashboard' },
      { icon: 'CheckSquare',     label: 'Approval Queue',      path: '/dashboard' },
      { icon: 'UserX',           label: 'Attendance',          path: '/academics' },
      { icon: 'BookOpen',        label: 'Courses',             path: '/academics' },
      { icon: 'Calendar',        label: 'Timetable',           path: '/academics' },
      { icon: 'BarChart2',       label: 'Faculty Workload',    path: '/reports' },
    ]},
    { section: 'Academic', items: [
      { icon: 'Edit3',           label: 'IA Marks',            path: '/examinations' },
      { icon: 'Target',          label: 'OBE / CO-PO',         path: '/academics/obe' },
      { icon: 'Shield',          label: 'NAAC — C2',           path: '/regulatory' },
    ]},
  ],

  FACULTY: [
    { section: 'My Classes', items: [
      { icon: 'LayoutDashboard', label: 'Dashboard',           path: '/dashboard' },
      { icon: 'Calendar',        label: 'Schedule',            path: '/my/courses' },
      { icon: 'UserCheck',       label: 'Attendance',          path: '/my/courses' },
      { icon: 'ClipboardList',   label: 'Assignments',         path: '/my/courses' },
      { icon: 'Edit3',           label: 'IA Marks Entry',      path: '/examinations' },
    ]},
    { section: 'Content', items: [
      { icon: 'FileText',        label: 'Course Materials',    path: '/academics' },
      { icon: 'Monitor',         label: 'LMS',                 path: '/academics/learning' },
      { icon: 'Target',          label: 'CO Progress',         path: '/academics/obe' },
    ]},
    { section: 'Self-Service', items: [
      { icon: 'Umbrella',        label: 'Leave',               path: '/training' },
      { icon: 'Star',            label: 'CAS Appraisal',       path: '/training' },
    ]},
  ],

  STUDENT: [
    { section: 'Academics', items: [
      { icon: 'LayoutDashboard', label: 'Dashboard',           path: '/dashboard' },
      { icon: 'Calendar',        label: 'Timetable',           path: '/my/courses' },
      { icon: 'UserCheck',       label: 'Attendance',          path: '/my/courses' },
      { icon: 'BarChart2',       label: 'Marks & Grades',      path: '/my/exams' },
      { icon: 'ClipboardList',   label: 'Assignments',         path: '/my/courses' },
      { icon: 'FileText',        label: 'Results',             path: '/my/exams' },
    ]},
    { section: 'Services', items: [
      { icon: 'Wallet',          label: 'Fee Account',         path: '/my/fees' },
      { icon: 'BookOpen',        label: 'Library',             path: '/my/library' },
      { icon: 'Home',            label: 'Hostel',              path: '/students' },
      { icon: 'Award',           label: 'Scholarships',        path: '/students' },
      { icon: 'MessageCircle',   label: 'Grievances',          path: '/students' },
    ]},
    { section: 'Career', items: [
      { icon: 'Briefcase',       label: 'Placement',           path: '/alumni' },
      { icon: 'Users',           label: 'Clubs & Events',      path: '/clubs' },
    ]},
  ],

  FINANCE_OFFICER: [
    { section: 'Revenue', items: [
      { icon: 'LayoutDashboard', label: 'Dashboard',           path: '/dashboard' },
      { icon: 'CreditCard',      label: 'Fee Collection',      path: '/finance' },
      { icon: 'Award',           label: 'Scholarships',        path: '/finance' },
      { icon: 'RotateCcw',       label: 'Refunds',             path: '/finance' },
    ]},
    { section: 'Expenditure', items: [
      { icon: 'ShoppingCart',    label: 'Vendors',             path: '/vendors' },
      { icon: 'Users2',          label: 'Payroll',             path: '/hr' },
      { icon: 'PieChart',        label: 'Budget',              path: '/budget' },
    ]},
    { section: 'Compliance', items: [
      { icon: 'Receipt',         label: 'GST / e-Invoice',     path: '/finance' },
      { icon: 'Percent',         label: 'TDS Returns',         path: '/finance' },
      { icon: 'FileBarChart',    label: 'Reports',             path: '/reports' },
    ]},
  ],

  COE: [
    { section: 'Exam Operations', items: [
      { icon: 'LayoutDashboard', label: 'Dashboard',           path: '/dashboard' },
      { icon: 'Ticket',          label: 'Hall Tickets',        path: '/examinations' },
      { icon: 'Calendar',        label: 'Exam Schedule',       path: '/examinations' },
      { icon: 'Lock',            label: 'Question Papers',     path: '/examinations' },
      { icon: 'Map',             label: 'Seating',             path: '/examinations' },
    ]},
    { section: 'Results', items: [
      { icon: 'Edit3',           label: 'Marks Entry',         path: '/examinations' },
      { icon: 'BarChart2',       label: 'Result Computation',  path: '/examinations' },
      { icon: 'RefreshCw',       label: 'Revaluation',         path: '/examinations' },
    ]},
    { section: 'Records', items: [
      { icon: 'FileText',        label: 'Transcripts',         path: '/examinations' },
      { icon: 'AlertTriangle',   label: 'Malpractice',         path: '/examinations' },
    ]},
  ],

  HR_MANAGER: [
    { section: 'Recruitment', items: [
      { icon: 'LayoutDashboard', label: 'Dashboard',           path: '/dashboard' },
      { icon: 'Briefcase',       label: 'Job Requisitions',    path: '/recruitment' },
      { icon: 'Users',           label: 'Applicant Tracking',  path: '/recruitment' },
      { icon: 'FileText',        label: 'Appointment Letters', path: '/recruitment' },
    ]},
    { section: 'Payroll', items: [
      { icon: 'Wallet',          label: 'Payroll Cycle',       path: '/hr' },
      { icon: 'Umbrella',        label: 'Leave Management',    path: '/hr' },
      { icon: 'Star',            label: 'CAS Appraisals',      path: '/hr' },
    ]},
    { section: 'Records', items: [
      { icon: 'Users2',          label: 'Employee Directory',  path: '/hr' },
      { icon: 'GraduationCap',   label: 'Training & FDP',      path: '/training' },
      { icon: 'Shield',          label: 'Statutory Compliance', path: '/hr' },
      { icon: 'LogOut',          label: 'Exit Management',     path: '/hr' },
    ]},
  ],
};

// ── Agent Rail Chips ────────────────────────────────────────

export interface AgentChip {
  label: string;
  prompt: string;
}

export const ROLE_AGENT_CHIPS: Record<FrontendRole, AgentChip[]> = {
  SUPER_ADMIN: [
    { label: 'System health',      prompt: 'Show me current system health across all containers' },
    { label: 'Domain events',      prompt: 'Show the last 20 domain events across all modules' },
    { label: 'Compliance check',   prompt: 'What compliance items are due or overdue right now?' },
    { label: 'Export audit log',   prompt: 'Prepare an audit log export for the last 7 days' },
  ],
  REGISTRAR: [
    { label: 'Pending eligibility',prompt: 'Show all applications awaiting eligibility decision' },
    { label: 'Merit list status',  prompt: 'What is the current status of the merit list?' },
    { label: 'Enrollment queue',   prompt: 'Show students with pending enrollment clearance' },
    { label: 'NAAC export',        prompt: 'Generate the NAAC AQAR data export' },
  ],
  DEAN: [
    { label: 'My escalations',     prompt: 'List all items currently escalated to me' },
    { label: 'Scholarship queue',  prompt: 'Show pending scholarship disbursement approvals' },
    { label: 'Faculty vacancies',  prompt: 'What are the current faculty vacancies by department?' },
    { label: 'Dept summary',       prompt: 'Give me a performance summary across all departments' },
  ],
  HOD: [
    { label: 'Shortfall list',     prompt: 'List all students below 75% attendance in my department' },
    { label: 'IA marks status',    prompt: 'Which faculty have not submitted IA marks yet?' },
    { label: 'CO attainment',      prompt: 'Show CO attainment status for current semester courses' },
    { label: 'Faculty workload',   prompt: 'Show faculty workload distribution for my department' },
  ],
  FACULTY: [
    { label: 'Mark attendance',    prompt: 'Help me mark attendance for my next class' },
    { label: 'My grievances',      prompt: 'Show all open grievances assigned to me' },
    { label: 'IA marks entry',     prompt: 'Open IA marks entry for my courses' },
    { label: 'My schedule',        prompt: 'What is my teaching schedule for this week?' },
  ],
  STUDENT: [
    { label: 'My attendance',      prompt: 'Show my attendance percentage for all courses' },
    { label: 'My fees',            prompt: 'What is my current fee status and any dues?' },
    { label: 'Library status',     prompt: 'Show my issued books and any fines' },
    { label: 'Raise grievance',    prompt: 'Help me raise a grievance' },
  ],
  FINANCE_OFFICER: [
    { label: 'Fee summary',        prompt: 'Show fee collection summary for the current month' },
    { label: 'Overdue accounts',   prompt: 'List the top 20 overdue fee accounts by amount' },
    { label: 'Bank recon status',  prompt: 'What is the status of today\'s bank reconciliation?' },
    { label: 'Payroll status',     prompt: 'What is the status of the current payroll cycle?' },
  ],
  COE: [
    { label: 'Hall ticket status', prompt: 'Show hall ticket generation status for current semester' },
    { label: 'Q-paper vault',      prompt: 'Which question papers are missing from the vault?' },
    { label: 'Exam schedule',      prompt: 'Show the current exam schedule' },
    { label: 'Revaluation queue',  prompt: 'List all pending revaluation requests' },
  ],
  HR_MANAGER: [
    { label: 'Payroll exceptions', prompt: 'Show all payroll exceptions for this cycle' },
    { label: 'Leave approvals',    prompt: 'List all pending leave approval requests' },
    { label: 'Open requisitions',  prompt: 'Show all open job requisitions and their status' },
    { label: 'CAS due',            prompt: 'Which faculty are due for CAS appraisal?' },
  ],
};

// ── Role Display Names ──────────────────────────────────────

export const ROLE_DISPLAY: Record<FrontendRole, { name: string; initials: string; description: string }> = {
  SUPER_ADMIN:     { name: 'Super Admin',        initials: 'SA', description: 'Full system access' },
  REGISTRAR:       { name: 'Registrar',           initials: 'RG', description: 'Admissions · Academic · Compliance' },
  DEAN:            { name: 'Dean',                initials: 'DN', description: 'Academic & Student Affairs' },
  HOD:             { name: 'Head of Department',  initials: 'HD', description: 'Department Operations' },
  FACULTY:         { name: 'Faculty',             initials: 'FC', description: 'Teaching & Assessment' },
  STUDENT:         { name: 'Student',             initials: 'ST', description: 'Self-Service Portal' },
  FINANCE_OFFICER: { name: 'Finance Officer',     initials: 'FO', description: 'FM-1 through FM-7 · MFA Active' },
  COE:             { name: 'Controller of Exams', initials: 'CE', description: 'Examination Operations' },
  HR_MANAGER:      { name: 'HR Manager',          initials: 'HR', description: 'HR & Payroll · MFA Active' },
};
