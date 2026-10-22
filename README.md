# Zara — AI Travel Booking Agent

An AI-powered travel assistant built with React, Vite, and JavaScript.

## Tech Stack

- **Frontend:** React 18, JavaScript (JSX), CSS
- **Build tool:** Vite 5
- **AI:** Anthropic Claude API

## Getting Started

```bash
# Install dependencies
npm install

# Copy environment variables
cp .env.example .env
# Fill in your API keys in .env

# Start dev server
npm run dev
```

## Project Structure

```
src/
├── components/
│   ├── Chat/       # Conversational UI (input, message list, bubbles)
│   ├── Travel/     # Travel-specific cards (flights, hotels, itinerary)
│   ├── Layout/     # Page-level layout (header, sidebar, footer)
│   └── UI/         # Generic reusable primitives (button, modal, spinner)
├── pages/          # Top-level route pages
├── services/       # API clients and external integrations
├── data/           # Static data, mock fixtures, constants
├── hooks/          # Custom React hooks
├── utils/          # Pure helper functions
├── styles/         # Global CSS and design tokens
└── assets/         # Images, icons, fonts bundled by Vite
public/
├── images/         # Static images served as-is
└── icons/          # Favicons and PWA icons
```

## Environment Variables

See [`.env.example`](.env.example) for required keys.
