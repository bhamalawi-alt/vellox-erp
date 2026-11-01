# Company Books and Exchange-Rate Policy

**Card:** [P5A-103] · **Date:** 2026-11-01 · **Status:** owner decisions taken 2026-11-01;
**accountant sign-off pending**
**Unblocks:** [P5A-104] chart of accounts, fiscal year, cost centers · [P5A-105]
currencies and exchange rates · [P5A-107] bank accounts · and through them all of P5
(billing, expenses, retainers, collections)
**Source:** `reports/Vellox company system roadmap.md` (research of 2026-10-30),
section "Finance foundation" and owner decisions 5 and 6

This is a policy, not a build. Nothing in P5A or P5 starts until it is approved by
the owner (done) and Vellox's accountant (open).

## 1. Owner decisions (2026-11-01)

| # | Question | Decision |
|---|---|---|
| F1 | Book currency | **LYD.** The Libyan company keeps its books in Libyan dinars; USD is a reporting view |
| F2 | LYD exchange rate | **Central Bank of Libya (CBL) official rate, entered by hand.** Never fetched automatically |
| F3 | Parallel-market rate | **A management memo only.** Noted for management reports; never posted in the books |
| F4 | Foreign-currency receipts | **An account abroad** receives clients' USD, EUR and EGP payments |
| F5 | Egypt-based people | **Freelancers or an employer-of-record.** No Egyptian company: no Egyptian payroll, VAT or e-invoicing |

## 2. Why these choices

- **LYD books.** Libya's tax authority and the Social Security Fund expect dinar
  figures at the official rate. Corporate income tax is 20 %, paid quarterly; the
  annual return follows audited accounts; records must be kept 15 years (PwC Libya,
  reviewed 31 May 2026). Keeping the books in dinars avoids re-converting every
  filing outside the system.
- **Manual CBL rate.** The official rate (≈ 6.40 LYD per USD on 21 Oct 2026, after a
  14.7 % devaluation in January 2026) and the parallel market (above 10 LYD per USD
  in mid-October 2026, about 60 % higher) differ widely. ERPNext's automatic rate
  providers do not publish the CBL rate, so LYD rates are typed in from the CBL.
- **Parallel rate as memo.** How a Libyan company accounts for parallel-market
  purchases is not documented anywhere the research found; it is an accounting
  policy call. Until the accountant decides otherwise it stays out of the books.
- **Account abroad.** Paying foreign suppliers from Libya now depends on a
  company's tax history (CBL Decree 428/2026); keeping foreign receipts abroad is
  both an operating and a compliance choice. Each such account is its own Bank
  Account in ERPNext, in its own currency.
- **No Egyptian entity.** Egyptian freelancers register and pay their own tax;
  a Libyan payer has no Egyptian withholding duty. An employer-of-record is a
  monthly supplier invoice. An Egyptian company would add 14 % VAT, monthly
  filings and real-time e-invoicing with a signing token.

## 3. The policy

### 3.1 Company and currencies
- One Company, **Vellox Studio**, country Libya, **default currency LYD**.
- Enabled currencies: **LYD, USD, EUR, EGP** only.
- Quotes and invoices may be in any of the four; the ledger records the LYD value
  at each document's own rate.
- Management reports use ERPNext's **presentation currency** (USD) on the
  financial statements. Vellox's own reports already show USD at each document's
  date (capacity plan D7); they read the same Currency Exchange records.

### 3.2 Exchange rates
| Pair | Source | Who | When |
|---|---|---|---|
| LYD ↔ USD, EUR, EGP | CBL official rate, typed into Currency Exchange | Finance | Each business day a foreign-currency document is dated, and at month end |
| USD ↔ EUR ↔ EGP | ERPNext's automatic provider | System | Daily |

- A document uses the latest rate on or before its date. A missing LYD rate stops
  the document with a clear message rather than guessing.
- The parallel rate is recorded in a management note (a memo field or a small
  report), never in Currency Exchange.

### 3.3 Revaluation and gains or losses
- Company accounts **Exchange Gain/Loss** (realised) and **Unrealized Exchange
  Gain/Loss** are set.
- **Exchange Rate Revaluation** runs **monthly** on open foreign-currency
  receivables, payables and bank balances, at the month-end CBL rate.
- Expect large, volatile figures: the dinar moved 14.7 % in one step in 2026.

### 3.4 Where money is received
- **Abroad:** one Bank Account per currency (USD, EUR, EGP) at the account
  abroad, each linked to its own ledger account in that currency.
- **In Libya:** an LYD bank account and LYD petty cash for local clients and
  costs.
- Bank statements are imported per account (one currency per account) and
  reconciled against Payment Entries ([P5A-107]).
- Still to confirm: the bank or platform holding the account abroad, and whether
  it accepts a Libyan company (not confirmed for Wise or Payoneer).

### 3.5 Egypt-based people
- Freelancers are **Suppliers** in a "Freelancers" supplier group; they invoice
  Vellox, and their time is recorded on Timesheets as for staff.
- An employer-of-record is a Supplier invoicing monthly.
- Their cost rates (Activity Cost per person, or the role default) are in **LYD**
  like every company-currency amount, converted from what they are paid at the CBL
  rate of the rate's effective date.
- Libyan payroll (Frappe HR) covers people on Libyan contracts only ([P9-116]).
  Note: Libyan labour law sets a 75 % Libyan-workforce quota for people on Libyan
  contracts.

### 3.6 Taxes (for [P5A-104] and [P5A-108])
- No VAT, excise or withholding tax on Libyan sales invoices.
- Liability accounts: Stamp Duty Payable, SSF Payable, PIT Payable, CIT Payable.
- Stamp duty 1 % on main service contracts and 0.1 % on subcontracts (PwC); the
  accountant confirms how it is charged.
- Invoicing Egyptian clients from Libya may trigger a 20 % non-resident
  withholding on the client's side unless the Egypt–Libya tax treaty applies
  (not researched): this belongs in the master service agreement for Egyptian
  clients.

## 4. What changes in the system

1. **The dev site is rebuilt as an LYD company** in [P5A-104]. ERPNext cannot
   change a company's currency once it has transactions, so the current USD dev
   company is replaced, not converted. The local test site and CI use their own
   fixtures and are unaffected.
2. **Role cost rates move to LYD.** The Egypt-based rates set on the dev site
   (USD per hour, 2026-11-01) are re-entered in LYD at the CBL official rate when
   the company is rebuilt; Finance confirms them.
3. **Price lists:** USD and EGP stay, EUR is added and LYD is added for local
   clients ([P5A-106]).
4. Vellox's profit and capacity reports keep showing USD; they convert LYD costs
   with the same manual CBL records.

## 5. Open points for the accountant

1. Confirm LYD book currency and the CBL official rate for statutory books.
2. Treatment of parallel-market purchases (kept out of the books until decided).
3. How stamp duty is charged on contracts (rate and on which documents).
4. Social Security Fund rates: PwC gives 5.125 % employee / 14.35 % employer /
   1.025 % treasury; employer-of-record guides give 3.75 % / 10.5 % / 0.75 %.
   Confirm with the SSF before the first payroll ([P9-116]).
5. Whether the Jehad tax still applies (PwC says abolished; some guides still
   list it).
6. Fiscal year (calendar year assumed) and chart-of-accounts conventions; a local
   Frappe partner (Ebkar) is a resource.

Sign-off is recorded on the Trello card [P5A-103]:
- Owner: decisions F1–F5, 2026-11-01.
- Accountant: pending.
