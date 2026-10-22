import React, { useState, useEffect } from 'react'
import '../../styles/header.css'

export default function Header() {
  const [scrolled, setScrolled]   = useState(false)
  const [menuOpen, setMenuOpen]   = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header className={`header${scrolled ? ' header--scrolled' : ''}`}>
      <div className="header__inner">
        <a className="header__logo" href="#">
          <span className="header__logo-icon">✈</span>
          <span className="header__logo-text">ZARA</span>
        </a>

        <nav className={`header__nav${menuOpen ? ' header__nav--open' : ''}`}>
          <a href="#" className="header__link">Explore</a>
          <a href="#" className="header__link">My Trips</a>
          <a href="#" className="header__link">Deals</a>
          <a href="#" className="header__link">About</a>
        </nav>

        <div className="header__right">
          <button className="header__cta">Get Started</button>
          <button
            className={`header__burger${menuOpen ? ' header__burger--open' : ''}`}
            onClick={() => setMenuOpen(v => !v)}
            aria-label="Toggle menu"
          >
            <span /><span /><span />
          </button>
        </div>
      </div>
    </header>
  )
}
