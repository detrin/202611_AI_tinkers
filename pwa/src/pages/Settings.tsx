import { useEffect, useState } from 'react'
import { api } from '../api'
import { errorText } from '../format'
import { getSettings, saveLastOutfit, saveSettings } from '../store'
import type { User } from '../types'
import { Notice } from '../ui'

type Status = 'checking' | 'ok' | 'down'

export default function SettingsPage({ onSaved }: { onSaved: () => void }) {
  const [settings, setSettings] = useState(getSettings)
  const [server, setServer] = useState<Status>('checking')
  const [user, setUser] = useState<User | null>(null)
  const [city, setCity] = useState('')
  const [newName, setNewName] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function check() {
    setServer('checking')
    setError('')
    try {
      await api.health()
      setServer('ok')
    } catch {
      setServer('down')
      setUser(null)
      return
    }
    if (!getSettings().userId) return setUser(null)
    try {
      const u = await api.user()
      setUser(u)
      setCity(u.city || '')
    } catch (e) {
      setUser(null)
      setError(`User not found: ${errorText(e)}`)
    }
  }

  useEffect(() => {
    check()
  }, [])

  function save(next = settings) {
    saveSettings(next)
    setSettings(next)
    saveLastOutfit(null)
    setMessage('Saved.')
    onSaved()
    check()
  }

  async function createUser() {
    setError('')
    try {
      const u = await api.createUser(newName.trim(), city.trim() || 'Prague')
      save({ ...settings, userId: u.id })
      setNewName('')
    } catch (e) {
      setError(errorText(e))
    }
  }

  async function saveCity() {
    setError('')
    try {
      setUser(await api.updateUser({ city: city.trim() }))
      saveLastOutfit(null)
      setMessage('Location saved. The next outfit uses its weather.')
      onSaved()
    } catch (e) {
      setError(errorText(e))
    }
  }

  const dot = (s: Status | boolean) => <i className={`status ${s === 'ok' || s === true ? 'ok' : s === 'checking' ? 'wait' : 'off'}`} />

  return (
    <div className="page">
      <header className="page-head">
        <h1>Settings</h1>
      </header>
      {message && <Notice>{message}</Notice>}
      {error && <Notice kind="error">{error}</Notice>}

      <section className="panel">
        <h3>Connections</h3>
        <div className="pref"><span>{dot(server)} Wardrobe server</span><b>{server === 'ok' ? 'Connected' : server === 'checking' ? 'Checking…' : 'Not reachable'}</b></div>
        <div className="pref"><span>{dot(false)} Google Calendar</span><b>Not connected</b></div>
        <div className="pref"><span>{dot(server)} Weather (Open-Meteo)</span><b>{server === 'ok' ? 'Live, through the server' : 'Needs the server'}</b></div>
        <div className="pref"><span>{dot(server)} Product links (Apify)</span><b>{server === 'ok' ? 'Through the server' : 'Needs the server'}</b></div>
        <p className="hint">Until the calendar is connected, set the occasion by hand with the sliders icon on Today.</p>
      </section>

      <section className="panel stack">
        <h3>Account</h3>
        {user ? (
          <>
            <div className="pref"><span>Signed in as</span><b>{user.name}</b></div>
            <label className="field">
              <span>Location for the weather</span>
              <input value={city} onChange={(e) => setCity(e.target.value)} placeholder="Prague" />
            </label>
            <button className="btn" onClick={saveCity} disabled={!city.trim() || city.trim() === user.city}>
              Save location
            </button>
          </>
        ) : (
          <>
            <p className="muted">No user yet. Paste an existing user id below, or create one.</p>
            <label className="field">
              <span>Your name</span>
              <input value={newName} onChange={(e) => setNewName(e.target.value)} />
            </label>
            <label className="field">
              <span>City</span>
              <input value={city} onChange={(e) => setCity(e.target.value)} placeholder="Prague" />
            </label>
            <button className="btn primary" onClick={createUser} disabled={!newName.trim() || server !== 'ok'}>
              Create user
            </button>
          </>
        )}
      </section>

      <section className="panel stack">
        <h3>Developer</h3>
        <label className="field">
          <span>User id</span>
          <input value={settings.userId} onChange={(e) => setSettings({ ...settings, userId: e.target.value.trim() })} />
        </label>
        <label className="field">
          <span>Server address</span>
          <input value={settings.apiBase} onChange={(e) => setSettings({ ...settings, apiBase: e.target.value.trim() })} />
        </label>
        <button className="btn" onClick={() => save()}>
          Save and reconnect
        </button>
      </section>
    </div>
  )
}
