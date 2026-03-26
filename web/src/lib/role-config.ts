/**
 * Role-based density and permission configuration.
 * Reference: ALIS-skills/references/frontend.md §3, §13
 */

import type { ALISModule, CanvasView } from './canvas-actions'

export type ALISRole =
  | 'registrar'
  | 'faculty'
  | 'student'
  | 'finance'
  | 'hod'
  | 'exam_controller'
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
  admin:           'approval_queue',
  super_admin:     'approval_queue',
}

export const ROLE_DEFAULT_MODULE: Record<ALISRole, ALISModule> = {
  registrar:       'admissions',
  faculty:         'academics',
  student:         'academics',
  finance:         'finance',
  hod:             'academics',
  exam_controller: 'examinations',
  admin:           'dashboard',
  super_admin:     'dashboard',
}

/** Modules visible to each role in the sidebar */
export const ROLE_MODULES: Record<ALISRole, ALISModule[]> = {
  registrar:       ['dashboard', 'admissions', 'academics', 'examinations', 'finance', 'hr', 'student_services', 'communications', 'alumni', 'phd', 'convocation', 'workflows', 'regulatory', 'reports'],
  faculty:         ['dashboard', 'academics', 'examinations', 'student_services', 'phd'],
  student:         ['dashboard', 'academics', 'examinations', 'student_services'],
  finance:         ['dashboard', 'finance', 'reports'],
  hod:             ['dashboard', 'academics', 'hr', 'student_services', 'phd', 'obe', 'reports'],
  exam_controller: ['dashboard', 'examinations', 'academics', 'convocation'],
  admin:           ['dashboard', 'admissions', 'academics', 'examinations', 'finance', 'hr', 'student_services', 'communications', 'alumni', 'phd', 'convocation', 'obe', 'workflows', 'process_engine', 'consent', 'regulatory', 'reports', 'settings'],
  super_admin:     ['dashboard', 'admissions', 'academics', 'examinations', 'finance', 'hr', 'student_services', 'communications', 'alumni', 'phd', 'convocation', 'obe', 'workflows', 'process_engine', 'consent', 'regulatory', 'reports', 'settings', 'onboarding'],
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
}
