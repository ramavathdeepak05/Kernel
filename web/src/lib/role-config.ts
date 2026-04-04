/**
 * Role-based configuration — controls what each user sees.
 *
 * Every role gets:
 * - A density (high/medium/low) controlling UI information density
 * - A default view (what they see first on /dashboard)
 * - A default module (where sidebar starts)
 * - A list of visible modules (sidebar navigation items)
 *
 * The backend role string (user.role) maps to ALISRole.
 * Unknown roles fall back to 'registrar' (safe default — RBAC still enforces).
 */

import type { ALISModule, CanvasView } from './canvas-actions'

export type ALISRole =
  | 'registrar'
  | 'faculty'
  | 'student'
  | 'finance'
  | 'hod'
  | 'exam_controller'
  | 'hr_manager'
  | 'dean'
  | 'admin'
  | 'super_admin'

export type Density = 'high' | 'medium' | 'low'

export const ROLE_DENSITY: Record<ALISRole, Density> = {
  registrar:       'high',
  faculty:         'medium',
  student:         'low',
  finance:         'high',
  hod:             'medium',
  exam_controller: 'high',
  hr_manager:      'high',
  dean:            'medium',
  admin:           'high',
  super_admin:     'high',
}

export const ROLE_DEFAULT_VIEW: Record<ALISRole, CanvasView> = {
  registrar:       'approval_queue',
  faculty:         'my_courses',
  student:         'my_academics',
  finance:         'fee_dashboard',
  hod:             'student_risk',
  exam_controller: 'exam_management',
  hr_manager:      'approval_queue',
  dean:            'approval_queue',
  admin:           'approval_queue',
  super_admin:     'approval_queue',
}

export const ROLE_DEFAULT_MODULE: Record<ALISRole, ALISModule> = {
  registrar:       'admissions',
  faculty:         'my_courses',
  student:         'my_courses',
  finance:         'finance',
  hod:             'academics',
  exam_controller: 'examinations',
  hr_manager:      'hr',
  dean:            'academics',
  admin:           'dashboard',
  super_admin:     'dashboard',
}

/** Modules visible to each role in the sidebar */
export const ROLE_MODULES: Record<ALISRole, ALISModule[]> = {
  // STUDENT — self-service only
  student: [
    'dashboard', 'my_courses', 'my_exams', 'my_fees', 'my_library',
    'learning', 'student_services', 'clubs',
  ],

  // FACULTY — teaching + research
  faculty: [
    'dashboard', 'my_courses', 'academics', 'examinations', 'learning',
    'student_services', 'phd', 'training',
  ],

  // HOD — department oversight + faculty's view
  hod: [
    'dashboard', 'academics', 'my_courses', 'examinations', 'hr',
    'student_services', 'phd', 'obe', 'reports', 'learning', 'training',
  ],

  // DEAN — academic oversight + approvals
  dean: [
    'dashboard', 'academics', 'examinations', 'student_services',
    'clubs', 'phd', 'obe', 'regulatory', 'reports',
  ],

  // EXAM CONTROLLER (CoE) — exam lifecycle
  exam_controller: [
    'dashboard', 'examinations', 'academics', 'convocation', 'reports',
  ],

  // FINANCE OFFICER — money
  finance: [
    'dashboard', 'finance', 'budget', 'vendors', 'reports',
  ],

  // HR MANAGER — people
  hr_manager: [
    'dashboard', 'hr', 'recruitment', 'training', 'reports',
  ],

  // REGISTRAR — institution-wide
  registrar: [
    'dashboard', 'admissions', 'academics', 'examinations', 'finance',
    'hr', 'student_services', 'communications', 'alumni', 'phd',
    'convocation', 'workflows', 'regulatory', 'reports',
  ],

  // ADMIN — everything operational
  admin: [
    'dashboard', 'admissions', 'academics', 'examinations', 'finance',
    'budget', 'vendors', 'hr', 'recruitment', 'training',
    'student_services', 'clubs', 'communications', 'alumni', 'phd',
    'convocation', 'obe', 'learning', 'workflows', 'process_engine',
    'consent', 'regulatory', 'reports', 'settings', 'team',
  ],

  // SUPER_ADMIN — everything + platform
  super_admin: [
    'dashboard', 'admissions', 'academics', 'examinations', 'finance',
    'budget', 'vendors', 'hr', 'recruitment', 'training',
    'student_services', 'clubs', 'communications', 'alumni', 'phd',
    'convocation', 'obe', 'learning', 'workflows', 'process_engine',
    'consent', 'regulatory', 'reports', 'settings', 'onboarding', 'team',
  ],
}

