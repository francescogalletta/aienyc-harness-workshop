#!/usr/bin/env python3
"""Seeded generator for the wedding example's account files (SPEC 9.8).

Everything here is invented. It writes three account files and a facilitator
key beside this script:

    python examples/wedding/data/.generate.py            # rewrite the files and the key
    python examples/wedding/data/.generate.py --out DIR  # write them somewhere else

The file and the key start with a dot on purpose: every other file in this
folder is an account file, and `data add` loads them all in example mode.
The same seed gives byte-identical files. Standard library only.

The story: the person takes home 10,000 a month, says they spend "about 5,000"
and have "10,000 saved". Their accounts say otherwise: autumn spending is
higher than the summer's, and the savings account holds a little less.
"""
from __future__ import annotations

import argparse
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 20270115
START = date(2026, 7, 1)
END = date(2027, 1, 14)             # the scenarios use today = 2027-01-15; January is not a full month
FIRST_PLANTED = "2026-10"
LAST_PLANTED = "2026-12"

SALARY = 1_000_000                  # cents
RENT = 185_000
TO_SAVINGS = 90_000
SAVINGS_OPENING = 408_900           # balance before the first savings row
CHECKING_OPENING = 420_000
SAVINGS_WITHDRAWAL = (date(2026, 8, 20), 120_000)

HERE = Path(__file__).resolve().parent


# --------------------------------------------------------------- formatting

