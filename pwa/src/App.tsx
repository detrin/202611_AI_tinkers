import { Home, Layers, Settings as SettingsIcon, Shirt } from 'lucide-react'
import { useEffect, useState } from 'react'
import Closet from './pages/Closet'
import SettingsPage from './pages/Settings'
import Style from './pages/Style'
import Today from './pages/Today'
import ShareInbox from './share'
import { getSettings } from './store'

type Tab = 'today' | 'closet' | 'style' | 'settings'

const TABS = [
  { id: 'today', label: 'Today', icon: Home },
  { id: 'closet', label: 'My Closet', icon: Shirt },
  { id: 'style', label: 'My Style', icon: Layers },
  { id: 'settings', label: 'Settings', icon: SettingsIcon },
] as const

export default function App() {
  const [tab, setTab] = useState<Tab>(getSettings().userId ? 'today' : 'settings')
  const [shared, setShared] = useState(() => new URLSearchParams(location.search).has('shared'))
  // Bumped when data changes on another tab's behalf, so lists reload when shown again.
  const [version, setVersion] = useState(0)

  useEffect(() => {
    if (shared) history.replaceState(null, '', '/')
  }, [shared])

  return (
    <div className="app">
      {/* All four pages stay mounted so switching tabs never loses state. */}
      <main hidden={tab !== 'today'}><Today active={tab === 'today'} version={version} /></main>
      <main hidden={tab !== 'closet'}><Closet active={tab === 'closet'} version={version} /></main>
      <main hidden={tab !== 'style'}><Style active={tab === 'style'} version={version} /></main>
      <main hidden={tab !== 'settings'}><SettingsPage onSaved={() => setVersion((v) => v + 1)} /></main>

      {shared && (
        <ShareInbox
          onDone={(goTo) => {
            setShared(false)
            setVersion((v) => v + 1)
            if (goTo) setTab(goTo)
          }}
        />
      )}

      <nav className="tabbar">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button key={id} className={tab === id ? 'on' : ''} onClick={() => setTab(id)} aria-current={tab === id}>
            <Icon size={22} strokeWidth={tab === id ? 2.2 : 1.6} />
            <span>{label}</span>
          </button>
        ))}
      </nav>
    </div>
  )
}
