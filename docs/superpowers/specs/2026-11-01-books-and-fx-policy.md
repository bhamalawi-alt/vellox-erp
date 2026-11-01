# Company Books and Exchange-Rate Policy

**Card:** [P5A-103] · **Date:** 2026-11-01 · **Status:** owner decisions taken 2026-11-01;
**accountant sign-off pending**
**Unblocks:** [P5A-104] chart of accounts, fiscal year, cost centers · [P5A-105]
currencies and exchange rates · [P5A-107] bank accounts · and through them all of P5
(billing, expenses, retainers, collections)
**Source:** `reports/Vellox company system roadmap.md` (research of 2026-10-30),
section "Finance foundation" and owner decisions 5 and 6. ERPNext behaviour is
checked against ERPNext 15.124.3 / Frappe 15.125.0.

This is a policy, not a build. Nothing in P5A or P5 starts until it is approved by
the owner (done) and Vellox's accountant (open).

## 1. Owner decisions (2026-11-01)

| # | Question | Decision |
|---|---|---|
| F1 | Book currency | **LYD.** The Libyan company keeps its books in Libyan dinars; USD is a reporting view |
| F2 | LYD exchange rate | **Central Bank of Libya (CBL) official rate, entered by hand.** Never fetched automatically; ERPNext must be configured to enforce this (section 3.2) |
| F3 | Parallel-market rate | **A management memo only.** Noted for management reports; never posted in the books |
| F4 | Foreign-currency receipts | **An account abroad** receives clients' USD, EUR and EGP payments |
| F5 | Egypt-based people | **Freelancers or an employer-of-record.** No Egyptian company: no Egyptian payroll, VAT or e-invoicing |

## 2. Why these choices

- **LYD books.** The research infers that Libya's tax authority and the Social
  Security Fund expect dinar figures at the official rate (open point 5.1).
  Corporate income tax is 20 %, paid quarterly; the annual return follows audited
  accounts; the tax statute of limitations is 15 years, so records should be kept
  at least that long (PwC Libya, reviewed 31 May 2026).
- **Manual CBL rate.** The official rate (≈ 6.40 LYD per USD on 21 Oct 2026, after a
  14.7 % devaluation in January 2026) and the parallel market (above 10 LYD per USD
  in mid-October 2026, about 60 % higher) differ widely. ERPNext's built-in
  providers (frankfurter, which uses ECB rates, and exchangerate.host) are not the
  CBL, so LYD rates are typed in from the CBL.
- **Parallel rate as memo.** How a Libyan company accounts for parallel-market
  purchases is not documented anywhere the research found; it is an accounting
  policy call. Until the accountant decides otherwise it stays out of the books.
- **Account abroad.** Paying foreign suppliers from Libya is capped by CBL Decree
  428/2026, which reportedly ties a company's ceiling to its tax history (single
  secondary source); keeping foreign receipts abroad is both an operating and a
  compliance choice.
- **No Egyptian entity.** Egyptian freelancers register and pay their own tax; a
  Libyan payer has no Egyptian withholding duty. An employer-of-record is a monthly
  supplier invoice. An Egyptian company would add 14 % VAT (10 % for professional
  services), monthly filings and real-time e-invoicing with a signing token.

## 3. The policy

### 3.1 Company and currencies
- One Company, **Vellox Studio**, country Libya, **default currency LYD** (three
  decimals: 1 dinar = 1,000 dirhams).
- Enabled currencies: **LYD, USD, EUR, EGP** only.
- Quotes and invoices may be in any of the four; the ledger records the LYD value
  at each document's own rate.
- **Statutory figures are always the LYD ones.** Two USD views exist and will
  differ:
  - ERPNext's financial statements (Balance Sheet, P&L, Cash Flow, Trial Balance,
    General Ledger) can show USD with the Presentation Currency filter. It converts
    every line at the single USD→LYD rate of the report's end date, and **if no
    rate is found it shows the LYD figures labelled as USD, with no warning**.
  - Vellox's own reports (capacity and profit, plan D7) convert each amount at its
    own date from the same Currency Exchange records.

