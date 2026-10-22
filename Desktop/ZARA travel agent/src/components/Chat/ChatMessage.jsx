import React from 'react'

export default function ChatMessage({ message }) {
  const isUser = message.role === 'user'

  return (
    <div className={`message message--${isUser ? 'user' : 'ai'}`}>
      <div className="message__avatar">
        {isUser ? '👤' : '✈'}
      </div>
      <div className="message__body">
        <div className="message__bubble">{message.text}</div>
        <span className="message__time">{message.time}</span>
      </div>
    </div>
  )
}
