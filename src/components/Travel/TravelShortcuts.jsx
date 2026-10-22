import React from 'react'
import ShortcutCard from './ShortcutCard.jsx'
import '../../styles/shortcuts.css'

const SHORTCUTS = [
  { id: 1, emoji: '✈️', name: 'Book Flights',    desc: 'Best routes & fares',       color: '#ede9fe' },
  { id: 2, emoji: '🏨', name: 'Find Hotels',     desc: 'Verified stays worldwide',  color: '#fef3c7' },
  { id: 3, emoji: '🗺️', name: 'Itinerary',       desc: 'Day-by-day planning',       color: '#dcfce7' },
  { id: 4, emoji: '🌍', name: 'Destinations',    desc: 'Discover new places',       color: '#e0f2fe' },
  { id: 5, emoji: '💰', name: 'Travel Deals',    desc: 'Exclusive discounts',       color: '#fce7f3' },
  { id: 6, emoji: '📋', name: 'My Trips',        desc: 'Manage your bookings',      color: '#f1f5f9' },
]

const DESTINATIONS = [
  { flag: '🇯🇵', name: 'Tokyo',    country: 'Japan',    price: 'From $680' },
  { flag: '🇫🇷', name: 'Paris',    country: 'France',   price: 'From $520' },
  { flag: '🇹🇭', name: 'Bangkok',  country: 'Thailand', price: 'From $450' },
  { flag: '🇮🇹', name: 'Rome',     country: 'Italy',    price: 'From $495' },
]

export default function TravelShortcuts() {
  return (
    <aside className="shortcuts">
      <div className="shortcuts__header">
        <h2 className="shortcuts__title">Quick Actions</h2>
        <p className="shortcuts__subtitle">What can I help you with?</p>
      </div>

      <div className="shortcuts__grid">
        {SHORTCUTS.map(s => (
          <ShortcutCard key={s.id} shortcut={s} />
        ))}
      </div>

      <div className="destinations">
        <div className="destinations__header">
          <span className="destinations__title">🔥 Trending Destinations</span>
          <a className="destinations__all" href="#">View all</a>
        </div>
        <div className="destination-list">
          {DESTINATIONS.map(d => (
            <div className="destination-item" key={d.name}>
              <span className="destination-item__flag">{d.flag}</span>
              <div className="destination-item__info">
                <div className="destination-item__name">{d.name}</div>
                <div className="destination-item__country">{d.country}</div>
              </div>
              <span className="destination-item__price">{d.price}</span>
            </div>
          ))}
        </div>
      </div>
    </aside>
  )
}