### 3.2 Exchange rates
| Pair | Source | Who | When |
|---|---|---|---|
| USD, EUR, EGP → LYD | CBL official rate, typed into Currency Exchange | Finance | Each business day a foreign-currency document is dated, and at month end |
| USD ↔ EUR ↔ EGP | Not used by the ledger: every posting goes through LYD | — | — |

- Records are entered as **1 USD/EUR/EGP = x LYD** (From = the foreign currency,
  To = LYD), with For Buying and For Selling both ticked unless the accountant
  wants separate CBL buy and sell rates. ERPNext looks up only that exact
  direction.
- A document uses the latest Currency Exchange record on or before its date.
  **ERPNext does not stop a document for a missing or old LYD rate by itself:** it
  reuses old records ("Allow Stale Exchange Rates" is on by default), falls back to
  the automatic provider (one global setting, enabled on the dev site), and accepts
  a rate typed on the document. Only a rate of 0 stops a document. To keep LYD
  rates CBL-only, [P5A-105] must:
  1. disable Currency Exchange Settings, or prove the provider returns nothing for LYD;
  2. turn off "Allow Stale Exchange Rates" and set Stale Days;
  3. decide whether typed conversion rates are allowed on documents.
- Vellox's profit report already refuses to run when no rate exists at all (it has
  no staleness check). It converts a quote's own currency straight to USD, so for
  EUR or EGP quotes either Finance also types EUR→USD and EGP→USD records, or the
  report converts through the quote's LYD base amount (decided in [P5A-105]).
- The card asked for automatic USD/EUR/EGP rates. With LYD books every rate the
  ledger uses is foreign → LYD and is typed from the CBL, so automatic cross rates
  are not needed by the books; ERPNext would only fetch them on demand (cached for
  six hours) and never stores them as records.
- The parallel rate is recorded in a management note (a memo field or a small
  report), never in Currency Exchange.

### 3.3 Revaluation and gains or losses
- Company accounts **Exchange Gain/Loss** and **Unrealized Exchange Gain/Loss** are
  set.
- Receivables and payables in USD, EUR or EGP use **Debtors and Creditors accounts
  in that currency**, set as each customer's and supplier's party account
  ([P5A-104]); Exchange Rate Revaluation only revalues accounts whose currency is
  not LYD, so balances kept in the LYD Debtors/Creditors are never revalued.
- **Exchange Rate Revaluation is run by hand, dated the last day of each month**,
  after the month-end CBL rate is entered. The company's auto-revaluation stays off
  (it posts on the day the job runs, not at month end).
- Expect large, volatile figures: the dinar moved 14.7 % in one step in 2026.

### 3.4 Where money is received
- **Abroad:** one Bank Account per currency (USD, EUR, EGP) at the account abroad,
  each linked to its own ledger account in that currency.
- **In Libya:** an LYD bank account and LYD petty cash for local clients and costs.
- Bank statements are imported per account (one currency per account) and
  reconciled against Payment Entries ([P5A-107]).
- Left out for now (open for [P5A-107]): an e-wallet balance (Sadad/Edfali) and an
  EGP account or petty cash in Egypt, both listed in the research.

### 3.5 Egypt-based people
- Freelancers are **Suppliers** in a "Freelancers" supplier group; they invoice
  Vellox, and their time is recorded on Timesheets as for staff.
- An employer-of-record is a Supplier invoicing monthly.
- Their cost rates (Activity Cost per person, or the role default) are in **LYD**
  like every company-currency amount, converted at the CBL rate on the day Finance
  sets them. Cost rates carry no date, so Finance re-sets them when the CBL rate
  moves by more than a threshold to be decided, or quarterly, whichever comes
  first; quotes awaiting approval are then re-saved (approval already refuses
  changed rates).
