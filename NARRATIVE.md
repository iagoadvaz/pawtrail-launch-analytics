# PawTrail Launch Health — 30-Day Narrative

## Verdict

The launch is not healthy on the metric that matters most: activation. Volume
and attach rate have grown steadily and predictably — cumulative subscriptions
rose from 22 to 3,000 and attach rate from 0.1% to 20% across the
seventeen-week window, finishing at **1.33x the 15% launch target** — but the
mature-cohort 30-day activation rate, which
held between 69.1% and 75.2% for eight straight weeks, dropped to 60.3% in the
most recently completed cohort (signup week of March 30). That drop is not
noise; it tracks a specific, worsening fulfillment failure that is consuming a
growing share of volume.

## Root Cause

Ohio's on-time kit delivery rate is 51.4%, against an 86.2% average across the
other eleven states — a 34.8-point gap, and by far the widest of any state
(the next-worst, New Jersey, is at 82.6%). Combined activation requires an
on-time kit, not merely a delivered one, so Ohio accounts activate at roughly
half the rate of accounts anywhere else. The problem compounds because Ohio's
share of new subscriptions has grown fastest of any state: its weekly attach
rate rose from under 1% in early January to 23.3% in the week of March 30 —
the same cohort where the headline activation rate fell. The state with the
worst fulfillment is now carrying a disproportionate and rising share of the
blended activation number.

## Recommendation: Next 30 Days

Escalate the Ohio carrier/fulfillment issue before scaling marketing spend
further into that state. The at-risk queue (`control_at_risk_by_driver.csv`)
currently holds 944 accounts: 496 flagged for digital-leg failure, 352 for
physical-leg failure, and 96 for both legs failed. Customer Success should
prioritize the 448 accounts with a physical-leg failure (352 + 96) — the
segment mechanically linked to the kit-delivery problem — and expect a
disproportionate share to carry Ohio addresses. Acquisition efficiency needs
watching rather than leaving alone: cost per activated account has nearly
tripled in both channels since the March 2 cohort, from $4.64 to $13.07 for
self-serve and from $12.65 to $37.73 for sales-assisted. Raw CAC rose 2.3x over
that stretch while cost per *activated* account rose 2.8x — acquisition got
more expensive and the accounts it bought activated less often, which is the
Ohio failure surfacing in the unit economics. The gap between the two channels
is not itself the story: sales-assisted costs 2.9x self-serve per activated
account, inside its 2.7-4.7x range since February. The growth lever to pull
this month is still fixing Ohio fulfillment — it is also the cheapest way to
bring cost per activated account back down, because it works on the
denominator rather than the spend.

## What This Memo Does Not Measure

Seven metrics from the spec are deliberately absent, not overlooked.
Twelve-month churn, net revenue retention, LTV, and LTV:CAC all require
observing accounts through a full year of renewal and expansion behavior; the
oldest cohort here is seventeen weeks old, so any such figure today would be
extrapolated rather than observed, and is excluded rather than estimated. Rule
of 40, Magic Number, and Quick Ratio are mature-stage operating metrics that
need multiple quarters of comparable expansion, sales-efficiency, and
cash-flow data to mean anything; a single-quarter launch cohort cannot support
them without producing a number that looks precise but isn't. All seven become
reportable as the cohort base matures — none is skipped for convenience.

## How These Numbers Are Counted

Four choices affect every rate above. First, activation rates use the mature
cohort only: an account must have had the full 7/10/30-day window to be
counted, so recent signups are excluded rather than scored as failures — this
is why the 30-day rate covers far fewer accounts (136 in the March 30 cohort)
than total subscribers that week, and why the four most recent weeks show no
30-day rate at all. Second, "activated" requires an on-time kit, not merely a
delivered one: because kits arrive within 30 days in nearly every state, a
delivered-within-30-days rule would let Ohio score as fully activated and hide
the exact problem this memo identifies. Third, cost per activated account
divides a week's spend by the activation rate of that week's mature accounts
applied to everyone it acquired, not by the mature activated count alone.
Spend is booked for the whole cohort the week it lands, so dividing it by only
the accounts that have finished their window would compare a complete
numerator against a partial one and overstate cost in exactly the newest
weeks: the March 30 cohort reads $13.07 for self-serve on that basis and
$16.60 on the naive one. The four most recent weeks have no mature accounts at
all, so they carry no figure rather than a guessed one.

Fourth, the time-to-milestone averages — days to first login and days to kit
delivery — are held to the same 30-day cohort and capped at 30 days. Without
the gate an account five days old can only contribute a value of five or less,
because its slower outcome has not happened yet and enters the average as a
null; the newest weeks then report only their fastest cases and read faster
than they are. The cap costs almost nothing (twelve kits in the whole dataset
arrive after day 30) and is what keeps events dated past the observation
cutoff out of the average entirely. Like the activation rates, these two
columns are blank for the four most recent weeks.
