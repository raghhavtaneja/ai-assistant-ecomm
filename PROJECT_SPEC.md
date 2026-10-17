# AI Sales Assistant for D2C Websites: Project Spec

> Working name: `TBD` (placeholder). Replace once chosen.

## 1. One-line pitch

**"Get an AI assistant for your website in 30 seconds."**

A site owner gives us their website URL (and optionally PDFs and a persona). We generate a chat widget they paste into their site with one `<script>` tag. The widget sees what the shopper is currently viewing, answers questions, recommends products, and nudges toward purchase.

## 2. Goals and non-goals

### Goals
- Setup in under 30 seconds: paste URL, optionally upload PDFs, pick a persona, copy the snippet.
- Extremely lightweight: small codebase, few dependencies, tiny widget bundle, cheap to run.
- Real-time streaming responses.
- Page-aware: the assistant knows which product or page the shopper is on.
- Honest, grounded answers: never invent prices, stock, discounts, or policies.
- Learning-first: the codebase should be simple enough to understand end to end.

### Non-goals (for v1)
- No billing or subscriptions, no team accounts, no complex roles.
- No analytics dashboard beyond a basic conversation log.
- No native Shopify app, WhatsApp, or voice. Consider these later.
- No heavy frameworks or microservices.

## 3. Principles

1. **Lightweight over featureful.** If a feature adds a dependency or a page, question it.
2. **One script tag.** The embed must work by pasting a single snippet.
3. **Fast.** Widget under ~25 KB gzipped, loads async, never blocks the host page.
4. **Grounded.** Answers come from the owner's content. When unsure, say so and offer a human handoff.
5. **Minimal UI.** Clean, monochrome, lots of whitespace.

## 4. User flows

### 4.1 Landing page (`/`)
- Single screen, minimalistic and clean.
- Headline: **"Get an AI assistant for your website in 30 seconds."**
- A URL input field and one primary button.
- A subtle **arrow in the bottom-right corner** that scrolls or navigates to the next section or the setup step.
- Optional below the fold: three-step explainer ("Paste your link, add your docs, copy one line"), a short demo, and a FAQ. Keep it small.
- No heavy animations, no stock photos. System font stack or one web font at most.

### 4.2 Setup flow (`/setup`), target under 30 seconds
1. **Website URL** (required). We crawl it in the background.
2. **PDFs** (optional): drag and drop for catalogs, policies, size guides, FAQs.
3. **Persona** (optional): a short text box with a few one-click presets (Friendly stylist, Expert advisor, Playful friend). Plus fields for assistant name, brand tone, and any rules ("never offer discounts").
4. **Generate**: show progress (crawling, reading, ready). The user can preview the chat immediately while indexing finishes.
5. **Copy snippet**: show the `<script>` tag and a live test chat.

### 4.3 Shopper experience (the widget)
- A small floating button in the corner that opens a compact chat panel.
- Streams replies in real time.
- Aware of the current page (see section 6).
- Shows product cards (image, title, price, link) when recommending.
- Opening message adapts to the page, e.g. on a product page: "Questions about this one? I can help with sizing, ingredients, or alternatives."
- Always offers a way to reach a human (link or email set by the owner).

## 5. Architecture (keep it small)

```
[Landing + Setup UI] ---> [API server] ---> [DB + vector store]
                              |  ^
                              v  |
                         [LLM + embeddings]
                              ^
[Embed script on customer site] -- SSE/WebSocket --> [API server]
```

### Suggested stack (change if you have a strong reason)
- **Server:** Python with FastAPI, or Node with Hono. Pick one, not both.
- **Database:** SQLite for v1 (Postgres with pgvector later). Use a lightweight vector option such as `sqlite-vec`, or plain cosine similarity in-process, since catalogs are small.
- **LLM:** Claude via the Anthropic API for chat. Use a small, fast model by default.
- **Embeddings:** any hosted embeddings API.
- **Crawler:** simple fetch plus HTML-to-text extraction. Prefer `sitemap.xml` and structured data (JSON-LD `Product` schema, Open Graph tags), which D2C stores usually expose. Respect `robots.txt`. Cap pages crawled (e.g. 200).
- **PDF parsing:** a lightweight text extractor (e.g. `pypdf`).
- **Frontend (landing + setup):** static HTML, plain CSS, minimal vanilla JS. No frontend framework for v1.
- **Widget:** a single vanilla JS file, no dependencies, rendered inside **Shadow DOM** so it never clashes with the host site's CSS.
- **Streaming:** Server-Sent Events (simplest). Use WebSocket only if needed.

## 6. Page awareness ("sees what the customer is viewing")

The widget collects lightweight context on the host page and sends it with each message:

- `url`, `title`, and `pathname`.
- Product data if present: JSON-LD `Product` schema, Open Graph tags (`og:title`, `og:price:amount`, `og:image`), or Shopify's `window.meta` / product JSON.
- Visible product name, price, and variant selected, if easily read from the DOM.
- Cart contents, if accessible (Shopify `/cart.js`).
- Recently viewed pages in this session (stored in `sessionStorage`).

The server uses this to prioritize retrieval ("answer about the product they're on first"), and to tailor suggestions.

