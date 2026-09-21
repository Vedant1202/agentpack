# Alerting

This document describes how alerts are defined, routed, and tuned. It is the
reference for anyone adding a new alert or trying to work out why an existing
one keeps firing.

## What Gets An Alert

An alert exists to wake someone up. If nobody would act on it at three in the
morning, it belongs on a dashboard instead. This is the single rule that keeps
the pager survivable, and almost every noisy pager rotation traces back to
having ignored it.

Every alert must name the symptom a customer would notice, not the internal
cause. "Checkout error rate above two percent" is an alert. "Queue depth above
ten thousand" is a dashboard panel, because queue depth is only interesting
when it causes something a customer can see.

Symptom-based alerts also survive refactors. An alert defined on internal queue
mechanics breaks the moment someone replaces the queue; an alert defined on
checkout errors keeps working regardless of what is behind it.

Every alert needs a runbook link in its definition. An alert that pages someone
at three in the morning with no runbook is a puzzle, not a signal, and the time
spent solving the puzzle is time customers spend affected.

## Routing

The alerting system routes by service ownership. Each service declares an
owning team, and the alerting system notifies that team's primary on-call
engineer.

Alerts with no declared owner route to the platform team, which is a fallback
and not a destination. An unowned alert is a bug in the service definition, and
the platform team will file it back rather than absorb it.

Escalation is automatic. An unacknowledged page escalates to the secondary
after ten minutes and to the engineering manager after twenty. The alerting
system stops escalating the moment someone acknowledges, which is why
acknowledging early matters even when you have not started investigating.

## Tuning

Review alert noise monthly. An alert that fired more than three times without
anyone taking action should be widened, moved to a dashboard, or deleted. All
three are better than leaving it as it is.

Deleting an alert is a legitimate outcome and needs no special justification
beyond the noise record. Teams tend to treat alert deletion as risky and alert
addition as free, which is backwards: an alert nobody trusts provides no
coverage while still costing sleep.

Silences expire. The alerting system caps a silence at seven days so that a
muted alert cannot quietly stay muted forever. A silence that needs renewing
twice is a signal that the underlying alert needs changing.

Thresholds are reviewed after every incident where the alert fired late or not
at all. This is the only alert change that is expected to come out of a
postmortem; broad "add more alerting" action items are discouraged because they
reliably produce noise that the next rotation has to clean up.
