# Vellox Trello Social Media Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old Vellox Social Media Trello content with a clean six-stage production workflow and 144 fully written, English-first social media concepts for MENA SMB customer acquisition.

**Architecture:** Trello is the production source of truth. One card represents one strategic concept and contains the master design brief plus separate LinkedIn, Instagram, Facebook, and X captions. Cards move through a six-list workflow; service labels, stable identifiers, due dates, and checklists make production status visible without platform-list duplication.

**Tech Stack:** Trello board connector, Vellox Studio public website, approved campaign design specification, Trello lists/cards/labels/checklists/due dates.

## Global Constraints

- Target owners and decision-makers at SMBs across the MENA region without limiting the campaign to specific industries.
- Use English only during this implementation; translation is a later phase.
- Promote branding, social media design, and website design/development.
- Use no video concepts during the six-month campaign.
- Use six master concepts per week for 24 production weeks, totaling 144 cards.
- Adapt every concept for LinkedIn, Instagram, Facebook, and X inside one Trello card.
- Keep the tone clean, confident, concise, professional, and not overly friendly.
- Use WhatsApp and direct messages as the conversion channels, with `BRAND`, `SOCIAL`, and `WEBSITE` as service keywords.
- Do not invent client names, quotations, results, prices, scarcity, guarantees, or contact details.
- Archive the old Trello cards and lists so they disappear from the active board but remain recoverable.
- Public posting, direct outreach, and messaging are outside this implementation.

---

### Task 1: Verify and Clear the Existing Board

**Surfaces:**
- Read: Trello board `Vellox Social Media` (`https://trello.com/b/NBjkHUfG/vellox-social-media`)
- Modify: All currently open cards and lists on that board

**Interfaces:**
- Consumes: Existing board identifier and authenticated Trello connection.
- Produces: An active board with no old open cards or lists; archived content remains recoverable through Trello.

- [ ] **Step 1: Capture the deletion baseline**

  Read all open cards grouped by list and confirm the expected baseline: 10 cards across Facebook, Instagram, LinkedIn, and Content Strategy; no cards in Published or Ready to Post.

- [ ] **Step 2: Archive every old card**

  Archive all 10 open cards using their Trello card ARIs. Re-read the board and confirm that no open cards remain.

- [ ] **Step 3: Archive every old list**

  Archive Published, Ready to Post, Facebook, Instagram, LinkedIn, and Content Strategy using their list ARIs.

- [ ] **Step 4: Verify the cleared state**

  Read the board's open lists and cards. Expected result: zero open lists and zero open cards.

---

### Task 2: Build the Clean Production Workflow

**Surfaces:**
- Modify: Trello board `Vellox Social Media`

**Interfaces:**
- Consumes: Cleared board from Task 1.
- Produces: Six ordered list ARIs used by every later task.

- [ ] **Step 1: Create the six lists in order**

  Create these open lists from left to right: `Start Here`, `Planned`, `Design in Progress`, `Review`, `Ready to Publish`, `Published`.

- [ ] **Step 2: Verify order and uniqueness**

  Read all open lists. Expected result: exactly six lists, with the exact names above and no duplicates.

- [ ] **Step 3: Create the service labels**

  Create or normalize exactly three active labels: `Branding`, `Social Media`, and `Websites`. Use three visually distinct colors and do not create month, platform, or status labels.

- [ ] **Step 4: Record stable identifiers**

  Keep the board ARI, six list ARIs, and three label identifiers available for later Trello writes. Verify each identifier belongs to this board before use.

---

### Task 3: Create the Start Here Operating Cards

**Surfaces:**
- Create: Four Trello cards in `Start Here`

**Interfaces:**
- Consumes: `Start Here` list ARI from Task 2 and the approved design specification.
- Produces: Four reference cards used by designers, reviewers, and publishers.

- [ ] **Step 1: Create `01 — READ FIRST — Campaign Strategy`**

  Include the objective, MENA SMB audience, three services, six-month journey, six-post weekly rhythm, platforms, English-first rule, no-video rule, and the DM/WhatsApp conversion path.

- [ ] **Step 2: Create `02 — DESIGN SYSTEM — Visual & Copy Rules`**

  Include strong typography, structured grids, generous space, one idea per design, minimal decoration, adaptable hierarchy, calm professional language, and the prohibited style patterns from the specification.

- [ ] **Step 3: Create `03 — CARD TEMPLATE — Production Brief`**

  Include the exact card sections: Purpose, Format, On-design copy, Visual direction, LinkedIn caption, Instagram caption, Facebook caption, X caption, CTA, Required assets, and Approval notes.

- [ ] **Step 4: Add the production checklist to the template card**

  Create a checklist containing: facts verified; assets collected; master design complete; four platform adaptations complete; copy and artwork reviewed; final approval received; four platforms published; links and initial results recorded.