- Libyan payroll (Frappe HR) covers people on Libyan contracts only ([P9-116]).
  Libyan labour law sets a 75 % Libyan-workforce quota for people on Libyan
  contracts.

### 3.6 Taxes (for [P5A-104] and [P5A-108])
- No VAT, excise or withholding tax on Libyan sales invoices.
- Liability accounts: Stamp Duty Payable, SSF Payable, PIT Payable, CIT Payable.
- Stamp duty 1 % on main service contracts and 0.1 % on subcontracts (PwC); the
  accountant confirms how it is charged (open point 5.3).
- Invoicing Egyptian clients from Libya may trigger a 20 % non-resident
  withholding on the client's side unless the Egypt–Libya tax treaty applies (not
  researched): this belongs in the master service agreement for Egyptian clients.

## 4. What changes in the system

1. **The dev site is rebuilt as an LYD company** in [P5A-104]. ERPNext refuses to
   change a company's currency once submitted quotations, orders or invoices
   exist, and the existing accounts, rates and prices are in USD, so the current
   company is replaced, not converted. The local test site and CI use their own
   fixtures and are unaffected.
2. **Role cost rates move to LYD.** The Egypt-based rates set on the dev site (USD
   per hour, 2026-11-01) are re-entered in LYD at the CBL official rate when the
   company is rebuilt; Finance confirms them.
3. **Price lists:** USD and EGP stay, EUR is added, and LYD is added for local
   clients ([P5A-106]).
4. Vellox's profit and capacity reports keep showing USD at each document's date
   (section 3.1).

## 5. Open points for the accountant

1. Confirm LYD book currency and the CBL official rate for statutory books.
2. Treatment of parallel-market purchases (kept out of the books until decided).
3. Stamp duty: how it is charged on contracts (a tax row on invoices or a Journal
   Entry), plus PwC's 0.5 % on every payment to the Tax Department and the 0.5 % on
   net salaries one Libyan firm (QBS) adds.
4. Social Security Fund rates: PwC gives 5.125 % employee / 14.35 % employer /
   1.025 % treasury; employer-of-record guides give 3.75 % / 10.5 % / 0.75 %.
   Confirm with the SSF before the first payroll ([P9-116]).
5. Whether the Jehad tax still applies (PwC says abolished; some guides still list
   it).
6. Fiscal year: the research gives 1 January to 31 December, and changing it needs
   the Tax Department's prior permission. Chart-of-accounts conventions: a local
   Frappe partner (Ebkar) is a resource.

## 6. Open for later cards

- **[P5A-105] Currencies:** provider on or off; Stale Days; typed conversion
  rates allowed or not; one CBL rate or separate buy and sell rates; who enters
  rates (role and Currency Exchange permission); whether the CBL publishes an
  official EGP rate; how the profit report converts EUR and EGP quotes; guarding
  against the silent fallback to 1 in USD statements.
- **[P5A-104] Books:** Debtors and Creditors accounts per currency and party
  defaults; the multi-currency party-account setting; LYD three-decimal precision;
  opening balances and the go-live date of the rebuilt company; stamp duty as a tax
  row or a Journal Entry.
- **[P5A-107] Banks:** who legally holds the account abroad (if it is not in the
  Libyan company's name it is not a company Bank Account, and receipts need a
  different treatment); which account pays Egyptian freelancers and in which
  currency; how money moves between the account abroad and the LYD bank, within
  the Decree 428 limits; the e-wallet and EGP accounts left out above.
- **[P5A-108] Terms:** a withholding clause on invoices to Egyptian clients, and the
  treaty check.
- **Reporting:** which USD view the owner reads for management (closing-rate
  statements or each document's date).
- **Cost rates:** the CBL movement threshold that triggers re-setting LYD cost
  rates.

## 7. Sign-off

Recorded on the Trello card [P5A-103]:
- Owner: decisions F1–F5, 2026-11-01.
- Accountant: pending.
