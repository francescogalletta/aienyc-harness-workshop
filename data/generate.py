#!/usr/bin/env python3
"""Seeded generator for the workshop's example data.

Everything here is invented. It produces the kind of files a person really
has: bank exports in two different formats, and a wedding budget kept by
hand. The mess is deliberate, and every planted quirk is listed in
FACILITATOR_KEY.md, which this script also writes.

    python data/generate.py            # rewrite data/example and the key
    python data/generate.py --out DIR  # write somewhere else

The same seed always gives byte-identical files (tests/data checks this).
Standard library only.
"""
from __future__ import annotations

import argparse
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 20261009
START = date(2026, 1, 1)
END = date(2026, 9, 30)
WEDDING = date(2027, 6, 12)

CHECKING_OPENING = 618_052   # cents, balance before the first row
SAVINGS_OPENING = 620_000
DECEMBER_CARD_BILL = 61_240  # paid in January, for spending not in the files

HERE = Path(__file__).resolve().parent


# --------------------------------------------------------------- formatting

def es_amount(cents: int) -> str:
    """1.150,00 style: dot for thousands, comma for decimals."""
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    return f"{sign}{whole:,}".replace(",", ".") + f",{frac:02d}"


def plain_amount(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    return f"{sign}{whole}.{frac:02d}"


def es_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def months():
    d = START
    while d <= END:
        yield d.year, d.month
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def next_weekday(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def prev_weekday(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


# -------------------------------------------------------------- credit card

GROCERIES = ["MERCADONA", "Mercadona S.A.", "MERCADONA 2231 MADRID",
             "CARREFOUR EXPRESS", "ALDI MADRID", "LIDL"]
RESTAURANTS = ["BAR LA ESQUINA", "TABERNA EL SUR", "SUSHI KO",
               "PIZZERIA NAPOLI", "CAFE COMERCIAL", "GLOVO*PEDIDO"]
TRANSPORT = ["RENFE VIAJEROS", "CRTM RECARGA", "CABIFY", "REPSOL EST. SERV."]
SHOPPING = ["AMAZON.ES*MK1", "ZARA", "DECATHLON", "FNAC", "EL CORTE INGLES"]
OTHER = ["FARMACIA LDA. RUIZ", "CINES RENOIR", "PELUQUERIA NUEVA"]

# (date, description, cents, original amount, original currency)
# The card export shows a charge as a POSITIVE number and a refund as negative.
CARD_FIXED = [
    (date(2026, 2, 14), "BODAS.NET *INVITACIONES", 18_400, "", ""),
    (date(2026, 4, 9), "ATELIER BLANCO NOVIAS", 45_000, "", ""),
    (date(2026, 5, 6), "ATELIER BLANCO NOVIAS - DEVOLUCION", -45_000, "", ""),
    (date(2026, 5, 23), "NOVIAS SAN GINES", 52_000, "", ""),
    (date(2026, 6, 19), "PAYPAL *FLORISTERIAELJARD", 12_000, "", ""),
    (date(2026, 8, 11), "SKYWAYS AIR 0162345 NEW YORK", 64_218, "698.00", "USD"),
    (date(2026, 8, 11), "COMISION CAMBIO DIVISA", 963, "", ""),
    (date(2026, 9, 17), "JOYERIA ARGENTA", 124_000, "", ""),
]


def build_card(rng: random.Random):
    rows = list(CARD_FIXED)
    for y, m in months():
        rows.append((date(y, m, 7), "NETFLIX.COM", 1_299, "", ""))
        rows.append((date(y, m, 14), "SPOTIFY", 1_099, "", ""))
    d = START
    while d <= END:
        week = [d + timedelta(days=i) for i in range(7) if d + timedelta(days=i) <= END]
        for _ in range(rng.choice([1, 2, 2])):
            rows.append((rng.choice(week), rng.choice(GROCERIES), rng.randint(2_500, 9_500), "", ""))
        for _ in range(rng.choice([1, 1, 2])):
            rows.append((rng.choice(week), rng.choice(RESTAURANTS), rng.randint(1_200, 6_200), "", ""))
        for _ in range(rng.choice([1, 2, 3])):
            rows.append((rng.choice(week), rng.choice(TRANSPORT), rng.randint(160, 3_800), "", ""))
        if rng.random() < 0.35:
            rows.append((rng.choice(week), rng.choice(SHOPPING), rng.randint(1_500, 12_000), "", ""))
        if rng.random() < 0.30:
            rows.append((rng.choice(week), rng.choice(OTHER), rng.randint(600, 4_500), "", ""))
        d += timedelta(days=7)
    rows.sort(key=lambda r: r[0])  # stable: same-day rows keep insertion order
    return rows


def card_month_totals(card_rows):
    totals = {}
    for d, _desc, cents, _oa, _oc in card_rows:
        totals[(d.year, d.month)] = totals.get((d.year, d.month), 0) + cents
    return totals


def write_card(card_rows, path: Path):
    lines = ["date,description,amount,currency,original_amount,original_currency"]
    for d, desc, cents, orig_amount, orig_ccy in card_rows:  # oldest first
        lines.append(f"{d.isoformat()},{desc},{plain_amount(cents)},EUR,{orig_amount},{orig_ccy}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ----------------------------------------------------------------- checking

SALARY = 295_014
SALARY_JUNE = 472_136          # includes the summer extra pay, not labelled
SAVINGS_TRANSFER = {1: 40_000, 2: 40_000, 3: 40_000, 4: 0, 5: 40_000,
                    6: 70_000, 7: 40_000, 8: 0, 9: 40_000}
PARTNER_BIZUM = {1: (25_000, "boda"), 3: (25_000, "boda marzo"),
                 4: (25_000, "boda"), 5: (31_000, "lo del finde + boda"),
                 6: (25_000, "boda"), 7: (25_000, "boda jul"),
                 8: (25_000, ""), 9: (25_000, "boda")}   # nothing in February
ELECTRICITY = {1: 9_312, 2: 8_847, 3: 6_120, 4: 5_233, 5: 4_871,
               6: 6_408, 7: 9_154, 8: 9_466, 9: 5_982}


def build_checking(rng: random.Random, card_totals):
    tx = []  # (date, concept, signed cents)

    for y, m in months():
        # Salary: the 28th, or the Friday before. August's arrived late, on 1 Sep.
        if m == 8:
            tx.append((date(2026, 9, 1), "ABONO NOMINA TECNOLOGIAS EJEMPLO SL", SALARY))
        else:
            pay_day = prev_weekday(date(y, m, 28))
            tx.append((pay_day, "ABONO NOMINA TECNOLOGIAS EJEMPLO SL",
                       SALARY_JUNE if m == 6 else SALARY))

        tx.append((next_weekday(date(y, m, 1)), "RECIBO ALQUILER INMOB. CASTELLANA", -115_000))
        if m <= 5:  # gym cancelled after May
            tx.append((next_weekday(date(y, m, 2)), "RECIBO GIMNASIO VIVA", -3_490))
        tx.append((next_weekday(date(y, m, rng.randint(10, 14))), "RECIBO LUZ ENERGIA XXI", -ELECTRICITY[m]))
        tx.append((next_weekday(date(y, m, 16)), "RECIBO FIBRA+MOVIL DIGI", -3_900))

        # Card bill: on the 5th, for the previous month's card spending.
        bill = DECEMBER_CARD_BILL if m == 1 else card_totals[(y, m - 1)]
        tx.append((next_weekday(date(y, m, 5)), "RECIBO TARJETA CREDITO ****4471", -bill))

        if SAVINGS_TRANSFER[m]:
            tx.append((prev_weekday(date(y, m, 29) if m != 2 else date(y, m, 27)),
                       "TRASPASO A CUENTA AHORRO", -SAVINGS_TRANSFER[m]))

        if m in PARTNER_BIZUM:
            cents, note = PARTNER_BIZUM[m]
            concept = "BIZUM DE LUCIA M." + (f" - {note}" if note else "")
            tx.append((date(y, m, rng.randint(3, 8)), concept, cents))

        for _ in range(2):
            tx.append((date(y, m, rng.randint(1, 27)), "REINTEGRO CAJERO", -rng.choice([4_000, 6_000, 10_000])))
        for _ in range(rng.choice([1, 2, 3])):
            shop = rng.choice(["PANADERIA LA TAHONA", "KIOSCO PLAZA", "FRUTERIA HNOS. GIL"])
            tx.append((date(y, m, rng.randint(1, 27)), f"COMPRA TARJ. DEBITO {shop}", -rng.randint(250, 1_900)))

    tx += [
        (date(2026, 3, 3), "RECIBO SEGURO COCHE MUTUA ANUAL", -48_630),
        (date(2026, 3, 12), "TRANSFERENCIA A FINCA LOS OLIVOS SL - RESERVA 12/06/27", -350_000),
        (date(2026, 4, 22), "TRANSF. A ESTUDIO LUZ - SEÑAL FOTOS", -60_000),
        (date(2026, 5, 18), "TRANSFERENCIA DE M CARMEN R. - PARA LA BODA", 500_000),
        (date(2026, 5, 20), "TRASPASO A CUENTA AHORRO", -500_000),
        (date(2026, 6, 16), "AEAT DEVOLUCION RENTA 2025", 38_420),
        (date(2026, 6, 30), "COMPRA TARJ. DEBITO FARMACIA LDA. RUIZ", -1_265),
        (date(2026, 6, 30), "REINTEGRO CAJERO", -6_000),
        (date(2026, 2, 21), "BIZUM A PABLO G. - cena", -2_350),
        (date(2026, 4, 11), "BIZUM DE ANA - regalo carlos", 1_500),
        (date(2026, 7, 4), "BIZUM A MARTA F. - despedida", -8_000),
        (date(2026, 9, 12), "BIZUM A PABLO G. - padel", -1_200),
    ]
    tx.sort(key=lambda r: r[0])
    return tx


def with_balance(tx, opening):
    out, bal = [], opening
    for d, concept, cents in tx:
        bal += cents
        out.append((d, concept, cents, bal))
    return out


def bank_lines(rows):
    """Bank export body: newest first, semicolons, Spanish number format."""
    return [f"{es_date(d)};{concept};{es_amount(cents)};{es_amount(bal)}"
            for d, concept, cents, bal in reversed(rows)]


BANK_HEADER = "Fecha;Concepto;Importe;Saldo"


def write_checking(rows, path: Path):
    """Two exports pasted into one file, the way people really do it.

    The later export (30 Jun to 30 Sep) sits on top, then the earlier one
    (1 Jan to 30 Jun). The header appears twice and every row dated 30 June
    appears in both halves.
    """
    cut = date(2026, 6, 30)
    later = [r for r in rows if r[0] >= cut]
    earlier = [r for r in rows if r[0] <= cut]
    lines = [BANK_HEADER, *bank_lines(later), BANK_HEADER, *bank_lines(earlier)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ savings

def build_savings(checking_tx):
    tx = [(d, "TRASPASO DESDE CUENTA CORRIENTE", -cents)
          for d, concept, cents in checking_tx if concept == "TRASPASO A CUENTA AHORRO"]
    tx += [
        (date(2026, 3, 31), "LIQUIDACION INTERESES", 1_142),
        (date(2026, 6, 30), "LIQUIDACION INTERESES", 1_987),
        (date(2026, 7, 8), "TRANSFERENCIA A CATERING LA MESA SL - SEÑAL", -100_000),
        (date(2026, 9, 30), "LIQUIDACION INTERESES", 2_210),
    ]
    tx.sort(key=lambda r: r[0])
    return tx


def write_savings(rows, path: Path):
    path.write_text("\n".join([BANK_HEADER, *bank_lines(rows)]) + "\n", encoding="utf-8")


# ----------------------------------------------------------- wedding budget

# Typed by hand in a spreadsheet and saved as CSV. Left exactly as a person
# would leave it: mixed number and date formats, guesses, gaps, a stale total.
BUDGET_CSV = """\
Item,Vendor,Estimate,Deposit paid,Remaining,Due,Notes
Venue,Finca Los Olivos,9.500,3.000,6.500,12/05/2027,rest one month before
Catering,Catering La Mesa,110 x 95 pax,1000 (paid Jul),,"50% 01/03/2027, rest 05/06/2027",depends on final guest count
Photographer,Estudio Luz,"1.800,00 €",600,1200,2027-06-12,balance on the day
Music / DJ,,~900,,,TBC,still need a quote
Flowers,Floristería El Jardín,1.200-1.500,,,May 2027,
Dress,Novias San Ginés,1.900,520,1380,15/02/2027,first shop refunded the deposit
Suit,,650,,,April?,
Rings,Joyería Argenta,1240,1240,0,,paid Sept
Invitations,bodas.net,184,184,0,,
Honeymoon,,4.000,"642,18",,flights: rest 3 months before,hotel not booked yet
Guest buses,,600 (x2),,,01/06/2027,two buses
,,,,,,
TOTAL,,31.500,,,,
"""


# ---------------------------------------------------------- facilitator key

def facilitator_key(card_rows, card_totals, checking, savings) -> str:
    sept_card = card_totals[(2026, 9)]
    return f"""\
# Facilitator key: what is planted in the example data

This older example data was made before the brief existed and does not match the wedding story; it is kept as the source adapter's test fixture, which the tests read (the wedding example's own account files and key are in `examples/wedding/data/`).

Written by `data/generate.py` (seed {SEED}). Everything is invented.
Remove this file from any copy you hand to attendees if you want them to
find these for themselves.

The story: one person's accounts from {START.isoformat()} to {END.isoformat()},
and a wedding on {WEDDING.isoformat()} that is partly paid for.

| File | What it is | Format |
| --- | --- | --- |
| `checking_2026.csv` | Main current account | Semicolons, `dd/mm/yyyy`, `1.150,00`, newest first, money out is negative |
| `savings_2026.csv` | Savings account | Same as checking |
| `card_2026.csv` | Credit card | Commas, ISO dates, `1150.00`, oldest first, **charges are positive** |
| `wedding_budget.csv` | Budget kept by hand | Whatever the person typed |

## Reference figures

| Figure | Value |
| --- | --- |
| Checking balance before the first row | {plain_amount(CHECKING_OPENING)} |
| Checking balance after the last row | {plain_amount(checking[-1][3])} |
| Savings balance before the first row | {plain_amount(SAVINGS_OPENING)} |
| Savings balance after the last row | {plain_amount(savings[-1][3])} |
| Real checking transactions (after removing repeats) | {len(checking)} |
| Card transactions | {len(card_rows)} |
| September card spending, not yet billed | {plain_amount(sept_card)} |
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

6. **Paying the card is not spending.** Each `RECIBO TARJETA CREDITO` in checking equals the previous month's card total. Counting both doubles the spending. January's bill ({plain_amount(DECEMBER_CARD_BILL)}) is for December, which is not in the card file.
7. **Moving money to savings is not spending.** `TRASPASO A CUENTA AHORRO` in checking matches `TRASPASO DESDE CUENTA CORRIENTE` in savings.
8. **A month with no salary.** August's salary arrived on 01/09/2026, so August shows none and September shows two.
9. **An unlabelled bonus.** June's salary is {plain_amount(SALARY_JUNE)} against the usual {plain_amount(SALARY)}. Nothing in the text says why.
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
"""


# --------------------------------------------------------------------- main

def generate(out: Path, key_path: Path | None) -> None:
    rng = random.Random(SEED)
    card_rows = build_card(rng)
    totals = card_month_totals(card_rows)
    checking_tx = build_checking(rng, totals)
    checking = with_balance(checking_tx, CHECKING_OPENING)
    savings = with_balance(build_savings(checking_tx), SAVINGS_OPENING)

    out.mkdir(parents=True, exist_ok=True)
    write_card(card_rows, out / "card_2026.csv")
    write_checking(checking, out / "checking_2026.csv")
    write_savings(savings, out / "savings_2026.csv")
    (out / "wedding_budget.csv").write_text(BUDGET_CSV, encoding="utf-8")
    if key_path is not None:
        key_path.write_text(facilitator_key(card_rows, totals, checking, savings), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=HERE / "example")
    parser.add_argument("--key", type=Path, default=None,
                        help="where to write the facilitator key (default: next to this script, "
                             "only when --out is the default)")
    args = parser.parse_args()
    key = args.key
    if key is None and args.out == HERE / "example":
        key = HERE / "FACILITATOR_KEY.md"
    generate(args.out, key)
    print(f"wrote example data to {args.out}")


if __name__ == "__main__":
    main()
