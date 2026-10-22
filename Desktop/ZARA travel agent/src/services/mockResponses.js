const INTENT_RESPONSES = [
  {
    keywords: ['flight', 'fly', 'airline', 'flights', '✈'],
    reply:
      "I found some great flight deals! ✈️\n\n" +
      "Top picks right now:\n" +
      "• New York → Paris — $418 round-trip (Air France, non-stop)\n" +
      "• London → Tokyo — £520 round-trip (JAL)\n" +
      "• Dubai → Bangkok — AED 950 round-trip (Emirates)\n\n" +
      "Want me to filter by travel date, cabin class, or a specific route?",
  },
  {
    keywords: ['hotel', 'hotels', 'stay', 'accommodation', 'lodge', '🏨'],
    reply:
      "Here are my top hotel picks for you! 🏨\n\n" +
      "Featured stays:\n" +
      "• Le Meurice, Paris — ⭐ 4.9 · From $340/night\n" +
      "• Park Hyatt Tokyo — ⭐ 4.8 · From $290/night\n" +
      "• Aman Bangkok — ⭐ 4.9 · From $280/night\n\n" +
      "Shall I narrow results by location, star rating, or price range?",
  },
  {
    keywords: ['budget', 'cheap', 'affordable', 'price', 'cost', 'money', '💰'],
    reply:
      "Smart travel, big savings! 💰\n\n" +
      "Tell me your total budget per person and a rough destination idea. I'll find:\n" +
      "• ✈️ Cheapest available flights on your dates\n" +
      "• 🏨 Value hotels with top reviews\n" +
      "• 🍜 Free attractions and local dining tips\n\n" +
      "What's your budget range?",
  },
  {
    keywords: ['holiday', 'vacation', 'itinerary', 'plan', '📅'],
    reply:
      "Let's plan your perfect holiday! 📅\n\n" +
      "To get started, tell me:\n" +
      "1. Which destination(s) are you dreaming of?\n" +
      "2. How many days do you have?\n" +
      "3. What's your travel style — adventure, culture, beaches, or city breaks?\n\n" +
      "I'll put together a personalised day-by-day itinerary for you!",
  },
  {
    keywords: ['tokyo', 'japan'],
    reply:
      "Tokyo is a fantastic choice! 🇯🇵\n\n" +
      "Cherry blossoms usually peak around March 25th 🌸\n\n" +
      "I found:\n" +
      "• Flights from $680 round-trip\n" +
      "• Hotels near Shinjuku from $85/night\n\n" +
      "Want me to build a full 14-day Tokyo itinerary?",
  },
  {
    keywords: ['paris', 'france'],
    reply:
      "Paris — the City of Light! 🗼\n\n" +
      "Great news:\n" +
      "• Round-trip flights from $418 (Air France)\n" +
      "• Boutique hotels in Le Marais from $120/night\n\n" +
      "Should I include must-see attractions and restaurant recommendations?",
  },
  {
    keywords: ['bangkok', 'thailand'],
    reply:
      "Bangkok is one of Asia's most vibrant cities! 🇹🇭\n\n" +
      "Current deals:\n" +
      "• Flights from $450 round-trip\n" +
      "• Riverside hotels from $65/night\n\n" +
      "Fancy a classic 10-day Thailand itinerary with beach extensions?",
  },
]

const FALLBACKS = [
  "Sounds exciting! Which destination are you thinking of? I can search flights and hotels instantly. 🌍",
  "I'm on it! Could you share your preferred travel dates and destination so I can give you the best options?",
  "Great idea! I can help with flights, hotels, and a full day-by-day itinerary. Where would you like to go?",
  "Love the enthusiasm! What's your approximate budget per person, and when are you hoping to travel?",
  "That's a fun challenge! Tell me a bit more — solo trip, couple, or group? I'll tailor everything to you. ✈️",
]

let fallbackIndex = 0

export function getMockResponse(text) {
  const lower = text.toLowerCase()

  for (const { keywords, reply } of INTENT_RESPONSES) {
    if (keywords.some(kw => lower.includes(kw.toLowerCase()))) {
      return reply
    }
  }

  const response = FALLBACKS[fallbackIndex % FALLBACKS.length]
  fallbackIndex++
  return response
}
