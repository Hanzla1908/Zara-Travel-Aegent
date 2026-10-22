import React from 'react'

const ACTIONS = [
  { id: 'flights', emoji: '✈️', label: 'Find Flights' },
  { id: 'hotels',  emoji: '🏨', label: 'Explore Hotels' },
  { id: 'holiday', emoji: '📅', label: 'Plan a Holiday' },
  { id: 'budget',  emoji: '💰', label: 'Find Trips Within My Budget' },
]

export default function QuickActions({ onSelect, disabled }) {
  return (
    <div className="quick-actions">
      <p className="quick-actions__label">Quick actions</p>
      <div className="quick-actions__grid">
        {ACTIONS.map(({ id, emoji, label }) => (
          <button
            key={id}
            className="quick-actions__btn"
            onClick={() => !disabled && onSelect(label)}
            disabled={disabled}
            title={label}
          >
            <span className="quick-actions__emoji">{emoji}</span>
            <span>{label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
