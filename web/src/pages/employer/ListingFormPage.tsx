import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Check, Clock, MapPin, Wallet } from 'lucide-react'
import { get, post, put } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { TYPE_WORD } from '../../lib/format'
import type { ListingDetailFull, ListingForm, ListingSummary } from '../../lib/types'
import { Badge, Banner, ErrorState, PageHeader, Section } from '../../components/ui'
import { EMPTY_LISTING, ListingFields, listingBody, previewSkills } from '../../components/ListingFields'
import { ApplyBy } from '../../components/Deadline'
import { useConfirm } from '../../components/Confirm'
import { useToast } from '../../components/Toast'
import { Spinner } from '../../components/ui'

export default function ListingFormPage() {
  const { oid } = useParams()
  const editing = !!oid
  const nav = useNavigate()
  const qc = useQueryClient()
  const confirm = useConfirm()
  const toast = useToast()
  const { user } = useAuth()
  const existing = useQuery({ queryKey: ['my-listing', oid], queryFn: () => get<ListingDetailFull>(`/api/me/listings/${oid}`), enabled: editing })
  const mine = useQuery({ queryKey: ['my-listings'], queryFn: () => get<ListingSummary[]>('/api/me/listings') })
  const [f, setF] = useState<ListingForm>(EMPTY_LISTING)
  const [error, setError] = useState<string | null>(null)
  const set = <K extends keyof ListingForm>(k: K, v: ListingForm[K]) => setF((c) => ({ ...c, [k]: v }))

  useEffect(() => { if (existing.data?.form) setF({ ...EMPTY_LISTING, ...existing.data.form }) }, [existing.data])
  useEffect(() => { if (!editing && !f.org_name) set('org_name', mine.data?.[0]?.org_name ?? user?.display_name ?? '') }, [editing, mine.data, user])  // eslint-disable-line react-hooks/exhaustive-deps

  const save = useMutation({
    mutationFn: ({ submit }: { submit: boolean }) => {
      const body = listingBody(f)
      return editing ? put<{ opp_id: string; status: string }>(`/api/me/listings/${oid}?submit=${submit}`, body)
                     : post<{ opp_id: string; status: string }>(`/api/me/listings?submit=${submit}`, body)
    },
    onSuccess: (r, v) => {
      qc.invalidateQueries({ queryKey: ['my-listings'] }); qc.invalidateQueries({ queryKey: ['my-listing'] })
      toast(v.submit ? 'Sent to the NGO for review.' : 'Draft saved.')
      nav(`/employer/${r.opp_id}`)
    },
    onError: (e) => setError((e as Error).message),
  })

  const live = existing.data?.status === 'active'
  const go = async (submit: boolean, e?: FormEvent) => {
    e?.preventDefault(); setError(null)
    if (live && !(await confirm({ title: 'Send this listing back to review?', body: 'It is live now. Saving a change hides it from students until the NGO approves it again.', confirmLabel: 'Save and send for review' }))) return
    save.mutate({ submit: submit || live })
  }
  const skills = useMemo(() => previewSkills(f.required_skills_text), [f.required_skills_text])

  if (editing && existing.isLoading) return <div className="p-8"><Spinner /></div>
  if (editing && existing.error) return <div className="p-8"><ErrorState error={existing.error} /></div>
  if (editing && existing.data && !existing.data.editable) return <div className="p-8"><Banner tone="amber" lead="The NGO manages this listing.">Message the NGO if you want it changed.</Banner></div>

  return (
    <>
      <PageHeader title={editing ? 'Edit listing' : 'Add a listing'} sub="Tell students what the role is and what it needs. The NGO checks it before students see it."
        actions={<Link to={editing ? `/employer/${oid}` : '/employer'} className="btn"><ArrowLeft className="h-4 w-4" aria-hidden />Back</Link>} />
      <div className="grid gap-8 px-4 py-6 sm:px-8 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <form onSubmit={(e) => go(true, e)} className="space-y-5" noValidate>
          {live && <Banner tone="amber" lead="This listing is live.">Saving a change sends it back to review, and it is hidden from students until it is approved again.</Banner>}
          <ListingFields f={f} set={set} />
          {error && <p className="rounded-md border border-fail-line bg-fail-soft px-3 py-2 text-sm text-fail" role="alert">{error}</p>}
          <div className="flex flex-wrap gap-2">
            <button type="submit" className="btn btn-primary" disabled={save.isPending}>{live ? 'Save and send for review' : 'Submit for review'}</button>
            {!live && <button type="button" className="btn" disabled={save.isPending} onClick={() => go(false)}>Save draft</button>}
          </div>
        </form>

        <aside aria-label="Preview">
          <Section title="How students will see it">
            <ListingPreview f={f} skills={skills} />
          </Section>
        </aside>
      </div>
    </>
  )
}

export function ListingPreview({ f, skills }: { f: ListingForm; skills: { name: string; nice: boolean }[] }) {
  return (
    <article className="card p-5">
      <div className="flex items-center gap-2 text-sm text-ink-soft"><Badge tone="neutral">{TYPE_WORD[f.type]}</Badge><span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5" aria-hidden />{f.mode === 'remote' ? 'Remote' : f.city || 'City'}</span></div>
      <h2 className="mt-2 !text-xl">{f.title || 'Your listing title'}</h2>
      <p className="text-sm text-ink-soft">{f.org_name || 'Your company'}</p>
      {f.apply_by && <div className="mt-1"><ApplyBy date={f.apply_by} /></div>}
      {f.description && <p className="mt-3 max-w-[75ch] text-sm">{f.description}</p>}
      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-soft">
        <li className="inline-flex items-center gap-1.5"><Wallet className="h-3.5 w-3.5" aria-hidden />{/^\s*(0|free|nil)?\s*$/i.test(f.upfront_cost_text) ? 'Free to join' : `Costs ${f.upfront_cost_text}`}{f.pay_text ? `, pays ${f.pay_text}` : ''}</li>
        <li className="inline-flex items-center gap-1.5"><Clock className="h-3.5 w-3.5" aria-hidden />{f.hours_per_week} hours a week</li>
      </ul>
      {skills.length > 0 && <div className="mt-3 flex flex-wrap gap-1.5">{skills.map((s) => <Badge key={s.name} tone={s.nice ? 'neutral' : 'accent'}><Check className="h-3 w-3" aria-hidden />{s.name}{s.nice && ' (nice to have)'}</Badge>)}</div>}
    </article>
  )
}
