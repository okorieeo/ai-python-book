# Chapter 9 — UI/UX Design for Developers: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## User Research for Builders › Personas: a face for the target user

A **persona** is a short, concrete description of a typical user, built from your research (not invented stereotypes). It stops the team designing for "everyone", which means no one. Keep it to half a page:

| **Part** | **Example (AI Chat SaaS)** |
|---|---|
| **Name and role** | Amaka, runs a small online shop and handles marketing herself |
| **Context** | Works mostly on her phone, sometimes on a laptop; mobile data is not unlimited, so slow or heavy pages frustrate her |
| **Goals** | Write product descriptions, customer replies and social media posts quickly, in a friendly tone |
| **Frustrations** | Blank-page anxiety; AI tools that feel complicated; surprise charges; losing a good draft |
| **Money** | Pays in naira with a local card or bank transfer; prefers a clear monthly price over complicated usage meters |
| **Quote from research** | "I just want to type what I need and get something I can send." |


## User Flows and Information Architecture › Navigation patterns

| **Pattern** | **Best for** | **Notes** |
|---|---|---|
| **Bottom tab bar** (mobile) | 3 to 5 top-level destinations used often | Thumb-friendly; the standard on iOS and common on Android |
| **Drawer / side menu** | Lists of items such as conversations; secondary destinations | Hidden by default on mobile; always visible sidebar on desktop |
| **Stack navigation** | Drilling into details and going back | The back gesture or button must always work |
| **Top navigation** (web) | Marketing pages and simple apps | Collapses into a menu icon on small screens |
| **Modal / bottom sheet** | Short, focused tasks (rename, confirm delete) | Do not nest modals; always provide a clear way to close |

Rule: a user should always know **where they are, where they can go, and how to get back**.


## Wireframing › Figma in one page

**Figma** (figma.com, with a free tier) is the industry-standard design tool and runs in the browser. Learn these ideas and you can design the whole app:

| **Concept** | **What it is** | **Why it matters** |
|---|---|---|
| **Frame** | A screen or container with a size (for example 390 x 844 for a modern phone) | Every screen is a frame |
| **Auto layout** | A frame that arranges its children with spacing and padding, like CSS flexbox | Designs resize like real UI and translate directly to code |
| **Components** | Reusable elements (button, input, message bubble) defined once, used many times | Edit once, update everywhere; mirrors React components |
| **Variants** | One component with several states (default, hover, disabled, loading) | Forces you to design states |
| **Styles / variables** | Named colors, text styles, spacing: your design tokens | Single source of truth (see 9.7) |
| **Prototype** | Link frames with clicks and transitions | Test the flow with real people before coding |
| **Dev Mode** | Inspect spacing, colors and export assets | Handoff to you, or to yourself |

Useful starters: Figma Community has free UI kits for iOS, Material Design and shadcn/ui. Starting from a good kit is **not cheating**; it is how most products begin. Replace colors and type with your tokens and you have a coherent look in an afternoon.


## Design Systems and Design Tokens › Components and their states

Every interactive component must be designed in **all its states**. A button, for example:

| **State** | **What the user sees** |
|---|---|
| Default | Filled primary color with a clear label |
| Hover / pressed | Slightly darker; on touch devices a pressed style gives instant feedback |
| Focused | A visible outline for keyboard users (never remove it without a replacement) |
| Disabled | Reduced emphasis; explain **why** nearby if it is not obvious |
| Loading | A spinner, label changes to "Saving...", and the button cannot be tapped twice (prevents duplicate payments and messages) |
| Error | The surrounding form shows what went wrong, not only the button |

The **Loading** state is where design meets engineering: a "Pay" button that can be double-tapped creates double charges. Disable it while the request is in flight, and back it with an idempotency key on the server (Chapter 8).


## Accessibility (a11y) › Testing accessibility

| **Tool** | **What it checks** |
|---|---|
| **Lighthouse** (Chrome DevTools) | Automated accessibility audit with a score and a list of issues |
| **axe DevTools** extension, `jest-axe` | Finds many WCAG violations; can run in automated tests |
| **Keyboard-only test** | Can you complete sign up and send a message without a mouse? |
| **Screen reader test** | Turn on VoiceOver, TalkBack or NVDA and try to complete one task with your eyes closed |
| **Zoom / large text test** | Layout still works at 200% zoom and large system fonts |
| **Grayscale test** | Is the interface still understandable without color? |

Automated tools find roughly a third to half of accessibility problems; manual testing finds the rest. Even doing the keyboard and screen reader checks **once** will teach you more than any article.


## Designing Every State, Forms and Microcopy › Microcopy: the words in the interface

Short texts on buttons, errors and empty states are some of the most important design work. Principles: be **specific**, **human**, **brief**, and **never blame the user**. Say what happened, why (if it helps) and what to do next.

