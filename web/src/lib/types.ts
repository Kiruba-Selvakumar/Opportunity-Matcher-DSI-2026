export type CheckStatus = 'pass' | 'fail' | 'unknown'
export interface Check { status: CheckStatus; note: string }

export interface StudentRef {
  id: string
  branch: string
  town: string
  label: string
  cgpa: number | null
  grad_year: number
  can_relocate: boolean | null
  budget: number | null
  family_limits: string[]
  missing_fields: string[]
  skills: string[]
  n_matches: number
  best_match: string | null
  candidate_code: string
  edited: string[]
  college: string
  program: Program
  has_resume: boolean
  resume_score: number | null
  whatsapp: boolean
}

export type Program = 'placements' | 'get_skills'
export const PROGRAM_WORD: Record<Program, string> = { placements: 'Placements', get_skills: 'Get Skills' }

export interface OpportunityRow {
  opp_id: string
  type: 'job' | 'training' | 'mentor'
  title: string
  org_name: string
  job_family: string
  city: string
  mode: string
  pay_min: number | null
  pay_max: number | null
  upfront_cost: number
  hours_per_week: number
  night_shift: boolean
  safety_score: number
  languages_required: string[]
  skills: string[]
  eligible_count: number
  load?: number
  managed?: boolean
  openings?: number
  apply_by?: string | null
  starts_on?: string | null
  duration_weeks?: number | null
  batch_every_weeks?: number
  closing_soon?: boolean
}

export interface Candidate {
  student_id: string
  branch: string
  town: string
  cgpa: number | null
  final_score: number
  coverage: number
  overlap: string[]
  missing: string[]
  checks: Record<string, Check>
  concerns: string[]
  needs_move: boolean
  college: string
  program: Program
  standing: Standing | null
  ats: number | null
}

export interface OpportunityDetail extends OpportunityRow {
  total_students: number
  removed_by: Record<string, number>
  candidates: Candidate[]
}

export interface Profile {
  student_id: string
  branch: string
  college_town: string
  grad_year: number
  cgpa: number | null
  backlogs: number | null
  projects: number
  english_level: 'basic' | 'intermediate' | 'fluent' | null
  languages: string[]
  can_relocate: boolean | null
  budget: number | null
  family_limits: string[]
  missing_fields: string[]
  skills: string[]
  unmatched: string[]
  skills_raw: string[]
  parse_method: 'rule' | 'llm'
  edited_fields?: string[]
  edited_at?: string | null
  college?: string
  program?: Program
  resume?: ResumeSummary | null
  consent?: Consent
}

export interface Match {
  rank: number
  opp_id: string
  title: string
  org_name: string
  type: 'job' | 'training' | 'mentor'
  city: string
  mode: string
  final_score: number
  overlap: string[]
  missing: string[]
  checks: Record<'location' | 'budget' | 'language' | 'family', Check>
  warnings: string[]
  reason: string
  reason_method: 'template' | 'llm'
  headline: string
  upfront_cost: number
  hours_per_week: number
  night_shift: boolean
  safety_score: number
  pay_min: number | null
  pay_max: number | null
  breakdown?: Breakdown
  fit: string
  gap_closers: GapCloser[]
  related: Related[]
  crowded: boolean
  prior_note: string | null
  application?: { id: number; status: string; words: string } | null
  saved?: boolean
  apply_by?: string | null
  starts_on?: string | null
  duration_weeks?: number | null
  upskill?: Upskill | null
  standing?: Standing | null
  ml?: number | null
  ats?: AtsResult | null
}

export interface Breakdown {
  skill_sim: number
  coverage: number
  base_score: number
  weight_sim: number
  weight_coverage: number
  penalty_hours: number
  penalty_safety: number
  final_score: number
  related?: Related[]
  adjustments?: Record<string, number>
  crowded?: boolean
  prior_note?: string | null
  upskill?: Upskill | null
  standing?: Standing | null
  ml?: number | null
}

export interface WhyNot {
  opp_id: string
  title: string
  type: string
  city: string
  base_score: number
  overlap: string[]
  fails: { check: string; note: string }[]
}

export interface MatchesResponse { what_if: boolean; matches: Match[]; why_not: WhyNot[] }

export interface WhatIf {
  can_relocate: 'yes' | 'no' | 'unknown'
  budget: number | null
  family_limits: string[]
}

export interface Decision {
  id: number
  created_at: string
  student_id: string
  opp_id: string
  rank: number | null
  final_score: number | null
  decision: 'accept' | 'reject' | 'flag'
  reject_reason: string | null
  note: string | null
  what_if: boolean
  seconds_to_decide: number | null
  decided_by: string | null
}