- [ ] **Step 5: Create `04 — WEEKLY RESULTS — Lead & Performance Log`**

  Include a 24-week table-style text log for qualified DMs, qualified WhatsApp enquiries, calls, proposals, customers, saves/shares, best topic, best format, best service, and the following week's adjustment.

- [ ] **Step 6: Verify the reference area**

  Read `Start Here`. Expected result: exactly four cards ordered `01` through `04`, all descriptions present, and the template checklist present.

---

### Task 4: Populate Month 1 — Recognition

**Surfaces:**
- Create: 24 Trello cards in `Planned`

**Interfaces:**
- Consumes: Planned list and service labels from Task 2; copy and design rules from Task 3.
- Produces: Cards `M01 W01 P01` through `M01 W04 P06`.

- [ ] **Step 1: Write Week 1 — Brand clarity**

  Create six complete concepts covering unclear positioning, broad offers, five-second comprehension, a brand-clarity checklist, a real Vellox brand example, and a `BRAND` diagnostic CTA.

- [ ] **Step 2: Write Week 2 — Visual consistency**

  Create six complete concepts covering inconsistent identity, logo-versus-system thinking, trust signals, a visual consistency audit, approved identity proof, and a `BRAND` CTA.

- [ ] **Step 3: Write Week 3 — Website recognition**

  Create six complete concepts covering unclear homepages, hidden proof, weak next steps, a homepage audit, a real website example, and a `WEBSITE` CTA.

- [ ] **Step 4: Write Week 4 — Social media recognition**

  Create six complete concepts covering disconnected post design, inconsistent templates, content without a business purpose, a social feed audit, a real social-design example, and a `SOCIAL` CTA.

- [ ] **Step 5: Validate Month 1**

  Read the 24 cards. Confirm exact on-design text, four distinct platform captions, one matching service label, one CTA keyword, required assets, approval notes, and the full production checklist on every card.

---

### Task 5: Populate Month 2 — Education

**Surfaces:**
- Create: 24 Trello cards in `Planned`

**Interfaces:**
- Consumes: Same card contract as Task 4.
- Produces: Cards `M02 W05 P01` through `M02 W08 P06`.

- [ ] **Step 1: Write Week 5 — Positioning and messaging**

  Cover audience definition, category framing, differentiators, message hierarchy, an approved strategy example, and a `BRAND` CTA.

- [ ] **Step 2: Write Week 6 — Identity systems**

  Cover logo roles, color discipline, typography hierarchy, scalable design systems, approved identity proof, and a `BRAND` CTA.

- [ ] **Step 3: Write Week 7 — Social design systems**

  Cover content pillars, reusable templates, hierarchy, consistency without repetition, approved social proof, and a `SOCIAL` CTA.

- [ ] **Step 4: Write Week 8 — Website foundations**

  Cover homepage structure, service-page clarity, proof placement, CTA structure, approved website proof, and a `WEBSITE` CTA.

- [ ] **Step 5: Validate Month 2**

  Confirm 24 cards, four adapted captions per card, accurate formatting, service balance, checklist completeness, and no duplicated headline from Month 1.

---

### Task 6: Populate Month 3 — Proof

**Surfaces:**
- Create: 24 Trello cards in `Planned`

**Interfaces:**
- Consumes: Publicly verified Vellox portfolio material and only user-approved client evidence.
- Produces: Cards `M03 W09 P01` through `M03 W12 P06`.

- [ ] **Step 1: Write Week 9 — Brand proof**

  Use approved project material to explain the initial problem, strategic decision, identity system, application, client perspective, and `BRAND` CTA without inventing performance figures.

- [ ] **Step 2: Write Week 10 — Website proof**

  Use approved website work to explain information architecture, messaging, responsive design, conversion path, client perspective, and `WEBSITE` CTA.

- [ ] **Step 3: Write Week 11 — Social design proof**

  Use approved visual-content or social-system work to explain the brief, visual system, content flexibility, consistency, client perspective, and `SOCIAL` CTA.

- [ ] **Step 4: Write Week 12 — Cross-service proof**

  Show how brand, social, and website decisions reinforce one another through three project lessons, one process comparison, one testimonial, and one combined diagnostic CTA.

- [ ] **Step 5: Validate every proof claim**

  Confirm that every client name, quotation, image request, and result appears in approved source material. Replace any unsupported outcome with a clearly labeled process lesson.

---

### Task 7: Populate Month 4 — Authority

**Surfaces:**
- Create: 24 Trello cards in `Planned`

**Interfaces:**
- Consumes: Vellox website positioning and approved campaign voice.
- Produces: Cards `M04 W13 P01` through `M04 W16 P06`.

- [ ] **Step 1: Write Week 13 — Meaningful design**

  Cover design as communication, strategic rationale, restraint, durability, a Vellox standard, and a `BRAND` CTA.

