# API Gateway Architecture

The API gateway is the single ingress point for all external traffic. Nothing
reaches a backend service without passing through it first, which makes it the
most load-bearing component in the system and the one with the strictest
change process.

## Routing

The API gateway matches an incoming request against a route table and forwards
it to the owning service. Routes are matched longest-prefix-first, so a more
specific route always wins over a general one regardless of declaration order.

Route changes take effect within thirty seconds of a configuration reload. No
restart is required and no connection is dropped during a reload; in-flight
requests finish against the old table while new requests use the new one.

A route that points at a service with no healthy instances returns 503 rather
than queueing. Queueing at the edge turns a backend outage into an edge
outage, because the queue eventually exhausts connection slots that every other
route also needs.

Wildcard routes are supported and discouraged. They make the route table
shorter and they make it impossible to tell, from the table alone, which
service will actually receive a given path.

## Rate Limiting

Every route carries a rate limit expressed in requests per minute per client.
Exceeding it returns a 429 with a `Retry-After` header set to the number of
seconds remaining in the current window.

Limits are enforced per instance rather than globally, so the effective ceiling
is the per-instance limit multiplied by the instance count. Size limits with
that multiplication in mind. A limit of 100 across ten instances is a limit of
1000 in practice, and teams are regularly surprised by this.

Rate limit state is held in memory and is lost when an instance restarts. A
rolling restart therefore briefly raises the effective ceiling. This is
accepted rather than fixed, because the alternative is a shared store on the
hot path of every single request.

## Authentication

The gateway validates the bearer token on every request and rejects anything
expired or malformed before it costs a backend service any work. Validation
happens at the edge specifically so that an invalid-token flood is absorbed
here rather than amplified across every downstream service.

Token validation results are cached for sixty seconds. A revoked token
therefore remains usable for up to a minute. This window is a deliberate
trade-off against validating every request against the identity provider, and
it is documented here because it surprises people during security reviews.

Service-to-service calls inside the cluster do not traverse the gateway and use
mutual TLS instead. The gateway is an ingress concern, not a service mesh.

## Timeouts

The default upstream timeout is thirty seconds. Services that need longer must
request an override per route rather than raising the global default.

Client-side timeouts should always be shorter than the gateway's upstream
timeout for the same route. When the client gives up first, the gateway is left
holding a connection for a response nobody will read, and under load those
abandoned connections are what actually exhausts the instance.

## Observability

Every request is logged with its route, upstream service, status code, and
total latency. Logs are sampled at ten percent for 2xx responses and retained
in full for everything else.

Latency is reported as the time from first byte in to last byte out, which
includes upstream time. A latency spike visible here is not evidence that the
gateway is slow; it is usually evidence that something behind it is.
