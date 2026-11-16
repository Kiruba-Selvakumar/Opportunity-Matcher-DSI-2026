import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { ChevronRight } from 'lucide-react'
import { PageHeader, Section } from '../components/ui'
import { Badge } from '../components/ui'

type Area = 'student' | 'employer' | 'ngo'

/** Open all / Close all for the questions in one section: each press bumps `gen`, and every question follows `open`. */
const AllCtx = createContext<{ gen: number; open: boolean }>({ gen: 0, open: false })

const slug = (q: string) => 'q-' + q.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

/** One question. Closed until clicked, so a section reads as a short list of questions. A link to #q-... opens it. */
const Q = ({ q, children }: { q: string; children: ReactNode }) => {
  const id = slug(q)
  const all = useContext(AllCtx)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => { if (all.gen > 0) setOpen(all.open) }, [all.gen, all.open])
  useEffect(() => {
    if (window.location.hash === `#${id}`) { setOpen(true); ref.current?.scrollIntoView({ block: 'start' }) }
  }, [id])
  return (
    <div ref={ref} id={id} className="max-w-[75ch] scroll-mt-4 border-b border-line last:border-0">
      <h3 className="text-base">
        <button type="button" className="flex w-full items-start gap-2 py-3 text-left hover:text-ink" aria-expanded={open} aria-controls={`${id}-a`} onClick={() => setOpen(!open)}>
          <motion.span className="mt-1 shrink-0" animate={{ rotate: open ? 90 : 0 }} transition={{ type: 'spring', bounce: 0.15, duration: 0.3 }}>
            <ChevronRight className="h-4 w-4 text-ink-soft" aria-hidden />
          </motion.span>
          <span>{q}</span>
        </button>
      </h3>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div id={`${id}-a`} initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }} className="overflow-hidden">
            <div className="space-y-2 pb-3 pl-6 text-sm text-ink-soft">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/** A section of questions with Open all / Close all. */
const Faq = ({ title, children }: { title: string; children: ReactNode }) => {
  const [all, setAll] = useState({ gen: 0, open: false })
  const flip = (open: boolean) => setAll((a) => ({ gen: a.gen + 1, open }))
  return (
    <Section title={title} right={
      <div className="flex gap-3 text-xs text-ink-soft">
        <button type="button" className="underline hover:text-ink" onClick={() => flip(true)}>Open all</button>
        <button type="button" className="underline hover:text-ink" onClick={() => flip(false)}>Close all</button>
      </div>}>
      <AllCtx.Provider value={all}>{children}</AllCtx.Provider>
    </Section>
  )
}

const STATUS_WORDS: [string, string][] = [
  ['Interested', 'You asked about this. The NGO will look at it next.'],
  ['Shared', 'The NGO passed your profile to the employer. You do not need to do anything.'],
  ['Shortlisted', 'The employer put you on their shortlist.'],
  ['Interview', 'The employer wants to interview you. The NGO will contact you with the details.'],
  ['Offered', 'The employer is making you an offer.'],
  ['Hired', 'You got the job.'],
  ['Declined / Not a fit', 'It was closed. Read the note to see why. You can still look at your other matches.'],
  ['Withdrawn', 'You stepped back. You can show interest again later.'],
]

const SCORE = (
  <Q q="How is a match scored?">
    <p>First, hard checks. A match is removed if it needs a move you cannot make, costs more than your budget, needs a language you do not speak, or breaks a family limit you gave us.</p>
    <p>Then a score from 0 to 1. Skills you have count, and rarer skills count for more. A close skill counts partly, for example MySQL for SQL. Small nudges can add or take away a few hundredths: a good branch fit, staying in your home state, and long hours or low safety. If many students have already applied for a listing, its score drops a little so everyone gets a fair chance.</p>
    <p>Three more small parts, each capped: a job whose missing skills are easy to learn (you know a close skill, or a training on your plan teaches it) counts a little more; where you stand among everyone the job fits; and, once there are enough, what happened with similar matches before (staff decisions and employer outcomes).</p>
    <p>Staff can open "How this score was made" on any match to see every part.</p>
  </Q>
)

