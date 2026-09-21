# Engineering Onboarding

Welcome to the platform team. This page is the first thing you should read, and
it links out to the runbooks you will need in your first month. It is written
for someone who has never worked in this codebase before, so it explains things
that will feel obvious by week three.

## Getting Access

Your manager files an access request on your first day. You need three things
before you can ship anything: a GitHub account added to the `platform` org, a
VPN certificate, and a PagerDuty login.

Access requests are reviewed twice a day, at 10:00 and 16:00. If yours is still
pending after a full business day, ping the platform channel rather than filing
a second request. Duplicate requests are closed unread and put you back at the
end of the queue.

The VPN certificate expires every ninety days. Renewal is self-service, but it
is not automatic, and an expired certificate looks exactly like a network
outage from the inside. When something stops resolving for no apparent reason,
check the certificate before you check anything else.

PagerDuty access is read-only until you complete on-call training. You will be
able to see incidents and follow along during your first month without being
able to acknowledge or resolve them, which is deliberate.

## Deployment Basics

Every service ships through the deployment pipeline. You do not deploy by hand,
and you do not merge straight to the production branch. There are no exceptions
to this, including for one-line changes and including during incidents.

The deployment pipeline runs four stages in order: build, test, canary, and
full rollout. A failing stage halts the pipeline and leaves the previous
release serving traffic. Nothing is ever half-deployed, and there is no state
in which some instances run new code and others run old code for longer than
the canary window.

The build stage compiles the service and produces a container image tagged with
the commit SHA. Images are immutable. If you need to change what ships, you
push a new commit; you never retag an existing image. This is what makes a
rollback a lookup rather than a rebuild.

The test stage runs unit and integration suites against the built image, not
against the source tree. Running against the image is slower, and it is the
only way to catch a dependency that exists on a developer machine but not in
the container.

Canary holds new code at five percent of traffic for fifteen minutes while the
alerting system watches error rates. If the alerting system fires during the
canary window, the pipeline rolls back on its own and posts to the platform
channel. Nobody has to be watching for this to work, which is the entire point
of the canary stage.

Full rollout replaces the remaining instances in batches of twenty percent,
pausing sixty seconds between batches. The pause exists so that a failure that
only appears under full production load still has a chance to trip the alerting
system before every instance is running the new code.

Read [the incident response runbook](incident-response.md) before your first
on-call shift. It explains what happens when a rollback is not enough.

## Your First Week

Pick a starter issue labelled `good-first-issue`. Ship it through the full
deployment pipeline end to end, even though it is small. The point is to see
every stage run once while someone is sitting next to you, so that the first
time you watch the pipeline is not during an incident.

Pair with your onboarding buddy for the first review. Code review here is
blocking and is expected to take a day, not an hour. A review that comes back
in ten minutes usually means the reviewer skimmed it.

Do not spend your first week reading the entire codebase. Read the service you
are shipping to, read its tests, and read the runbook for the alert it owns.
Breadth comes later and comes faster once you have shipped something.

## Where Things Live

Service code lives in the `platform` org, one repository per service. There is
no monorepo, and attempts to create one have been abandoned twice.

Infrastructure is defined in the `infra` repository as Terraform modules.
Changes there go through the same deployment pipeline as service code, with an
additional manual approval gate before the apply step.

The API gateway configuration is the one exception: it lives in its own
repository because its release cadence is different from everything else and
because a bad gateway config affects every service at once rather than one.

Documentation lives next to the code it describes. A runbook that lives in a
wiki drifts from reality within two quarters; a runbook in the repository at
least shows up in the diff when the behaviour it documents changes.
