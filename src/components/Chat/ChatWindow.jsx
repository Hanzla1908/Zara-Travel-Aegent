import React, { useState, useRef, useEffect } from 'react'
import ChatMessage from './ChatMessage.jsx'
import ChatInput from './ChatInput.jsx'
import QuickActions from './QuickActions.jsx'
import { getMockResponse } from '../../services/mockResponses.js'
import '../../styles/chat.css'

function nowTime() {
  return new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })
}

const WELCOME = {
  id: 0,
  role: 'ai',
  text:
    "Hi! I'm Zara ✈️ Your personal AI travel companion.\n\n" +
    "Tell me where you'd like to go and I'll find the best flights, hotels, " +
    "and craft a custom itinerary — or pick a quick action below to get started!",
  time: nowTime(),
}

export default function ChatWindow() {
  const [messages, setMessages] = useState([WELCOME])
  const [typing, setTyping]     = useState(false)
  const bottomRef               = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, typing])

  const handleSend = (text) => {
    setMessages(prev => [...prev, { id: Date.now(), role: 'user', text, time: nowTime() }])
    setTyping(true)

    const delay = 1200 + Math.random() * 600
    setTimeout(() => {
      setTyping(false)
      setMessages(prev => [
        ...prev,
        { id: Date.now() + 1, role: 'ai', text: getMockResponse(text), time: nowTime() },
      ])
    }, delay)
  }

  const handleReset = () => {
    setMessages([{ ...WELCOME, id: Date.now(), time: nowTime() }])
    setTyping(false)
  }

  return (
    <div className="chat-panel">
      {/* ── Header ─────────────────────────────── */}
      <div className="chat-panel__header">
        <div className="chat-panel__avatar">✈</div>
        <div className="chat-panel__info">
          <div className="chat-panel__name">Zara</div>
          <div className="chat-panel__status">● Online · Ready to plan</div>
        </div>
        <div className="chat-panel__actions">
          <button
            className="chat-panel__action-btn"
            title="New conversation"
            onClick={handleReset}
          >
            ✏️
          </button>
          <button className="chat-panel__action-btn" title="Options">⋯</button>
        </div>
      </div>

      {/* ── Messages ───────────────────────────── */}
      <div className="chat-messages">
        {messages.map(msg => (
          <ChatMessage key={msg.id} message={msg} />
        ))}

        {typing && (
          <div className="typing-indicator">
            <div className="typing-indicator__avatar">✈</div>
            <div className="typing-indicator__bubble">
              <div className="typing-dot" />
              <div className="typing-dot" />
              <div className="typing-dot" />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* ── Quick actions ──────────────────────── */}
      <QuickActions onSelect={handleSend} disabled={typing} />

      {/* ── Input ──────────────────────────────── */}
      <ChatInput onSend={handleSend} disabled={typing} />
    </div>
  )
}