const ROLES: [string, string, string][] = [
  ['Students, matches, case notes, learning plans', 'Yes', 'Yes'],
  ['Upload resumes, one or many', 'Yes', 'Yes'],
  ['Put an interested student forward', 'Yes', 'Yes'],
  ['Share a student with an employer', 'No', 'Yes, after reading the resume beside the listing'],
  ['Schedule interviews, paste or fetch notes', 'Yes', 'Yes'],
  ['Approve, reject, post, edit or close listings', 'Reads the queue', 'Yes'],
  ['Bulk WhatsApp and WhatsApp messages from employers', 'No', 'Yes'],
  ['Settings, accounts and the audit log', 'No', 'Yes'],
]

const PRIVACY = (
  <Section title="Who can see what">
    <div className="max-w-[75ch] space-y-2 text-sm text-ink-soft">
      <p><strong className="text-ink">Students</strong> see only their own profile, matches and messages.</p>
      <p><strong className="text-ink">Employers</strong> see only their own listings, and only students the NGO has shared with them. They see a short candidate code, branch, town, CGPA and skills. Never a name, a phone number, an email, a budget or a family limit.</p>
      <p><strong className="text-ink">NGO staff</strong> see student records, matches, applications, resumes and messages. Names are hidden on screen unless staff turn on "Show names". Every time a student record or a resume is opened, it is written to a log that nobody can edit.</p>
      <p>Phone numbers and emails are removed from messages, notes and meeting notes before they are saved. A saved resume is kept in a private folder; only the student and NGO staff can open it, and it is never sent to an employer or to an AI service. WhatsApp messages go only to students who agreed.</p>
    </div>
  </Section>
)