- [ ] **Step 2: Write Week 14 — One accountable system**

  Cover hand-off risk, brand-to-web continuity, social consistency, a connected-system checklist, Vellox's integrated process, and a combined CTA.

- [ ] **Step 3: Write Week 15 — MENA SMB decision quality**

  Cover professional credibility, bilingual-ready systems without translating now, regional expansion readiness, channel consistency, a practical decision framework, and the relevant service CTA.

- [ ] **Step 4: Write Week 16 — Studio process**

  Cover discovery, strategic alignment, design exploration, review discipline, launch preparation, and a direct consultation CTA.

- [ ] **Step 5: Validate Month 4**

  Confirm 24 distinct concepts, calm authority, no generic motivational content, and no claim that depends on unverified market statistics.

---

### Task 8: Populate Month 5 — Consideration

**Surfaces:**
- Create: 24 Trello cards in `Planned`

**Interfaces:**
- Consumes: Approved public service descriptions and realistic timelines from the Vellox website.
- Produces: Cards `M05 W17 P01` through `M05 W20 P06`.

- [ ] **Step 1: Write Week 17 — Choosing the right service**

  Cover when a business needs strategy, identity, social design, a website, a combined engagement, and a service-selection CTA.

- [ ] **Step 2: Write Week 18 — Deliverables and timelines**

  Explain what a client receives, how scope affects timing, the role of approvals, what readiness looks like, Vellox's delivery standard, and a consultation CTA without inventing prices.

- [ ] **Step 3: Write Week 19 — Objections and risk**

  Address redesign timing, internal alignment, content readiness, platform choice, the cost of inconsistency, and a low-pressure diagnostic CTA.

- [ ] **Step 4: Write Week 20 — Working relationship**

  Explain communication, feedback, decision ownership, revision discipline, launch support, and who is a strong fit for Vellox.

- [ ] **Step 5: Validate Month 5**

  Confirm 24 cards, accurate public service details, no invented price, no false urgency, and a clear decision benefit in each caption.

---

### Task 9: Populate Month 6 — Conversion

**Surfaces:**
- Create: 24 Trello cards in `Planned`

**Interfaces:**
- Consumes: Strongest approved proof and all earlier service narratives.
- Produces: Cards `M06 W21 P01` through `M06 W24 P06`.

- [ ] **Step 1: Write Week 21 — Brand diagnostic campaign**

  Create a brand-symptom post, identity audit, positioning framework, approved proof, fit criteria, and a direct `BRAND` DM/WhatsApp offer.

- [ ] **Step 2: Write Week 22 — Website diagnostic campaign**

  Create a website-symptom post, homepage audit, conversion-path framework, approved proof, fit criteria, and a direct `WEBSITE` DM/WhatsApp offer.

- [ ] **Step 3: Write Week 23 — Social design diagnostic campaign**

  Create a social-symptom post, feed audit, template-system framework, approved proof, fit criteria, and a direct `SOCIAL` DM/WhatsApp offer.

- [ ] **Step 4: Write Week 24 — Portfolio and consultation close**

  Create three strongest-work recaps, one integrated-services post, one FAQ, and one direct invitation to discuss the next project.

- [ ] **Step 5: Validate Month 6**

  Confirm 24 cards, clear DM/WhatsApp routes, correct service keywords, professional selectivity, and no guarantee or false scarcity.

---

### Task 10: Schedule and Finalize the Production System

**Surfaces:**
- Modify: All 144 planned cards
- Read: Complete Trello board

**Interfaces:**
- Consumes: All month batches and workflow identifiers.
- Produces: A scheduled, verified six-month production board ready for designers.

- [ ] **Step 1: Apply stable titles and ordering**

  Verify consecutive identifiers from `M01 W01 P01` through `M06 W24 P06`. Within each week, order cards P01 through P06.

- [ ] **Step 2: Apply publish dates**

  Start on Monday, 2026-08-31. Schedule six concepts per production week, Monday through Saturday, at 10:00 in `Africa/Cairo`, unless a later performance review changes the time. Store Trello due dates in UTC after verifying the authenticated member timezone and applying Cairo daylight-saving offsets for each date.

- [ ] **Step 3: Verify board totals**

  Expected active state: six lists, four Start Here cards, 144 Planned cards, zero cards in active production/review/ready/published lists, and zero old open cards.

- [ ] **Step 4: Sample every month for copy quality**

  Read at least two cards from each month and confirm exact on-design copy, four platform captions, visual direction, CTA, assets, approval notes, service label, due date, and checklist.

- [ ] **Step 5: Run duplicate and safety review**

  Confirm there are no duplicate titles, copied captions across all four platforms, invented claims, prices, contact details, client results, fake scarcity, or video instructions.

- [ ] **Step 6: Deliver the board**

  Provide the literal board URL `https://trello.com/b/NBjkHUfG/vellox-social-media`, the final counts, the assumed first publish date and time, and any cards that require Vellox to attach real project assets before design begins.
