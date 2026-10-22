import React from 'react'
import Header from '../components/Layout/Header.jsx'
import ChatWindow from '../components/Chat/ChatWindow.jsx'
import TravelShortcuts from '../components/Travel/TravelShortcuts.jsx'
import '../styles/hero.css'

export default function HomePage() {
  return (
    <div className="page">
      <Header />

      {/* ── Hero ─────────────────────────────────── */}
      <section className="hero">
        <div className="hero__orbs">
          <div className="hero__orb hero__orb--1" />
          <div className="hero__orb hero__orb--2" />
          <div className="hero__orb hero__orb--3" />
        </div>

        {/* Floating destination cards — desktop only */}
        <div className="hero__float hero__float--1">
          <span className="hero__float-icon">✈️</span>
          <div>
            <div className="hero__float-title">NYC → TYO</div>
            <div className="hero__float-sub">From $680 round-trip</div>
          </div>
        </div>
        <div className="hero__float hero__float--2">
          <span className="hero__float-icon">🏨</span>
          <div>
            <div className="hero__float-title">Shinjuku Hotel</div>
            <div className="hero__float-sub">⭐ 4.9 · From $85/night</div>
          </div>
        </div>
        <div className="hero__float hero__float--3">
          <span className="hero__float-check">✓</span>
          Itinerary confirmed!
        </div>

        {/* Main text */}
        <div className="hero__content">
          <div className="hero__eyebrow">AI Travel Assistant</div>
          <h1 className="hero__title">
            Where would you<br />
            <span className="hero__title-gradient">like to go?</span>
          </h1>
          <p className="hero__subtitle">
            Tell Zara your dream destination — I'll find the best flights,
            hotels, and craft a personalized itinerary, all in one conversation.
          </p>
          <div className="hero__stats">
            <div className="hero__stat">
              <span className="hero__stat-number">150+</span>
              <span className="hero__stat-label">Countries</span>
            </div>
            <div className="hero__stat-sep" />
            <div className="hero__stat">
              <span className="hero__stat-number">2M+</span>
              <span className="hero__stat-label">Trips Planned</span>
            </div>
            <div className="hero__stat-sep" />
            <div className="hero__stat">
              <span className="hero__stat-number">4.9★</span>
              <span className="hero__stat-label">User Rating</span>
            </div>
          </div>
        </div>

        <a className="hero__scroll" href="#main">
          <span>Start planning</span>
          <div className="hero__scroll-icon" />
        </a>
      </section>

      {/* ── Main content ──────────────────────────── */}
      <main className="main" id="main">
        <div className="main__grid">
          <div className="main__chat">
            <ChatWindow />
          </div>
          <div className="main__sidebar">
            <TravelShortcuts />
          </div>
        </div>
      </main>
    </div>
  )
}
