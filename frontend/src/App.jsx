import { useState, useEffect, useMemo } from 'react'
import './App.css'

const API = '/api/scratchoff'
const PRICES = [1, 2, 5, 10, 20, 30, 50]

const getTier = (pct) => {
  if (pct == null) return { label: '—', cls: 'tier-none', icon: '' }
  if (pct >= 100) return { label: 'JACKPOT', cls: 'tier-jackpot', icon: '💰' }
  if (pct >= 75) return { label: 'HOT', cls: 'tier-hot', icon: '🔥' }
  if (pct >= 65) return { label: 'SOLID', cls: 'tier-solid', icon: '💎' }
  if (pct >= 55) return { label: 'MEH', cls: 'tier-meh', icon: '😐' }
  return { label: 'COLD', cls: 'tier-cold', icon: '🧊' }
}

function ReturnMeter({ pct }) {
  if (pct == null) return <span className="no-data">—</span>
  const width = Math.min(pct, 100)
  const cls = pct >= 100 ? 'meter-jackpot' : pct >= 75 ? 'meter-hot' : pct >= 65 ? 'meter-solid' : pct >= 55 ? 'meter-meh' : 'meter-cold'
  return (
    <div className="return-meter">
      <div className={`meter-fill ${cls}`} style={{ width: `${width}%` }} />
      <span className="meter-label">{pct}%</span>
    </div>
  )
}

function HeroCard({ game, rank, onClick }) {
  const tier = getTier(game.return_pct)
  const medals = ['🥇', '🥈', '🥉']
  return (
    <div className={`hero-card ${tier.cls}`} onClick={() => onClick(game.game_number)}>
      <div className="hero-rank">{medals[rank]}</div>
      <div className="hero-name">{game.name}</div>
      <div className="hero-price">${game.price} ticket</div>
      <div className="hero-ev">
        <span className="hero-ev-value">${game.ev_value?.toFixed(2)}</span>
        <span className="hero-ev-label">expected back</span>
      </div>
      <ReturnMeter pct={game.return_pct} />
      <div className={`hero-tier ${tier.cls}`}>{tier.icon} {tier.label}</div>
    </div>
  )
}

