import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, MessageCircle } from 'lucide-react'
import { get, post, put } from '../../lib/api'
import type { AuthUser, ListingForm } from '../../lib/types'
import { Banner, ErrorState, PageHeader, Section, Spinner } from '../../components/ui'
import { EMPTY_LISTING, ListingFields, listingBody, previewSkills } from '../../components/ListingFields'
import { useToast } from '../../components/Toast'
import { ListingPreview } from '../employer/ListingFormPage'

interface Suggestion extends ListingForm { lead_id: number; found: { skills: string[]; city: string | null; pay: string | null; openings: boolean } }

/** An NGO admin adds or edits a listing. It goes live at once: the admin is the reviewer. A WhatsApp lead can pre-fill it. */
export default function ListingEditor() {
  const { oid } = useParams()
  const [params] = useSearchParams()
  const leadId = params.get('lead')
  const nav = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()
  const [f, setF] = useState<ListingForm>(EMPTY_LISTING)
  const [owner, setOwner] = useState('')
  const [safety, setSafety] = useState(4)
  const [tell, setTell] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const set = <K extends keyof ListingForm>(k: K, v: ListingForm[K]) => setF((c) => ({ ...c, [k]: v }))

  const existing = useQuery({ queryKey: ['ngo-listing-form', oid], queryFn: () => get<{ form: ListingForm; safety_score: number; status: string }>(`/api/listings/${oid}/form`), enabled: !!oid })
  const lead = useQuery({ queryKey: ['lead-suggest', leadId], queryFn: () => get<Suggestion>(`/api/leads/${leadId}/suggest`), enabled: !!leadId && !oid })
  const users = useQuery({ queryKey: ['admin-users'], queryFn: () => get<AuthUser[]>('/api/admin/users') })
  useEffect(() => { if (existing.data) { setF({ ...EMPTY_LISTING, ...existing.data.form }); setSafety(existing.data.safety_score) } }, [existing.data])
  useEffect(() => {
    if (!lead.data) return
    const form: Partial<Suggestion> = { ...lead.data }
    delete form.lead_id; delete form.found
    setF({ ...EMPTY_LISTING, ...form })
  }, [lead.data])

  const save = useMutation({
    mutationFn: () => {
      const body = { ...listingBody(f), safety_score: safety, owner_username: owner || null, lead_id: leadId ? Number(leadId) : null, tell_students: !oid && tell }
      return oid ? put<{ opp_id: string; told?: number }>(`/api/listings/${oid}`, body) : post<{ opp_id: string; told?: number }>('/api/listings', body)
    },
    onSuccess: (r) => {
      ['opportunities', 'reviews', 'dashboard', 'leads'].forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
      toast(oid ? 'Saved. It stays live.' : `Posted. It is live and matched straight away.${r.told ? ` ${r.told} student${r.told === 1 ? '' : 's'} told on WhatsApp.` : ''}`)
      nav(`/ngo/opportunities/${r.opp_id}`)
    },
    onError: (e) => setError((e as Error).message),
  })
  const skills = useMemo(() => previewSkills(f.required_skills_text), [f.required_skills_text])
  const employers = (users.data ?? []).filter((u) => u.role === 'employer' && u.is_active)
  const submit = (e: FormEvent) => { e.preventDefault(); setError(null); save.mutate() }

  if (oid && existing.isLoading) return <div className="p-8"><Spinner /></div>
  if (oid && existing.error) return <div className="p-8"><ErrorState error={existing.error} /></div>
  return (
    <>
      <PageHeader title={oid ? 'Edit opportunity' : 'Add an opportunity'} sub="As an admin you are the reviewer, so it goes live when you save. Use this for openings the NGO hears about directly, its own trainings, and mentors."
        actions={<Link to={oid ? `/ngo/opportunities/${oid}` : '/ngo/opportunities'} className="btn"><ArrowLeft className="h-4 w-4" aria-hidden />Back</Link>} />
      <div className="grid gap-8 px-4 py-6 sm:px-8 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <form onSubmit={submit} className="space-y-5" noValidate>
          {lead.data && (
            <Banner tone="sky" lead="Filled in from a WhatsApp message." icon={MessageCircle}>
              We found {lead.data.found.skills.length ? lead.data.found.skills.join(', ') : 'no skills'}{lead.data.found.city ? `, ${lead.data.found.city}` : ''}{lead.data.found.pay ? `, pay ${lead.data.found.pay}` : ''}. Check every field before you post.
            </Banner>)}
          <ListingFields f={f} set={set} allowMentor />
          <div className="card grid gap-4 p-5 sm:grid-cols-2">
            <div><label className="label" htmlFor="n-safety">Safety score</label>
              <select id="n-safety" className="input" value={safety} onChange={(e) => setSafety(Number(e.target.value))}>{[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{n} of 5{n === 5 ? ' (safest)' : n === 1 ? ' (least safe)' : ''}</option>)}</select></div>
            {!oid && <div><label className="label" htmlFor="n-owner">Employer account (optional)</label>
              <select id="n-owner" className="input" value={owner} onChange={(e) => setOwner(e.target.value)}>
                <option value="">The NGO manages it</option>{employers.map((u) => <option key={u.id} value={u.username}>{u.display_name} ({u.username})</option>)}</select>
              <p className="mt-1 text-xs text-ink-faint">Pick one and that employer sees the listing and its applicants too.</p></div>}
          </div>
          {!oid && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={tell} onChange={(e) => setTell(e.target.checked)} />When it goes live, tell the students it fits best on WhatsApp (only those who agreed)</label>}
          {error && <p className="rounded-md border border-fail-line bg-fail-soft px-3 py-2 text-sm text-fail" role="alert">{error}</p>}
          <button type="submit" className="btn btn-primary" disabled={save.isPending}>{save.isPending ? 'Saving' : oid ? 'Save changes' : 'Post it now'}</button>
        </form>
        <aside aria-label="Preview"><Section title="How students will see it"><ListingPreview f={f} skills={skills} /></Section></aside>
      </div>
    </>
  )
}
