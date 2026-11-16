import { Link } from 'react-router-dom'
import { Compass } from 'lucide-react'
import { Empty, PageHeader } from '../components/ui'

export default function NotFound({ home, label = 'Go to your home page' }: { home: string; label?: string }) {
  return (
    <>
      <PageHeader title="Page not found" sub="That address does not lead anywhere. It may have moved, or the link may be wrong." />
      <Empty icon={Compass} title="Nothing here"><Link to={home} className="btn btn-primary mt-3">{label}</Link></Empty>
    </>
  )
}
