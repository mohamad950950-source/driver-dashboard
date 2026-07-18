import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { API } from '@/lib/api'

let currentUser = null

export default function App() {
  const [user, setUser] = useState(null)
  const [page, setPage] = useState('login')

  useEffect(() => {
    API('/api/auth/me').then(d => {
      if (d.id) {
        currentUser = d
        setUser(d)
        setPage(d.role === 'owner' ? 'owner' : 'dashboard')
      }
    }).catch(() => {})
  }, [])

  if (!user) return <LoginPage onLogin={(u) => { setUser(u); setPage(u.role === 'owner' ? 'owner' : 'dashboard') }} />
  if (page === 'login') return <LoginPage onLogin={(u) => { setUser(u); setPage(u.role === 'owner' ? 'owner' : 'dashboard') }} />
  if (page === 'dashboard') return <DriverDashboard user={user} onLogout={() => { setUser(null); setPage('login') }} />
  if (page === 'owner') return <OwnerDashboard user={user} onLogout={() => { setUser(null); setPage('login') }} />
  return <div className="p-8 text-center">404</div>
}

/* ═══ LOGIN ═══ */
function LoginPage({ onLogin }) {
  const [phone, setPhone] = useState('')
  const [pw, setPw] = useState('')
  const [role, setRole] = useState('driver')
  const [mode, setMode] = useState('login')
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async () => {
    if (!phone || !pw) { setErr('Enter phone and password'); return }
    setLoading(true); setErr('')
    try {
      const d = await API(`/api/auth/${mode}`, {
        method: 'POST',
        body: JSON.stringify({ username: phone, email: `${phone}@d.driver`, password: pw, role }),
      })
      currentUser = d.user
      onLogin(d.user)
    } catch (e) { setErr(String(e)) }
    setLoading(false)
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 w-10 h-10 rounded-lg bg-primary flex items-center justify-center text-primary-foreground font-bold text-lg">D</div>
          <CardTitle className="text-xl">Driver Dashboard</CardTitle>
          <p className="text-sm text-muted-foreground">{mode === 'login' ? 'Sign in to track earnings' : 'Create account to start'}</p>
        </CardHeader>
        <CardContent>
          {err && <div className="mb-3 p-2 text-sm rounded bg-destructive/10 text-destructive">{err}</div>}

          <div className="space-y-3">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Phone</label>
              <input className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring" 
                type="tel" placeholder="0100xxxxxxx" value={phone} onChange={e => setPhone(e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Password</label>
              <input className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                type="password" placeholder="••••••••" value={pw} onChange={e => setPw(e.target.value)} />
            </div>

            <div className="flex gap-2">
              <Button variant={role === 'driver' ? 'default' : 'outline'} size="sm" className="flex-1" onClick={() => setRole('driver')}>Driver</Button>
              <Button variant={role === 'owner' ? 'default' : 'outline'} size="sm" className="flex-1" onClick={() => setRole('owner')}>Owner</Button>
            </div>

            <Button className="w-full" onClick={submit} disabled={loading}>{loading ? '...' : mode === 'login' ? 'Sign In' : 'Create Account'}</Button>

            <p className="text-xs text-center text-muted-foreground">
              {mode === 'login' 
                ? <span className="cursor-pointer text-primary hover:underline" onClick={() => setMode('register')}>No account? Register</span>
                : <span className="cursor-pointer text-primary hover:underline" onClick={() => setMode('login')}>Have account? Sign in</span>
              }
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

/* ═══ DRIVER DASHBOARD (shadcn/ui) ═══ */
function DriverDashboard({ user, onLogout }) {
  const [summary, setSummary] = useState(null)
  const [accounts, setAccounts] = useState({})

  useEffect(() => {
    API('/api/driver-summary?period=today').then(setSummary).catch(() => {})
    API('/api/connected-accounts').then(d => {
      const m = {}; d.accounts.forEach(a => m[a.platform] = a)
      setAccounts(m)
    }).catch(() => {})
  }, [])

  const connectPlatform = (pid) => {
    API(`/api/connect-platform/${pid}`, { method: 'POST' }).catch(() => {})
    window.open(`/api/oauth/${pid}/authorize`, '_blank', 'width=500,height=700')
  }

  const logout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' })
    onLogout()
  }

  const net = summary?.total_net_revenue || 0
  const trips = summary?.revenue?.reduce((a, r) => a + r.trip_count, 0) || 0

  return (
    <div className="min-h-screen bg-background">
      {/* Nav */}
      <header className="border-b sticky top-0 bg-background/95 backdrop-blur z-10">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-md bg-primary flex items-center justify-center text-primary-foreground font-bold text-sm">D</div>
            <span className="font-semibold">Driver Dashboard</span>
          </div>
          <Button variant="outline" size="sm" onClick={logout}>Logout</Button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {/* Today Card */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base text-muted-foreground font-normal">Today's Work</CardTitle>
            <p className="text-3xl font-bold">{net.toLocaleString()} EGP</p>
            <p className="text-sm text-muted-foreground">{trips} trips</p>
          </CardHeader>
        </Card>

        {/* Action Grid */}
        <div className="grid grid-cols-3 gap-3 max-w-lg">
          {['uber', 'didi', 'indrive'].map(pid => {
            const connected = accounts[pid]?.status === 'connected'
            return (
              <Card key={pid} className={`cursor-pointer transition-colors hover:bg-accent ${connected ? 'bg-primary/5 border-primary' : ''}`} onClick={() => !connected && connectPlatform(pid)}>
                <CardContent className="p-4 text-center">
                  <div className={`w-10 h-10 mx-auto rounded-md flex items-center justify-center font-bold text-white mb-1 ${
                    pid === 'uber' ? 'bg-green-500' : pid === 'didi' ? 'bg-orange-500' : 'bg-red-500'
                  }`}>
                    {pid === 'uber' ? 'U' : pid === 'didi' ? 'D' : 'I'}
                  </div>
                  <p className="text-sm font-medium">{pid === 'uber' ? 'Uber' : pid === 'didi' ? 'Didi' : 'InDrive'}</p>
                  <p className="text-xs text-muted-foreground">{connected ? 'Connected' : 'Connect'}</p>
                </CardContent>
              </Card>
            )
          })}
          {['VIP', 'Fuel', 'Service'].map((name, i) => (
            <Card key={name}>
              <CardContent className="p-4 text-center">
                <div className={`w-10 h-10 mx-auto rounded-md flex items-center justify-center font-bold text-white mb-1 ${
                  i === 0 ? 'bg-purple-500' : i === 1 ? 'bg-yellow-500' : 'bg-blue-500'
                }`}>{name[0]}</div>
                <p className="text-sm font-medium">{name}</p>
                <p className="text-xs text-muted-foreground">{i === 0 ? 'Add VIP' : i === 1 ? 'Log Fuel' : 'Log Service'}</p>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Recent Trips */}
        <Card>
          <CardHeader><CardTitle className="text-base">Recent Trips</CardTitle></CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Platform</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow><TableCell colSpan={3} className="text-center text-muted-foreground">No trips yet</TableCell></TableRow>
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </main>
    </div>
  )
}

/* ═══ OWNER DASHBOARD ═══ */
function OwnerDashboard({ user, onLogout }) {
  const logout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' })
    onLogout()
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b sticky top-0 bg-background/95 backdrop-blur z-10">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-md bg-primary flex items-center justify-center text-primary-foreground font-bold text-sm">O</div>
            <span className="font-semibold">Owner Dashboard</span>
          </div>
          <Button variant="outline" size="sm" onClick={logout}>Logout</Button>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-4 py-6">
        <Card>
          <CardHeader><CardTitle>Owner Overview</CardTitle></CardHeader>
          <CardContent>
            <p className="text-muted-foreground">Owner dashboard coming soon with shadcn/ui ✨</p>
          </CardContent>
        </Card>
      </main>
    </div>
  )
}