export interface IntakeInput {
  branch: string
  college_town: string
  grad_year: number
  cgpa: number | null
  english_level: string | null
  languages: string[]
  can_relocate: 'yes' | 'no' | 'unknown'
  budget: number | null
  family_limits: string[]
}

export interface IntakeResult {
  student: Profile
  skills: string[]
  unmatched: string[]
  extracted: { cgpa: number | null; projects: number; english_level: string | null; skills_found: string[] }
  matches?: Match[]
  pages?: number
}

export type RawText = Record<string, string>

export type ChatRole = 'ngo' | 'student' | 'lister'

export interface ChatMessage {
  id: number
  created_at: string
  thread_type: 'student' | 'listing'
  thread_id: string
  sender_role: ChatRole
  body: string
  about_opp_id: string | null
}

export interface Thread {
  thread_type: 'student' | 'listing'
  thread_id: string
  count: number
  unread: number
  last_body: string
  last_role: ChatRole
  last_at: string
}

export type Role = 'ngo_admin' | 'ngo_staff' | 'student' | 'employer'

export interface AuthUser {
  id: number
  username: string
  display_name: string
  role: Role
  student_id: string | null
  is_active: boolean
  must_change_password: boolean
  locked_until: string | null
  last_login_at: string | null
  created_at: string
  listings: string[]
  locked?: boolean
  email?: string | null
}

export interface AuditEvent {
  id: number
  at: string
  user_id: number | null
  username: string | null
  role: string | null
  action: string
  target: string | null
  ip: string | null
  detail: string | null
}

export interface StudentSelf {
  profile: Profile
  matches: Match[]
  why_not: WhyNot[]
  name: string | null
  shown: number
  eligible_total: number
  min_score: number
}

export interface ListingRow {
  opp_id: string
  title: string
  org_name: string
  type: 'job' | 'training' | 'mentor'
  city: string
  mode: string
  eligible_count: number
}

export interface EmployerCandidate {
  candidate_code: string
  branch: string
  town: string
  cgpa: number | null
  final_score: number
  coverage: number
  overlap: string[]
  missing: string[]
}

export interface EmployerListing extends Omit<OpportunityRow, 'eligible_count'> {
  eligible_count: number
  total_students: number
  candidates: EmployerCandidate[]
}

// ---------------- v2 additions ----------------
export interface GapCloser { opp_id: string; title: string; type: string; covers: string[]; cost: number }
export interface Related { have: string; need: string; credit: number }

export interface Notification { id: number; kind: string; text: string; link: string | null; created_at: string; read_at: string | null }

export type ListingStatus = 'draft' | 'pending' | 'active' | 'rejected' | 'closed'

export interface ListingForm {
  title: string
  type: 'job' | 'training' | 'mentor'
  org_name: string
  description: string
  required_skills_text: string
  city: string
  mode: 'onsite' | 'hybrid' | 'remote'
  pay_text: string
  upfront_cost_text: string
  hours_per_week: number
  night_shift: boolean
  languages: ('English' | 'Telugu' | 'Hindi')[]
  openings: number
  apply_by?: string | null
  starts_on?: string | null
  duration_weeks?: number | null
  batch_every_weeks?: number
}

export interface ListingSummary {
  opp_id: string
  title: string
  org_name: string
  type: 'job' | 'training' | 'mentor'
  city: string
  mode: string
  status: ListingStatus
  managed: boolean
  editable: boolean
  openings: number
  eligible_count: number
  applicants: number
  review_note: string | null
  updated_at: string | null
  apply_by?: string | null
  closing_soon?: boolean
}

export interface Applicant {
  id: number
  candidate_code: string
  branch: string
  town: string
  cgpa: number | null
  status: string
  overlap: string[]
  missing: string[]
  student_note: string | null
  employer_note: string | null
  days_in_stage: number
  next: string[]
  interviews: Interview[]
  can_schedule: boolean
}

export interface ListingDetailFull extends EmployerListing {
  status: ListingStatus
  editable: boolean
  managed: boolean
  openings: number
  description: string
  form: ListingForm | null
  review_note: string | null
  closed_reason: string | null
  applicants: Applicant[]
}

export interface ReviewItem {
  opp_id: string
  status: ListingStatus
  form: ListingForm
  safety_score: number
  review_note: string | null
  reviewed_by: string | null
  updated_at: string
  owner: string
  was_approved: boolean
  edited_since_review: boolean
  flags: { level: 'red' | 'amber'; text: string }[]
  mapped_skills: number
}

export interface AppEvent { at: string; by: string; to: string; words: string; note: string | null }

