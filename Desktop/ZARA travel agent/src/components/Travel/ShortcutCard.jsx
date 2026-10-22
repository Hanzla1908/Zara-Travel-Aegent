import React from 'react'

export default function ShortcutCard({ shortcut }) {
  return (
    <button className="shortcut-card">
      <div
        className="shortcut-card__icon"
        style={{ background: shortcut.color }}
      >
        {shortcut.emoji}
      </div>
      <div className="shortcut-card__name">{shortcut.name}</div>
      <div className="shortcut-card__desc">{shortcut.desc}</div>
    </button>
  )
}