export default function Help({ area }: { area: Area }) {
  return (
    <>
      <PageHeader title="Help" sub={{ student: 'How the app works for students, in plain words.', employer: 'How to post a listing and work with the NGO.', ngo: 'How the pieces fit together, and where to look when something seems off.' }[area]} />
      <div className="px-4 pb-16 sm:px-8">
        {area === 'student' && (
          <>
            <Faq title="Getting started">
              <Q q="What do I do first?"><p>Open <strong>Profile</strong> and answer the open questions. Whether you can move, and how much you can spend up front, change which matches you see. The meter shows how complete your profile is.</p></Q>
              <Q q="What does I'm interested do?"><p>It tells the NGO you would like this one. The NGO checks it and, if it fits, shares your profile with the employer. You can see every step on <strong>Applications</strong>, and you can step back at any time.</p></Q>
              <Q q="What is Save?"><p>It keeps a match in a list for later. Nobody is told.</p></Q>
              {SCORE}
              <Q q="Why is an option missing?"><p>The "Options we left out" list says why: usually a move you cannot make, a cost above your budget, or a family limit. If something changed, update your profile and your matches update at once.</p></Q>
              <Q q="What is a Stretch match?"><p>A match where you are missing some skills, but there is training or a mentor that can teach them. The card names it.</p></Q>
              <Q q="What is my learning plan?"><p>On <strong>My matches</strong>: courses and mentors that teach what your best jobs ask for, taken one after another. For each job it shows your score now and with the plan, the day you would be ready, and the job's last day to apply. If a course would make you miss one, it says so and suggests a change that fixes it.</p><p>Want different ones? Choose <strong>Choose my own courses</strong>, tick up to six, and put them in the order you want with the arrows. The plan updates as you go, and nothing is kept until you save. The scores are a preview: your matches change once you add the new skill to your profile.</p></Q>
              <Q q="Should I save my resume?"><p>Yes, if you can. On <strong>Profile</strong>, choose "Save as my resume". The NGO can then read it when they share you with an employer, and you see how a hiring screen reads it, with tips to make it stronger. Employers never get the file.</p></Q>
              <Q q="Can I get updates on WhatsApp?"><p>Yes. Turn it on at the bottom of <strong>Profile</strong>. You can turn it off at any time.</p></Q>
              <Q q="How do I change my mobile number?"><p>On <strong>Profile</strong>, under <strong>Your mobile number</strong>, choose "Change number". The NGO checks the new number before we send anything to it, so a typo never sends your messages to a stranger. Until then we keep using your old number. You get a notification when it is done.</p></Q>
              <Q q="Will I know when the NGO messages me?"><p>Yes. You see it under <strong>Notifications</strong>, and you also get an email and, if you turned WhatsApp on, a WhatsApp. It only says you have a message and links to it; it never repeats what was written. You get one alert until you read it, not one for every message.</p></Q>
            </Faq>
            <Section title="What the statuses mean">
              <div className="max-w-[75ch] space-y-2">{STATUS_WORDS.map(([s, w]) => <p key={s} className="text-sm"><Badge tone="neutral" className="mr-2">{s}</Badge><span className="text-ink-soft">{w}</span></p>)}</div>
            </Section>
            {PRIVACY}
            <Section title="Your data">
              <p className="max-w-[75ch] text-sm text-ink-soft">On <strong>Profile</strong>, choose "Download my data" to get everything we hold about you in one file. To fix something you cannot edit, such as your CGPA, message the NGO.</p>
            </Section>
          </>
        )}
        {area === 'employer' && (
          <>
            <Faq title="Posting a listing">
              <Q q="How do I post one?"><p>Choose <strong>Add listing</strong>, fill in the form, and either save a draft or submit it for review. The preview shows how students will see it.</p></Q>
              <Q q="Why does it need a review?"><p>The NGO checks every listing before students see it. They look at pay, hours, night shifts, safety, and whether it asks students for money. Most reviews are quick. If it is not approved you will see why, and you can fix it and send it again.</p></Q>
              <Q q="Can I change a live listing?"><p>Yes. A change sends it back to review, and it is hidden from students until it is approved again.</p></Q>
              <Q q="What are openings?"><p>How many people you want to hire. When that many students are marked hired, the listing closes by itself.</p></Q>
              <Q q="How do I mark a skill as nice to have?"><p>Write "is a plus" after it, for example <em>Python, SQL, Power BI is a plus</em>. It counts for half as much.</p></Q>
              <Q q="Can I set a last day to apply?"><p>Yes, on the form. After that day students cannot show interest, and the listing closes by itself. Reopen it with a new date to take more.</p></Q>
              <Q q="Will I get emails?"><p>Yes, if your account has an email (set it on your Account page): when a listing is approved or needs a change, when a candidate is shared, when an interview is set, and when the NGO sends you a message (one email until you read it).</p></Q>
            </Faq>
            <Faq title="Working with applicants">
              <Q q="Why do I only see some students?"><p>The NGO decides which interested students to share with you. Everyone you see has been looked at and fits the basics.</p></Q>
              <Q q="Why codes and not names?"><p>To protect students until there is a real conversation. Give the NGO the candidate code when you want to talk about someone, and they will arrange contact.</p></Q>
              <Q q="What can I do with an applicant?"><p>Move them forward: shortlist, interview, offer, hired. Or mark them not a good fit, with a short note. You cannot move someone backwards. Ask the NGO if you made a mistake.</p></Q>
              <Q q="How do I set up an interview?"><p>Shortlist the candidate, then choose <strong>Schedule interview</strong>. Pick a time and how (Google Meet, phone or in person). Everyone gets a calendar invite. Tick the notetaker and the meeting is recorded and summarised, so the NGO gets the action points even if they cannot join.</p></Q>
            </Faq>
            {PRIVACY}
          </>
        )}
        {area === 'ngo' && (
          <>
            <Section title="Staff and admins">
              <p className="mb-3 max-w-[75ch] text-sm text-ink-soft">Staff do the case work. The admin is the gate: nothing reaches an employer, and no listing reaches students, without an admin.</p>
              <div className="card max-w-3xl overflow-x-auto">
                <table className="w-full text-sm"><thead><tr><th className="th">&nbsp;</th><th className="th">NGO staff</th><th className="th">NGO admin</th></tr></thead>
                  <tbody>{ROLES.map(([what, staff, admin]) => <tr key={what}><td className="td">{what}</td><td className="td text-ink-soft">{staff}</td><td className="td text-ink-soft">{admin}</td></tr>)}</tbody></table>
              </div>
            </Section>
            <Faq title="Daily work">
              <Q q="Where do I start?"><p><strong>Home</strong> lists what needs you. For staff: new interest to check, interviews this week, unread messages. For admins: students waiting for your approval, listings to review, and WhatsApp messages from employers.</p></Q>
              <Q q="How does a student get to an employer?"><p>The student shows interest. Staff open <strong>Applications</strong>, look at the fit and put the student forward with a note, or decline with a reason the student will understand. An admin opens <strong>Review and share</strong>, reads the resume beside the listing, and shares. The employer is told by email and in the app.</p></Q>
              <Q q="How do I review or add a listing?"><p>Admins: open <strong>Opportunities</strong>, then <strong>Waiting for review</strong>. Red flags (money asked up front, contact details in the text) need a real look. Set the safety score, then approve or reject. <strong>Add opportunity</strong> posts one straight away, for openings the NGO hears about, its own trainings and mentors.</p></Q>
              <Q q="How do interviews work?"><p>From an application with an employer, choose <strong>Interview</strong>. Either the employer or the NGO can take it. With Google connected (Settings), it gets a Meet link and Google sends the invites; otherwise everyone gets a calendar file by email. Tick the notetaker and Fireflies joins and records it. Afterwards, fetch the notes, or paste the transcript, and the action points are pulled out. Copy them to the case notes with a follow-up date.</p></Q>
              <Q q="How do I upload many resumes?"><p><strong>Students</strong>, then <strong>Upload resumes</strong>. Name each file with the student ID (S014_resume.pdf) and it is matched for you. Each resume gets a score with tips, shown on the student's Resume tab.</p></Q>
              <Q q="How do bulk WhatsApp and employer messages work?"><p>Admins: <strong>Messages</strong>, then <strong>Bulk WhatsApp</strong>. Send a new listing to the students it fits best, tell students their matches are ready, or send an update. Only students who agreed get it; record a student's answer on their Resume tab. Employers who write to the NGO's WhatsApp number show up under <strong>WhatsApp from employers</strong>; reply there, and <strong>Make a listing from this</strong> fills the form from what they wrote.</p></Q>
              <Q q="A student asked to change their number. What do I do?"><p>Home shows it, and the student's page has the new number with <strong>Approve</strong> and <strong>Turn down</strong>. Check it with the student first, by a call or in person. Nothing is sent to the new number until you approve, and the log records the decision but never the number.</p></Q>
              <Q q="What are case notes?"><p>Private notes on a student, with an optional follow-up date. Only NGO staff can see them.</p></Q>
            </Faq>
            <Faq title="Matching">
              {SCORE}
              <Q q="What does Missing info mean?"><p>The student has not told us something, such as whether they can relocate. Matches that depend on it carry a "check" warning, and the student sees a prompt on their profile.</p></Q>
              <Q q="Can a student change their own data?"><p>Only their circumstances: relocation, budget, family limits, languages, English level and extra skills. The record shows "edited by the student". CGPA and branch can only change through you.</p></Q>
              <Q q="What is the staff prior?"><p>A tiny, capped nudge that follows what staff have accepted for similar listings. It needs at least 5 decisions and moves a score by at most 0.03. The match card says when it applied.</p></Q>
              <Q q="Which match is better?"><p>On a student's page, open <strong>Which one is better?</strong> above the top 5. It puts the matches side by side (skills covered, how easy the gap is, rank among students, resume score, pay, cost, move) and marks the best value in each row.</p></Q>
              <Q q="What do Placements and Get Skills mean?"><p>The NGO program the student came through. Get Skills students usually need training first, so look at their <strong>Learning plan</strong> tab: courses and mentors one after another, with what each does for their best jobs and whether they would be ready before each last day to apply.</p></Q>
              <Q q="What is the learned part of the score?"><p>Once there are 20 staff decisions and employer outcomes, the score learns which kinds of match tend to work and nudges similar ones by at most 0.06. Settings, Scoring and decisions, shows how many it has and what it learned.</p></Q>
            </Faq>
            <Section title="Shortcuts">
              <p className="max-w-[75ch] text-sm text-ink-soft">Press <kbd className="rounded border border-line bg-sunk px-1.5 py-0.5 font-mono text-xs">/</kbd> on any list to jump to the search box. Press <kbd className="rounded border border-line bg-sunk px-1.5 py-0.5 font-mono text-xs">Esc</kbd> to close a menu or dialog. Table headers sort when you click them.</p>
            </Section>
            {PRIVACY}
          </>
        )}
      </div>
    </>
  )
}