export interface StudentApplication {
  id: number
  opp_id: string
  title: string
  org_name: string
  type: string
  city: string
  status: string
  words: string
  student_note: string | null
  ngo_note: string | null
  employer_note: string | null
  days_in_stage: number
  created_at: string
  can_withdraw: boolean
  reviewing?: boolean
  stopped_at?: string | null
  events: AppEvent[]
  interviews: Interview[]
}

export interface NgoApplication {
  id: number
  student_id: string
  opp_id: string
  title: string
  branch: string
  town: string
  candidate_code: string
  name: string | null
  status: string
  student_note: string | null
  ngo_note: string | null
  employer_note: string | null
  days_in_stage: number
  updated_at: string
  next: string[]
  college: string
  program: Program | ''
  recommended_by: string | null
  recommended_at: string | null
  score: number | null
  fit: string | null
  ats: number | null
  has_resume: boolean
  can_recommend: boolean
  interviews: Interview[]
}

export interface ProfilePayload {
  profile: Profile
  completeness: { percent: number; items: { field: string; label: string; done: boolean; impact: number }[] }
  edited_fields: string[]
  edited_at: string | null
  extra_skills: string[]
}

export interface CaseNote { id: number; student_id: string; author: string; body: string; follow_up_on: string | null; done: number; created_at: string }
export interface TimelineEvent { at: string; kind: 'decision' | 'application' | 'note' | 'message' | 'edit'; text: string }

export interface Dashboard {
  counts: { students: number; active_listings: number; pending_reviews: number; interests_waiting: number; unread_messages: number; hired: number; in_play: number
    put_forward: number; interviews_week: number; closing_soon: number; new_leads: number; with_resume: number; number_changes?: number }
  funnel: Record<string, number>
  attention: {
    number_changes?: string[]
    no_matches: { count: number; ids: string[] }
    missing_info: { count: number; items: { id: string; missing: number }[] }
    stale: { id: number; student_id: string; title: string; status: string; days: number }[]
    busiest: { opp_id: string; title: string; load: number; openings: number }[]
    followups: { id: number; student_id: string; due: string; text: string }[]
    interviews: { id: number; student_id: string; title: string; when: string; mode: string; interviewer: string }[]
    closing: { opp_id: string; title: string; apply_by: string; eligible: number }[]
  }
}

export interface SessionRow { created_at: string; last_seen_at: string; ip: string | null; current: boolean }

// ---------------- v3 additions: resumes, interviews, messaging, learning plans ----------------
export interface Standing { rank: number; of: number; percentile: number }
export interface UpskillStep { skill: string; ease: number; from: string | null; via: { opp_id: string; title: string; type: string; cost: number } | null }
export interface Upskill { reach: number; potential: number; steps: UpskillStep[] }

export interface ResumeSummary {
  uploaded_at: string
  source: 'student' | 'ngo' | 'bulk'
  pages: number
  score: number
  grade: 'Strong' | 'Fair' | 'Weak'
  parts: Record<string, number>
  sections: string[]
  tips: string[]
  skills: string[]
  not_in_profile: string[]
}
export interface AtsResult { score: number; grade: string; keywords_found: string[]; keywords_missing: string[]; coverage: number; quality: number; tips: string[] }
export interface Consent { whatsapp: boolean; recorded_by: string | null; updated_at: string | null; reachable: boolean }

export interface Interview {
  id: number
  starts_at: string
  when: string
  minutes: number
  mode: 'meet' | 'phone' | 'in_person'
  location: string | null
  meet_link: string | null
  status: 'scheduled' | 'done' | 'cancelled' | 'no_show'
  interviewer: 'employer' | 'ngo'
  calendar: 'google' | 'ics' | 'none'
  notetaker: boolean
  summary?: string | null
  action_items?: string[]
  notes_source?: string | null
  interviewer_email?: string | null
  application_id?: number
  opp_id?: string
  student_id?: string
  title?: string
  candidate_code?: string
}
export interface ScheduleResult { interview: Interview; calendar: string; warnings: string[] }

