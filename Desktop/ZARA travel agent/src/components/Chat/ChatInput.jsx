import React, { useState, useRef, useEffect } from 'react'

export default function ChatInput({ onSend, disabled }) {
  const [value, setValue] = useState('')
  const textareaRef       = useRef(null)

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [value])

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
    textareaRef.current?.focus()
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="chat-input">
      <div className="chat-input__row">
        <button className="chat-input__extra-btn" aria-label="Attach file">📎</button>
        <textarea
          ref={textareaRef}
          className="chat-input__field"
          placeholder="Ask Zara anything about travel..."
          value={value}
          rows={1}
          disabled={disabled}
          onChange={e => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <div className="chat-input__extras">
          <button className="chat-input__extra-btn" aria-label="Voice input">🎙</button>
          <button
            className="chat-input__send"
            onClick={handleSend}
            disabled={!value.trim() || disabled}
            aria-label="Send message"
          >
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path
                d="M14 8H2M14 8L9 3M14 8L9 13"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        </div>
      </div>
      <p className="chat-input__hint">Enter to send · Shift+Enter for new line</p>
    </div>
  )
}