| **Situation** | **Weak** | **Better** |
|---|---|---|
| Button | Submit | Send message / Create account / Pay 19.00 USD |
| Network error | Error 500 | Something went wrong on our side. Your message is saved. Try again in a moment. |
| Invalid email | Invalid input | Enter an email like name@example.com |
| Token limit | Request failed (429) | You’ve used all 1,000,000 tokens this month. They reset on Dec 1, or you can upgrade now. |
| Payment declined | Transaction failed | Your bank declined the payment. Try another card or pay by bank transfer. |
| Delete | Are you sure? | Delete this conversation? This can’t be undone. [Cancel] [Delete conversation] |


## Designing Payment and Subscription UX

Money moments are where trust is won or lost. Design them carefully, because you will implement them in Part VII.


### Pricing page

- Show **2 to 3 plans** with a recommended one highlighted. Compare by **outcomes** ("about 500 chats a month"), not only technical numbers (tokens), and keep the exact limits one tap away.
- State the **currency, billing period and total** up front. Offer monthly and yearly with the yearly saving shown clearly.
- Show prices in the user’s currency when possible (for example NGN with Paystack, USD with Stripe) and explain taxes and fees clearly.
- Be explicit about trials: when they end, the price afterwards, and how to cancel.

### Upgrade prompts: at the moment of value

The best time to ask for money is when the user has just hit a limit while getting value. Explain what happened, what they get by upgrading, and when the free allowance resets, so it is a choice, not a trap. Never block a user from accessing or exporting their existing data because of an unpaid plan.


### Checkout

- **Minimize steps**; do not ask for information the payment provider already collects.
- Use the provider’s **hosted checkout** or official mobile SDK for card entry. It is more secure, handles local payment methods (cards, bank transfer, USSD and wallets with Paystack; cards, Apple Pay and Google Pay with Stripe) and keeps you out of heavy compliance duties.
- Show trust signals: a lock icon, the provider’s name, accepted methods, a link to terms and refund policy.
- **Disable the pay button on click** and show a progress state to prevent double charges.

### After payment

- Show a success screen that confirms the plan, amount, next billing date and what is unlocked, and send a receipt by email.
- Payments are confirmed by **webhooks**, which may arrive a few seconds after the user returns to your app. Design a **pending** state ("Confirming your payment...") that polls or listens on the WebSocket, instead of telling users "payment failed" while it is still processing.

### Failure and retention

- Show specific failure reasons from the provider in human language, and offer another method.
- For a failed renewal, show a clear **banner** ("Update your payment method to keep Pro") with a grace period, not a sudden lockout.
- **Make cancellation easy to find.** Hidden or confusing cancellation causes chargebacks, bad reviews and, in many jurisdictions, regulatory problems. Offer "pause" or a downgrade as an alternative, then respect the choice.

## Usability Testing › Nielsen’s ten usability heuristics (a review checklist)

| **Heuristic** | **Ask yourself** |
|---|---|
| 1. Visibility of system status | Does the user always know what is happening (loading, saved, offline, streaming)? |
| 2. Match with the real world | Does it use the user’s language, not our internal jargon (say "monthly limit", not "token quota")? |
| 3. User control and freedom | Can they undo, cancel, stop and go back? |
| 4. Consistency and standards | Do similar things look and work the same, and follow platform conventions? |
| 5. Error prevention | Can we stop the mistake before it happens (confirmations, disabling, sensible defaults)? |
| 6. Recognition over recall | Are options visible instead of requiring memory? |
| 7. Flexibility and efficiency | Are there shortcuts for experts (keyboard, saved prompts) that do not burden beginners? |
| 8. Minimalist design | Is every element needed? Does anything distract from the main task? |
| 9. Help users recover from errors | Are messages plain, precise and constructive? |
| 10. Help and documentation | Is help findable and task-focused? |


## Usability Testing › Measure after launch

- **Task success rate** (did they finish sign up?), **time on task**, **drop-off per step** in your funnel (analytics events at each step of the flow).
- **SUS** (System Usability Scale), a 10-question survey with a score out of 100; around 68 is average.
- Qualitative feedback: in-app feedback button, support tickets, app store reviews. Read them weekly.
> **Using AI for design feedback**
>
> You can paste a screenshot or description of a screen into an AI assistant and ask for a heuristic review, microcopy alternatives, accessibility concerns or edge cases you forgot. This is a useful first pass and a good brainstorming partner. It is **not a replacement for watching real users**, because it cannot tell you what confuses the actual people you serve. Never upload confidential designs or customer data to tools your organization has not approved.


## From Design to Code: Handoff and Design QA

- **Name things the same in design and code**: a Figma component called `MessageBubble` becomes `components/chat/MessageBubble.tsx`; tokens have identical names in Figma variables, `tokens.json`, CSS and TypeScript.
- **Build the smallest components first** (Button, Input, Badge), then compose bigger ones (MessageBubble, Composer, PlanCard). Document them in **Storybook** if you wish, showing each state.
- **Build every state**: use the screen inventory and states table as a checklist so empty, loading and error states are never forgotten.
- **Use real data and real devices**: test on an actual low-end Android phone and on a slow connection, not only on your fast laptop and simulator.
- **Design QA before release**: compare the built screen with the design for spacing, type, color and behavior; run the keyboard test and the contrast check; test dark mode.
- **Keep the design file alive.** When you change the UI in code, update the design, so the source of truth does not drift.