function GameDetail({ gameNumber, onBack }) {
  const [game, setGame] = useState(null)
  useEffect(() => {
    fetch(`${API}/games/${gameNumber}`).then(r => r.json()).then(setGame)
  }, [gameNumber])

  if (!game) return <div className="loading">✨ Loading the goods...</div>

  const tier = getTier(game.return_pct)

  return (
    <div className="detail">
      <button className="back-btn" onClick={onBack}>← All Games</button>
      <div className="detail-header">
        <h2>{game.name} <span className="game-num">#{game.game_number}</span></h2>
        <div className={`detail-tier ${tier.cls}`}>{tier.icon} {tier.label}</div>
      </div>
      <div className="detail-stats">
        <div className="stat"><label>💵 Price</label><span>${game.price}</span></div>
        <div className="stat"><label>🏆 Top Prize</label><span>{game.top_prize}</span></div>
        <div className="stat"><label>🎲 Odds</label><span>{game.overall_odds ? `1 in ${game.overall_odds}` : '—'}</span></div>
        <div className="stat glow"><label>📊 Expected Value</label>
          <span className={game.return_pct >= 75 ? 'positive-ev' : ''}>{game.ev_value != null ? `$${game.ev_value.toFixed(2)}` : '—'}</span>
        </div>
        <div className="stat glow"><label>📈 Return</label>
          <span className={game.return_pct >= 75 ? 'positive-ev' : ''}>{game.return_pct != null ? <ReturnMeter pct={game.return_pct} /> : '—'}</span>
        </div>
      </div>

      {game.prize_tiers?.length > 0 && (
        <>
          <h3>🎯 Prize Breakdown</h3>
          <table>
            <thead>
              <tr>
                <th>Prize</th>
                <th>Total</th>
                <th>Remaining</th>
                <th>% Left</th>
              </tr>
            </thead>
            <tbody>
              {game.prize_tiers.map((t, i) => {
                const pct = t.total_prizes > 0 ? (100 * t.remaining_prizes / t.total_prizes) : 0
                return (
                  <tr key={i} className={t.remaining_prizes === 0 ? 'depleted' : ''}>
                    <td className="prize-val">${t.prize_value.toLocaleString()}</td>
                    <td>{t.total_prizes.toLocaleString()}</td>
                    <td className={t.remaining_prizes === 0 ? 'zero' : ''}>{t.remaining_prizes.toLocaleString()}</td>
                    <td><div className="pct-bar"><div className="pct-fill" style={{ width: `${pct}%` }} /><span>{pct.toFixed(0)}%</span></div></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}

function App() {
  const [games, setGames] = useState([])
  const [priceFilter, setPriceFilter] = useState(null)
  const [sort, setSort] = useState({ col: 'return_pct', dir: 'desc' })
  const [loading, setLoading] = useState(true)
  const [selectedGame, setSelectedGame] = useState(null)

  useEffect(() => {
    fetch(`${API}/games`)
      .then(r => r.json())
      .then(data => { setGames(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => {
    let list = priceFilter ? games.filter(g => g.price === priceFilter) : games
    return list.slice().sort((a, b) => {
      let av = a[sort.col], bv = b[sort.col]
      if (av == null) return 1
      if (bv == null) return -1
      if (typeof av === 'string') return sort.dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
      return sort.dir === 'asc' ? av - bv : bv - av
    })
  }, [games, priceFilter, sort])

  const topPicks = useMemo(() =>
    games.filter(g => g.return_pct != null).sort((a, b) => b.return_pct - a.return_pct).slice(0, 3)
  , [games])

  const toggleSort = (col) => {
    setSort(prev => ({ col, dir: prev.col === col && prev.dir === 'asc' ? 'desc' : 'asc' }))
  }

  const arrow = (col) => sort.col === col ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''

  if (selectedGame) return <div className="app"><GameDetail gameNumber={selectedGame} onBack={() => setSelectedGame(null)} /></div>
  if (loading) return <div className="loading">✨ Crunching the numbers...</div>

  return (
    <div className="app">
      <header className="hero">
        <h1>🎰 BuckeyeBets</h1>
        <p className="subtitle">The math behind the scratch. Updated daily at 6 AM.</p>
      </header>

      {topPicks.length > 0 && (
        <section className="top-picks">
          <h2 className="section-title">🏆 Today's Best Bets</h2>
          <div className="hero-cards">
            {topPicks.map((g, i) => <HeroCard key={g.id} game={g} rank={i} onClick={setSelectedGame} />)}
          </div>
        </section>
      )}

      <section className="all-games">
        <h2 className="section-title">📋 All Games</h2>
        <div className="filters">
          <button className={!priceFilter ? 'active' : ''} onClick={() => setPriceFilter(null)}>All</button>
          {PRICES.map(p => (
            <button key={p} className={priceFilter === p ? 'active' : ''} onClick={() => setPriceFilter(p)}>${p}</button>
          ))}
        </div>
        <div className="count">{filtered.length} games · sorted by best return</div>
        <table>
          <thead>
            <tr>
              <th onClick={() => toggleSort('name')}>Game{arrow('name')}</th>
              <th onClick={() => toggleSort('price')}>Price{arrow('price')}</th>
              <th onClick={() => toggleSort('top_prize')}>Top Prize{arrow('top_prize')}</th>
              <th onClick={() => toggleSort('ev_value')}>EV{arrow('ev_value')}</th>
              <th onClick={() => toggleSort('return_pct')}>Return{arrow('return_pct')}</th>
              <th>Rating</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(g => {
              const tier = getTier(g.return_pct)
              return (
                <tr key={g.id} className={`clickable ${g.prizes_remaining === 0 ? 'depleted' : ''}`} onClick={() => setSelectedGame(g.game_number)}>
                  <td className="game-name-cell">{g.name}</td>
                  <td>${g.price}</td>
                  <td>{g.top_prize}</td>
                  <td>{g.ev_value != null ? `$${g.ev_value.toFixed(2)}` : '—'}</td>
                  <td><ReturnMeter pct={g.return_pct} /></td>
                  <td><span className={`tier-badge ${tier.cls}`}>{tier.icon} {tier.label}</span></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>
    </div>
  )
}

export default App