export const MODULE_ICONS: Record<ALISModule, string> = {
  dashboard:        '⌂',
  tasks:            '✓',
  students:         '◎',
  admissions:       '→',
  academics:        '▤',
  examinations:     '≡',
  finance:          '₹',
  hr:               '☰',
  student_services: '◈',
  communications:   '✉',
  alumni:           '◉',
  phd:              '⬡',
  convocation:      '⚑',
  obe:              '▣',
  workflows:        '⇌',
  process_engine:   '◧',
  consent:          '⚖',
  regulatory:       '✦',
  reports:          '↗',
  settings:         '⚙',
  onboarding:       '⬡',
  team:             '◎',
  clubs:            '♣',
  training:         '⎔',
  recruitment:      '⊕',
  budget:           '⊞',
  vendors:          '⊡',
  my_fees:          '₹',
  my_courses:       '▤',
  my_exams:         '≡',
  my_library:       '⊟',
  learning:         '⊞',
}

export const MODULE_LABELS: Record<ALISModule, string> = {
  dashboard:        'Dashboard',
  tasks:            'Tasks',
  students:         'Students',
  admissions:       'Admissions',
  academics:        'Academics',
  examinations:     'Examinations',
  finance:          'Finance',
  hr:               'HR & Staff',
  student_services: 'Student Services',
  communications:   'Communications',
  alumni:           'Alumni & Placement',
  phd:              'PhD / Doctoral',
  convocation:      'Convocation',
  obe:              'OBE / CO-PO',
  workflows:        'Workflows',
  process_engine:   'Process Engine',
  consent:          'Consent (DPDP)',
  regulatory:       'Regulatory',
  reports:          'Reports',
  settings:         'Settings',
  onboarding:       'Onboarding',
  team:             'My Team',
  clubs:            'Clubs & Events',
  training:         'Training',
  recruitment:      'Recruitment',
  budget:           'Budget',
  vendors:          'Vendors & Purchase',
  my_fees:          'My Fees',
  my_courses:       'My Courses',
  my_exams:         'My Exams',
  my_library:       'Library',
  learning:         'Learning (LMS)',
}

export const MODULE_ROUTES: Record<ALISModule, string> = {
  dashboard:        '/dashboard',
  tasks:            '/tasks',
  students:         '/students',
  admissions:       '/admissions',
  academics:        '/academics',
  examinations:     '/examinations',
  finance:          '/finance',
  hr:               '/hr',
  student_services: '/students',
  communications:   '/communications',
  alumni:           '/alumni',
  phd:              '/phd',
  convocation:      '/convocation',
  obe:              '/academics/obe',
  workflows:        '/workflows',
  process_engine:   '/process-engine',
  consent:          '/consent',
  regulatory:       '/regulatory',
  reports:          '/reports',
  settings:         '/settings',
  onboarding:       '/admin/onboarding',
  team:             '/admin/team',
  clubs:            '/clubs',
  training:         '/training',
  recruitment:      '/recruitment',
  budget:           '/budget',
  vendors:          '/vendors',
  my_fees:          '/my/fees',
  my_courses:       '/my/courses',
  my_exams:         '/my/exams',
  my_library:       '/my/library',
  learning:         '/academics/learning',
}
