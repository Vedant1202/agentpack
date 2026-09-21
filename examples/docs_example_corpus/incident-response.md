# Incident Response Runbook

This runbook covers what to do between the moment an alert fires and the moment
the incident is closed. It assumes you are the primary on-call engineer and
that you have never run an incident before.

## Severity Levels

A Sev1 is a total outage or data loss. A Sev2 is a degraded service that
customers can notice. A Sev3 is an internal problem with no customer impact.

Only a Sev1 pages the secondary on-call. Sev2 and Sev3 stay with whoever is
holding the primary pager. If you are unsure between two levels, pick the
higher one and downgrade later. Downgrading a Sev1 costs one message in the
incident channel; upgrading a Sev3 two hours late costs considerably more.

Severity is about customer impact, not about how hard the problem is to fix. A
one-character configuration typo that takes checkout offline is a Sev1. A
memory leak that will exhaust a host in three days is a Sev3, no matter how
alarming the graph looks.

## When An Alert Fires

You are paged by the alerting system. Acknowledge within five
minutes. Acknowledging is not the same as fixing it; it tells the alerting
system to stop escalating while you look at the problem.

Open an incident channel before you start investigating. Every decision goes in
that channel as you make it, not afterwards from memory. The channel is the
timeline you will write the postmortem from, and reconstructing it later always
produces a cleaner story than what actually happened.

Declare yourself incident commander explicitly, in writing. On a quiet incident
this feels like ceremony. On a loud one, where six people have joined and three
are running their own investigations, it is the only thing that keeps two
people from applying conflicting fixes at the same time.

If the alerting system wakes you for something that turns out to be noise,
resolve it and open an issue against the alert definition in the same sitting.
Noise that nobody files against never gets fixed, and the next person on call
inherits it.

## The Deployment Pipeline

Most incidents trace back to a recent release, so the deployment pipeline is
the first place to look. Check what the deployment pipeline shipped in the last
hour before you go anywhere near the application logs. This takes thirty
seconds and resolves a surprising fraction of incidents outright.

If a bad release is the cause, roll it back through the deployment pipeline. Do
not patch forward during an incident. A rollback is reversible and a forward
fix, under time pressure, usually is not. The rollback path is exercised
constantly by the canary stage, so it is the best-tested operation available to
you at three in the morning.

A rollback through the deployment pipeline takes about four minutes end to end.
If you are considering a forward fix because "the rollback will take too long",
check that number against how long your fix will take to write, review, and
ship. It is almost never close.

See [the onboarding guide](onboarding.md) for how the pipeline stages work and
what each one is checking.

When the deployment pipeline itself is the thing that is broken, escalate to
the platform team rather than trying to deploy around it. There is a documented
break-glass procedure, it requires two people, and it is deliberately annoying
enough that nobody reaches for it casually.

## Communicating During An Incident

Post an update every thirty minutes even when there is nothing new. "Still
investigating, no new information" is a useful update; silence is not, because
silence is indistinguishable from nobody working on it.

Write updates for someone who just joined. Avoid internal shorthand and service
code names in customer-facing updates, and state impact in terms of what a
customer cannot currently do.

## Closing An Incident

An incident is closed when customer impact has ended, not when the fix has
merged. Those are frequently hours apart, and conflating them produces
postmortems that understate how long customers were affected.

Write the postmortem within two business days while the incident channel still
reads as a timeline. Postmortems are blameless in the specific sense that they
identify the conditions that made the failure possible rather than the person
who tripped over them.

Every postmortem produces at least one action item with an owner and a date. A
postmortem with no action items means either the incident was genuinely
unpreventable, which is rare, or nobody looked hard enough.