export interface PlanStep {
  opp_id: string; title: string; org_name: string; type: string; mode: string; city: string; cost: number
  starts_on: string | null; ends_on: string | null; weeks: number | null; teaches: string[]
  hours_per_week: number; total_hours: number | null; self_paced: boolean; covered_by_earlier?: boolean; any_time?: boolean; no_batch?: boolean
  unlocks: { opp_id: string; title: string; before: number; after: number }[]
}
/** A course or mentor the student could put in their plan. */
export type PlanOption = PlanStep & { chosen: boolean; suggested: boolean }
export interface LearningPlan {
  targets: { opp_id: string; title: string; before: number; after: number; missing: string[] }[]
  steps: PlanStep[]
  gap: string[]
  still_missing?: string[]
  message: string
  finish_by?: string | null; weeks_total?: number | null; hours_total?: number | null; open_ended?: number
  custom?: boolean; suggested?: string[]; options?: PlanOption[]; dropped?: string[]
  order?: string[]; roles?: PlanRole[]; fixes?: PlanFix[]; late?: number
}
/** One role the plan is for: its score now and with the plan, when the student would be ready, and its deadline. */
export interface PlanRole {
  opp_id: string; title: string; before: number; after: number; missing: string[]
  ready_by: string | null; apply_by: string | null; days_late: number; learns: string[]; org_name?: string; pay_lpa?: number | null
  status: 'in_time' | 'late' | 'no_deadline' | 'not_helped' | 'unknown'
}
/** A change that gets a late role in time: take a pick first, or drop one. order is the whole new order. */
export interface PlanFix { role: string; role_id: string; kind: 'move' | 'drop'; opp_id: string; title: string; order: string[]; ready_by: string | null; apply_by: string; loses?: string[] }

export interface ReviewBundle {
  application: NgoApplication
  listing: OpportunityRow & { description?: string; nice?: string[] }
  student: Profile
  match: (Breakdown & { overlap: string[]; missing: string[]; eligible: boolean; checks: Record<string, Check> }) | null
  ats: AtsResult | null
  events: { at: string; actor_role: string; from_status: string | null; to_status: string; note: string | null }[]
}

export interface LeadThread {
  id: number; phone: string; profile_name: string | null; status: 'new' | 'mapped' | 'dismissed'; mapped_opp_id: string | null
  mapped_by: string | null; note: string | null; unread: number; last_at: string; created_at: string; last_body?: string; count?: number
  messages?: { id: number; direction: 'in' | 'out'; body: string; at: string; sent_by: string | null }[]
}

export interface OutboxItem {
  id: number; created_at: string; channel: 'email' | 'whatsapp'; kind: string; recipient: string; address: string
  subject: string | null; body: string; status: 'queued' | 'sent' | 'delivered' | 'read' | 'failed' | 'dry_run'
  provider_id: string | null; error: string | null; batch_id: string | null; sent_at: string | null
}

export interface IntegrationStatus {
  email: { live: boolean; from: string | null }
  whatsapp: { live: boolean; webhook_ready: boolean; only_to: number; templates: Record<string, string> }
  google: { configured: boolean; connected: boolean; account: string | null; connected_by: string | null; connected_at: string | null }
  fireflies: { live: boolean; bot_email: string | null; webhook_ready: boolean }
  test_mode: { active: boolean }
  app_url: string
}

export interface BroadcastPlan {
  kind: 'opportunity' | 'matches' | 'update'; total: number; reachable: number; not_agreed: number; no_phone: number
  preview: string; sample: { student_id: string; score?: number | null }[]; live: boolean; stand_ins: number | null
}

export interface ScoringInfo {
  v2: Record<string, boolean>
  v3: Record<string, boolean>
  caps: { upskill: number; ml: number; standing: number; standing_min_field: number }
  ml: { labels: number; yes: number; no: number; needed: number; needed_each: number; max_nudge: number; on: boolean; trained: boolean
    weight?: number; learned?: { what: string; effect: 'helps' | 'hurts'; strength: number }[] }
}

/** One live listing in full, as the signed-in student sees it (GET /api/me/browse/{id}). */
export interface StudentListing {
  opp_id: string; title: string; org_name: string; type: 'job' | 'training' | 'mentor'; city: string; mode: string
  score: number; fit: string; eligible: boolean; blockers: string[]; checks: string[]
  pay_min: number | null; pay_max: number | null; upfront_cost: number; hours_per_week: number; night_shift: boolean
  overlap: string[]; missing: string[]; crowded: boolean; description: string; saved: boolean
  application: { id: number; status: string; words?: string } | null
  job_family: string; openings: number; languages_required: string[]; skills: string[]; nice: string[]
  related: Related[]; teaches: string[]; gap_closers: GapCloser[]
  apply_by: string | null; closing_soon: boolean; starts_on: string | null; duration_weeks: number | null
}

/** The student's own mobile number (masked), any change waiting for the NGO, and the last decision. */
export interface MyContact {
  phone: string | null
  pending: { phone: string | null; requested_at: string } | null
  last: { status: 'approved' | 'rejected'; decided_at: string; note: string | null } | null
}
export interface ContactChange { id: number; student_id: string; name: string | null; phone: string; current: string | null; requested_at: string }