**Privacy:** no personal data collection, no cross-site tracking, no storing page contents beyond what's needed. Mention this in the snippet's docs.

## 7. Knowledge and retrieval

1. **Ingest:** crawl the site, extract product pages (name, description, price, image, URL, availability) into a structured `products` table, and chunk other pages and PDFs into passages.
2. **Embed** products and passages.
3. **Retrieve** on each user message: combine semantic search with the current page's product, then pass the top results to the LLM.
4. **Respond** with the persona prompt, retrieved context, and page context.
5. **Refresh:** re-crawl on demand (button) and automatically on a schedule (e.g. daily), keeping prices and stock fresh.

### LLM tools (function calling)
- `search_products(query, filters)`: returns product cards.
- `get_product(url_or_id)`: full details.
- `search_knowledge(query)`: policies, FAQs, PDF content.
- `handoff_to_human()`: returns the owner's contact details.

Prices, stock, and links shown to the shopper must come from tool results, never from the model's memory.

## 8. Guardrails (this is where quality comes from)

- Never state a price, discount, offer, or stock status that is not in retrieved data.
- Never invent policies (returns, shipping, warranty). If not found, say so and offer handoff.
- Respect owner rules from the persona config ("don't discuss competitors", "no medical claims").
- Keep replies short (2 to 4 sentences by default), conversational, and ending with a helpful next step or question.
- Don't be pushy. Recommend, then let the shopper decide.
- Rate limit per IP and per site to control cost and abuse. Add basic prompt-injection resistance: treat page and PDF content as data, never as instructions.

## 9. Evals (build early)

Create a small test harness, since reliability is the differentiator:

- A set of ~30 to 50 test questions per sample store (product questions, comparison, policy, out-of-scope, prompt-injection attempts).
- Automated checks: does every price and URL in the answer match the catalog? Did it refuse when information was missing? Did it stay on persona?
- Run on every change to prompts or retrieval. Track pass rate over time.

## 10. Data model (v1, minimal)

- `sites`: id, owner_email, url, public_key, persona_json, created_at, last_crawled_at
- `products`: id, site_id, url, title, description, price, currency, image_url, availability, embedding
- `chunks`: id, site_id, source (url or pdf name), text, embedding
- `conversations`: id, site_id, session_id, started_at
- `messages`: id, conversation_id, role, content, created_at

Auth for v1: magic link by email, or even just a secret edit-link per site. Keep it simple.

## 11. API sketch

- `POST /api/sites`: create a site from `{url, persona}`, starts the crawl.
- `POST /api/sites/{id}/documents`: upload PDFs.
- `GET /api/sites/{id}/status`: crawl and index progress.
- `POST /api/chat`: `{site_key, session_id, message, page_context}`, streams the reply via SSE.
- `GET /widget.js?key=SITE_KEY`: serves the embed script with config.

### Embed snippet shown to the user
```html
<script src="https://YOUR_DOMAIN/widget.js" data-key="SITE_KEY" async></script>
```

## 12. Milestones

**M1: Core engine (weekend 1).** CLI or script: take a store URL, crawl and extract products, embed, and answer questions in the terminal with grounded answers.

**M2: API and widget (weekend 2).** FastAPI/Hono `POST /api/chat` with streaming, plus a bare-bones widget that works on a test HTML page with page awareness.

**M3: Setup flow and landing page (weekend 3).** URL, PDFs, persona, generate, copy snippet. Polished minimal landing page.

**M4: Evals and hardening (weekend 4).** Eval harness, rate limiting, guardrails, re-crawl, basic conversation log for the owner.

**M5: Pilot.** Install on 2 to 3 real D2C sites and measure add-to-cart and conversion lift.

## 13. Acceptance criteria for v1

- A new user can go from landing page to a working widget on a test site in under 30 seconds of their own effort (indexing may finish in the background).
- Widget loads asynchronously, is under ~25 KB gzipped, and does not break host site styles.
- First streamed token appears in under ~2 seconds on a typical request.
- Answers about price, stock, and links match the catalog in at least 95% of eval cases.
- When information is missing, the assistant says so and offers a human handoff.

## 14. Design notes

- Palette: off-white or black background, one accent color, generous spacing.
- Typography: system fonts or a single clean sans-serif.
- Landing page has one clear action. The bottom-right arrow is the only decorative element.
- Widget panel is compact (about 360 px wide on desktop, full width on mobile) with rounded corners and subtle shadow, and respects the host site's accent color if provided.

## 15. Open questions (decide as you build)

- Final product name and domain.
- Shopify-only first, or support any site via crawling from day one? (Recommendation: crawl-based works anywhere, with Shopify extras layered on.)
- Pricing model (flat monthly vs base plus revenue share), to be decided after the pilots.
- How to measure revenue attribution honestly (UTM or cart-token tagging on chat-originated clicks).

## 16. Instructions for Claude Code

- Start with M1 and get it working end to end before building any UI.
- Keep dependencies minimal and justify each new one.
- Prefer simple, readable code over abstractions. This project is also for learning, so add short comments explaining non-obvious decisions.
- Write the eval harness alongside the retrieval code, not after.
- Ask before adding any framework, queue, or external service not listed above.