def plain_amount(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    return f"{sign}{whole}.{frac:02d}"


def es_amount(cents: int) -> str:
    """1.150,00 style: dot for thousands, comma for decimals."""
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    return f"{sign}{whole:,}".replace(",", ".") + f",{frac:02d}"


def es_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def next_weekday(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def prev_weekday(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def month_list():
    d = START.replace(day=1)
    while d <= END:
        yield d.year, d.month
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)


# ------------------------------------------------------------- credit card
# A row is (date, description, cents). On the card a charge is a positive
# number in the file; here it is kept as money out, negative, like every
# other account, and written the card's way at the end.

GROCERIES = ["MERCADONA", "Mercadona S.A.", "MERCADONA 2231 MADRID", "CARREFOUR EXPRESS", "LIDL", "ALDI MADRID"]
RESTAURANTS = ["BAR LA ESQUINA", "TABERNA EL SUR", "SUSHI KO", "PIZZERIA NAPOLI", "CAFE COMERCIAL", "GLOVO*PEDIDO"]
TRANSPORT = ["RENFE VIAJEROS", "CRTM RECARGA", "CABIFY", "REPSOL EST. SERV."]
SHOPPING = ["AMAZON.ES*MK1", "ZARA", "DECATHLON", "FNAC", "EL CORTE INGLES"]
OTHER = ["FARMACIA LDA. RUIZ", "CINES RENOIR", "PELUQUERIA NUEVA"]

# Autumn costs more than summer. These lumps are what lifts October to December.
CARD_LUMPS = [
    (date(2026, 10, 3), "EL CORTE INGLES", 31_230),
    (date(2026, 10, 17), "ZARA", 14_755),
    (date(2026, 10, 24), "IBERIA LINEAS AEREAS", 22_640),
    (date(2026, 11, 7), "AMAZON.ES*MK1", 25_680),
    (date(2026, 11, 14), "FNAC", 18_900),
    (date(2026, 11, 28), "CASA RURAL EL MOLINO", 21_500),
    (date(2026, 12, 5), "EL CORTE INGLES", 41_345),
    (date(2026, 12, 12), "AMAZON.ES*MK1", 19_820),
    (date(2026, 12, 19), "RENFE VIAJEROS", 14_510),
    (date(2026, 12, 23), "RESTAURANTE LA TERRAZA", 13_800),
]
CARD_REFUND = (date(2026, 11, 20), "ZARA - REFUND", 6_490)       # money in, on the card


def build_card(rng: random.Random):
    rows = []
    for y, m in month_list():
        rows.append((date(y, m, 1), "NETFLIX.COM", -1_299))
        rows.append((date(y, m, 14), "SPOTIFY", -1_099))
        rows.append((date(y, m, 9), "GIMNASIO VIVA", -3_990))
    d = START
    while d <= END:
        week = [d + timedelta(days=i) for i in range(7) if d + timedelta(days=i) <= END]
        for _ in range(rng.choice([1, 2, 2])):
            rows.append((rng.choice(week), rng.choice(GROCERIES), -rng.randint(4_800, 14_700)))
        for _ in range(rng.choice([1, 1, 2])):
            rows.append((rng.choice(week), rng.choice(RESTAURANTS), -rng.randint(2_700, 10_350)))
        for _ in range(rng.choice([1, 2, 3])):
            rows.append((rng.choice(week), rng.choice(TRANSPORT), -rng.randint(390, 5_700)))
        if rng.random() < 0.30:
            rows.append((rng.choice(week), rng.choice(SHOPPING), -rng.randint(2_250, 13_500)))
        if rng.random() < 0.30:
            rows.append((rng.choice(week), rng.choice(OTHER), -rng.randint(900, 6_750)))
        d += timedelta(days=7)
    rows += [(d, desc, -cents) for d, desc, cents in CARD_LUMPS]
    rows.append((CARD_REFUND[0], CARD_REFUND[1], CARD_REFUND[2]))
    rows.sort(key=lambda r: r[0])           # stable: same-day rows keep their order
    return rows


def card_charges_by_month(card_rows):
    totals = {}
    for d, _desc, cents in card_rows:
        totals[(d.year, d.month)] = totals.get((d.year, d.month), 0) - cents     # a refund lowers the bill
    return totals


# ---------------------------------------------------------------- checking

ELECTRICITY = {(2026, 7): 8_840, (2026, 8): 9_115, (2026, 9): 7_630, (2026, 10): 10_425,
               (2026, 11): 13_180, (2026, 12): 14_860, (2027, 1): 15_235}
JUNE_CARD_BILL = 154_880            # paid on 6 July for June, which is not in the card file


def build_checking(rng: random.Random, card_totals):
    """Returns (rows, own) where own tags a row that is half of a move between the person's own accounts."""
    tx = []                          # (date, description, cents, own)
    for y, m in month_list():
        tx.append((next_weekday(date(y, m, 1)), "STANDING ORDER RENT CASTELLANA HOMES", -RENT, False))
        tx.append((next_weekday(date(y, m, 2)), "TRANSFER TO SAVINGS", -TO_SAVINGS, True))
        tx.append((next_weekday(date(y, m, 5)), "CARD BILL ****4471",
                   -(JUNE_CARD_BILL if (y, m) == (2026, 7) else card_totals[(y, m - 1) if m > 1 else (y - 1, 12)]), True))
        tx.append((next_weekday(date(y, m, 8)), "DIRECT DEBIT HEALTH INSURANCE SANITAS", -8_650, False))
        tx.append((next_weekday(date(y, m, rng.randint(10, 13))), "DIRECT DEBIT ELECTRICITY ENERGIA XXI",
                   -ELECTRICITY[(y, m)], False))
        tx.append((next_weekday(date(y, m, 16)), "DIRECT DEBIT FIBRE + MOBILE DIGI", -4_290, False))
        tx.append((next_weekday(date(y, m, 20)), "DIRECT DEBIT CAR LOAN SANTANDER CONSUMER", -42_000, False))
        tx.append((next_weekday(date(y, m, 21)), "DIRECT DEBIT CAR INSURANCE MUTUA", -6_240, False))
        if date(y, m, 27) <= END:
            tx.append((prev_weekday(date(y, m, 27)), "PAYROLL ACME SOLUTIONS LTD", SALARY, False))
        for _ in range(2):
            tx.append((date(y, m, rng.randint(1, 13)), "ATM WITHDRAWAL", -rng.choice([6_000, 10_000, 15_000]), False))
        for _ in range(rng.choice([5, 6, 7])):
            shop = rng.choice(["MERCADONA", "Mercadona S.A.", "MERCADONA 2231 MADRID", "PANADERIA LA TAHONA",
                               "FRUTERIA HNOS. GIL", "ALDI MADRID"])
            tx.append((date(y, m, rng.randint(1, 13)), f"CARD PURCHASE {shop}", -rng.randint(1_450, 9_200), False))
    tx.append((SAVINGS_WITHDRAWAL[0], "TRANSFER FROM SAVINGS", SAVINGS_WITHDRAWAL[1], True))
    tx += [
        (date(2026, 7, 4), "BIZUM TO MARTA F. - dinner", -8_000, False),
        (date(2026, 9, 12), "BIZUM TO PABLO G. - padel", -1_200, False),
        (date(2026, 11, 3), "BIZUM TO PABLO G. - padel", -1_200, False),
        (date(2026, 12, 9), "BIZUM TO MARTA F. - gift", -4_500, False),
    ]
    tx = [row for row in tx if row[0] <= END]
    tx.sort(key=lambda r: r[0])
    return tx


def with_balance(tx, opening):
    out, bal = [], opening
    for row in tx:
        bal += row[2]
        out.append((*row[:3], bal, *row[4:]))
    return out


BANK_HEADER = "Date;Description;Amount;Balance"


def bank_lines(rows):
    """Bank export body: newest first, semicolons, 1.234,56."""
    return [f"{es_date(d)};{desc};{es_amount(cents)};{es_amount(bal)}" for d, desc, cents, bal, *_ in reversed(rows)]


def write_checking(rows, path: Path):
    """Two exports pasted into one file, the way people really do it.

    The later export sits on top, then the earlier one. The heading row appears
    twice and every row dated on the cut appears in both halves, with the same
    balance, which is how a repeat is told from a real second payment.
    """
    autumn = [d for d, *_ in rows if date(2026, 10, 1) <= d <= date(2026, 10, 31)]
    cut = max(sorted(set(autumn)), key=autumn.count)       # the busiest day of October: the most repeats
    later = [r for r in rows if r[0] >= cut]
    earlier = [r for r in rows if r[0] <= cut]
    lines = [BANK_HEADER, *bank_lines(later), BANK_HEADER, *bank_lines(earlier)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return cut, lines


# ----------------------------------------------------------------- savings

def build_savings(checking_tx):
    tx = []
    for d, desc, cents, _own in checking_tx:
        if desc == "TRANSFER TO SAVINGS":
            tx.append((d, "TRANSFER FROM CHECKING", -cents, True))
    tx.append((SAVINGS_WITHDRAWAL[0], "TRANSFER TO CHECKING", -SAVINGS_WITHDRAWAL[1], True))
    tx += [
        (date(2026, 6, 30), "INTEREST", 1_184, False),
        (date(2026, 9, 30), "INTEREST", 1_422, False),
        (date(2026, 12, 31), "INTEREST", 1_507, False),
    ]
    tx.sort(key=lambda r: r[0])
    return tx


def write_savings(rows, path: Path):
    lines = ["Date,Description,Amount,Balance"]
    lines += [f"{d.isoformat()},{desc},{plain_amount(cents)},{plain_amount(bal)}" for d, desc, cents, bal, *_ in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_card(card_rows, card_bill_rows, path: Path):
    """The card's way: charges are positive, a payment or refund is negative, oldest first, no balance."""
    rows = sorted(card_rows + card_bill_rows, key=lambda r: r[0])
    lines = ["Transaction Date,Merchant,Amount,Currency"]
    lines += [f"{d.isoformat()},{desc},{plain_amount(-cents)},EUR" for d, desc, cents in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ----------------------------------------------------------- independent figures

def months_between(first: str, last: str):
    y, m = int(first[:4]), int(first[5:])
    while f"{y:04d}-{m:02d}" <= last:
        yield f"{y:04d}-{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def figures(accounts):
    """accounts: {name: [(date, desc, cents, own)]}, money out negative. Worked out from the rows as built."""
    by_month = {}
    for rows in accounts.values():
        for d, _desc, cents, own, *_ in rows:
            if own:
                continue
            key = f"{d.year:04d}-{d.month:02d}"
            money_in, money_out = by_month.get(key, (0, 0))
            by_month[key] = (money_in + max(cents, 0), money_out - min(cents, 0))
    return by_month


def money(cents) -> str:
    return plain_amount(round(cents))


def average(by_month, which, months):
    return sum(by_month[month][which] for month in months) / len(months)


# ---------------------------------------------------------- facilitator key

def facilitator_key(checking, savings, n_card, last_card, by_month, cut, claims) -> str:
    planted = [f"{FIRST_PLANTED[:4]}-{m}" for m in ("10", "11", "12")]
    summer = ["2026-07", "2026-08", "2026-09"]
    lines_by_month = "\n".join(
        f"| {month} | {money(by_month[month][0])} | {money(by_month[month][1])} |" for month in sorted(by_month)
        if "2026-07" <= month <= LAST_PLANTED)
    return f"""\
# Facilitator key: what is planted in the wedding example's account files

Written by `examples/wedding/data/.generate.py` (seed {SEED}). Everything is invented. Remove this file from any copy you
hand to attendees if you want them to find these for themselves. It and the script start with a dot so that
`data add` does not read them as accounts.

The story: the person takes home 10,000 a month, says they spend "about 5,000" a month and have "10,000 saved". The scenarios
use `today` 2027-01-15, so the last three full months are {planted[0]}, {planted[1]} and {planted[2]}.

| File | Account | Format |
| --- | --- | --- |
| `checking.csv` | `checking` | Semicolons, `DD/MM/YYYY`, `1.234,56`, newest first, a balance column, money out is negative |
| `savings.csv` | `savings` | Commas, `YYYY-MM-DD`, `1234.56`, oldest first, a balance column, money out is negative |
| `credit_card.csv` | `credit_card` | Commas, `YYYY-MM-DD`, `1234.56`, oldest first, no balance column, **charges are positive** |

Rows run from {START.isoformat()}; the files end {checking[-1][0].isoformat()} (checking), {savings[-1][0].isoformat()} (savings) and
{last_card} (card). Full months for all three accounts: 2026-07 to 2026-12. January 2027 is partial and is never counted.

## What is planted (and what the harness must compute)

| Figure | Said | Files show |
| --- | --- | --- |
| Money out a month, `all` accounts, last 3 full months ({planted[0]} to {planted[2]}) | about 5,000 | **{claims['out']}** |
| Money out a month, the 3 months before ({summer[0]} to {summer[2]}) | | {claims['out_summer']} |
| Latest balance of `savings` (as of {savings[-1][0].isoformat()}) | 10,000 | **{claims['balance']}** |
| Money in a month, `all` accounts, last 3 full months | 10,000 take-home | **{claims['in']}**, inside the 5% tolerance |

Money in and out by full month, own transfers left out:

| Month | Money in | Money out |
| --- | --- | --- |
{lines_by_month}

Why the figures are what they are:

1. **Spending is higher than said, in the months that count.** Summer months sit near 4,800; October to December carry
   extra card spending (a department store, flights, a weekend away, Christmas). The average over the last three
   months is {claims['out']}, {claims['out_pct']}% above 5,000, so it is outside the 5% tolerance. Over all six months it would be
   {claims['out_six']}, which a 5,000 claim is within 5% of: a verifier that asks for six months finds nothing.
2. **Savings is lower than said.** The latest balance is {claims['balance']}, {claims['balance_pct']}% under 10,000, so it is outside the tolerance.
3. **Pay agrees.** Money in is 10,000.00 of pay each month, plus 64.90 refunded to the card in November and 15.07 of
   interest in December, so {claims['in']} against 10,000. A claim about pay is checked on a clean measure.
4. **Moving money between own accounts is not spending.** The monthly `TRANSFER TO SAVINGS` (900.00) matches
   `TRANSFER FROM CHECKING` in the savings file on the same day, the August withdrawal from savings (1,200.00) matches
   `TRANSFER FROM SAVINGS` in checking, and each `CARD BILL ****4471` in checking matches a negative `PAYMENT` line in the
   card file on the same day. All of them are left out of money in and money out. The card file lists its payments on the
   same day on purpose: loaded without them, the card's charges would count once as charges and again as the bill.
5. **The person keeps the rest in the current account.** Money in 10,000, money out about 5,600: the difference builds up in
   `checking`, whose balance after the last row is {plain_amount(checking[-1][3])}. Only `savings` is the wedding
   fund, so "10,000 saved for the wedding" is checked against it.

## Mess the adapter is specified to handle

6. **Two formats and two sign conventions.** `checking` and `savings` write money out negative; `credit_card` writes a charge
   positive. `checking` uses semicolons, `DD/MM/YYYY` and `1.234,56`; the others use commas, ISO dates and `1234.56`.
7. **A pasted export.** `checking.csv` is two exports in one file: the heading row appears again in the middle, and every
   row dated {es_date(cut)} ({sum(1 for r in checking if r[0] == cut)} of them) appears in both halves with the same balance. Left out by the adapter, as `repeated header` and
   `repeated row`.
8. **Different headings.** `Date`, `Description`, `Amount`, `Balance` on the bank files; `Transaction Date`, `Merchant`,
   `Amount`, `Currency` on the card (the currency column is ignored).
9. **Mixed merchant spellings.** `MERCADONA`, `Mercadona S.A.` and `MERCADONA 2231 MADRID`, on the card and in the debit purchases.
10. **Small things that are not spending.** A refund (`ZARA - REFUND`, 64.90) counts as money in; `INTEREST` on the savings
    account counts as money in.

Nothing here is something the adapter refuses: no separate money in and out columns, no ambiguous dates (days above 12
appear in every file), no amount like `1,150` that could be read two ways.

Counts: checking {len([r for r in checking])} rows after removing repeats, savings {len(savings)}, card {n_card}.
"""


# --------------------------------------------------------------------- main

def generate(out: Path, key_path: Path | None) -> dict:
    rng = random.Random(SEED)
    card_spend = build_card(rng)
    card_totals = card_charges_by_month(card_spend)
    checking_tx = build_checking(rng, card_totals)

    # The card file lists each bill payment, on the day the bank took it.
    card_payments = [(d, "PAYMENT RECEIVED - THANK YOU", -cents) for d, desc, cents, _own in checking_tx
                     if desc.startswith("CARD BILL")]
    checking = with_balance(checking_tx, CHECKING_OPENING)
    savings = with_balance(build_savings(checking_tx), SAVINGS_OPENING)

    out.mkdir(parents=True, exist_ok=True)
    cut, _ = write_checking(checking, out / "checking.csv")
    write_savings(savings, out / "savings.csv")
    # A payment is money in on the card, so positive here and negative in the file, where a charge is positive.
    write_card(card_spend, card_payments, out / "credit_card.csv")

    card_all = [(d, desc, cents, False) for d, desc, cents in card_spend]
    card_all += [(d, desc, cents, True) for d, desc, cents in card_payments]
    by_month = figures({"checking": checking_tx, "savings": build_savings(checking_tx), "credit_card": card_all})
    planted = ["2026-10", "2026-11", "2026-12"]
    six = [f"2026-{m:02d}" for m in range(7, 13)]
    claims = {
        "out": money(average(by_month, 1, planted)),
        "out_summer": money(average(by_month, 1, ["2026-07", "2026-08", "2026-09"])),
        "out_six": money(average(by_month, 1, six)),
        "in": money(average(by_month, 0, planted)),
        "balance": plain_amount(savings[-1][3]),
    }
    claims["out_pct"] = f"{(average(by_month, 1, planted) - 500_000) / 5_000:.1f}"
    claims["balance_pct"] = f"{(1_000_000 - savings[-1][3]) / 10_000:.1f}"
    if key_path is not None:
        key_path.write_text(facilitator_key(checking, savings, len(card_spend) + len(card_payments), max(r[0] for r in card_spend).isoformat(), by_month, cut, claims), encoding="utf-8")
    return claims


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=HERE)
    parser.add_argument("--key", type=Path, default=None,
                        help="where to write the key (default: .FACILITATOR_KEY.md next to --out's files)")
    args = parser.parse_args()
    key = args.key or args.out / ".FACILITATOR_KEY.md"
    claims = generate(args.out, key)
    print(f"wrote the wedding example's data to {args.out}")
    for name, value in claims.items():
        print(f"  {name}: {value}")


if __name__ == "__main__":
    main()
