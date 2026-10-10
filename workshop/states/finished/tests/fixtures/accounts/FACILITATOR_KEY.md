# Facilitator key: what is planted in the example data

This older example data was made before the brief existed and does not match the wedding story; it is kept as the source adapter's test fixture, which the tests read (the wedding example's own account files and key are in `examples/wedding/data/`).

Written by `tests/fixtures/accounts/generate.py` (seed 20261009). Everything is invented.
Remove this file from any copy you hand to attendees if you want them to
find these for themselves.

The story: one person's accounts from 2026-01-01 to 2026-09-30,
and a wedding on 2027-06-12 that is partly paid for.

| File | What it is | Format |
| --- | --- | --- |
| `checking_2026.csv` | Main current account | Semicolons, `dd/mm/yyyy`, `1.150,00`, newest first, money out is negative |
| `savings_2026.csv` | Savings account | Same as checking |
| `card_2026.csv` | Credit card | Commas, ISO dates, `1150.00`, oldest first, **charges are positive** |
| `wedding_budget.csv` | Budget kept by hand | Whatever the person typed |

## Reference figures

| Figure | Value |
| --- | --- |
| Checking balance before the first row | 6180.52 |
| Checking balance after the last row | 6318.60 |
| Savings balance before the first row | 6200.00 |
| Savings balance after the last row | 13353.39 |
| Real checking transactions (after removing repeats) | 112 |
| Card transactions | 248 |
| September card spending, not yet billed | 2373.26 |
| Sum of the budget rows (flowers at the midpoint) | 33174.00 |
| Total typed at the bottom of the budget | 31500.00 |

## Planted quirks

Format and structure (these test "the harness is not tied to an input format"):

1. **Two sign conventions.** A card charge is positive; a bank debit is negative.
2. **Two number and date formats.** `1.150,00` with `dd/mm/yyyy` in the bank files, `1150.00` with ISO dates on the card.
3. **Two sort orders.** Bank files are newest first, the card file oldest first.
4. **A pasted export.** `checking_2026.csv` is two exports in one file. The header row appears again in the middle, and every row dated 30/06/2026 appears twice. The repeated rows carry the same balance, which is how you can tell they are repeats and not real second payments.
5. **Messy merchant names.** The same supermarket appears as `MERCADONA`, `Mercadona S.A.` and `MERCADONA 2231 MADRID`.

Meaning (these need the shared domain, a judgment call or a check):

6. **Paying the card is not spending.** Each `RECIBO TARJETA CREDITO` in checking equals the previous month's card total. Counting both doubles the spending. January's bill (612.40) is for December, which is not in the card file.
7. **Moving money to savings is not spending.** `TRASPASO A CUENTA AHORRO` in checking matches `TRASPASO DESDE CUENTA CORRIENTE` in savings.
8. **A month with no salary.** August's salary arrived on 01/09/2026, so August shows none and September shows two.
9. **An unlabelled bonus.** June's salary is 4721.36 against the usual 2950.14. Nothing in the text says why.
10. **One-off money in.** A gift of 5000.00 from a parent on 18/05/2026, moved to savings two days later, and a tax refund of 384.20 in June. Is either "income"?
11. **Irregular saving.** No transfer to savings in April or August, 700.00 in June, 400.00 otherwise.
12. **A partner's contribution with vague notes.** `BIZUM DE LUCIA M.` most months, none in February, 310.00 in May labelled "lo del finde + boda", and one with no note at all.
13. **A refund.** A dress deposit of 450.00 in April comes back in May, and a different shop is paid 520.00.
14. **A foreign currency charge.** Flights charged as 642.18 EUR (698.00 USD), plus a separate 9.63 conversion fee that the budget does not count.
15. **Lumpy and changing bills.** Car insurance once a year in March; the gym stops after May.
16. **Unpaid card spending.** September's card total has not been billed yet, so it is owed but appears in no bank file.
17. **Wedding payments from three places.** Venue and photographer from checking, catering from savings, the rest on the card.

Budget against bank (these are what verification should catch):

18. **The venue deposit does not match.** The budget says 3.000 paid; the bank shows 3500.00 on 12/03/2026.
19. **A payment the budget does not know about.** 120.00 to the florist on the card in June; the budget shows no flower deposit.
20. **A stale total.** The budget's own rows add up to about 33174, but the typed total says 31.500.
21. **Amounts that are not numbers.** `110 x 95 pax`, `~900`, `1.200-1.500`, `600 (x2)`, `1.800,00 €`.
22. **Dates that are not dates.** `TBC`, `May 2027`, `April?`, and one cell with two instalments.
23. **Missing things.** No vendor for music or the suit, no due date for the honeymoon balance, and nothing anywhere about how much the partner will pay in total.
