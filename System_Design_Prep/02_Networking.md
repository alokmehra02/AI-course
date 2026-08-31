# Module 02 — Networking: DNS, HTTP, TCP/UDP, WebSockets

> **What this module makes you able to do:** explain what happens between a user typing a
> URL and your handler running, choose a transport for real-time features and defend it,
> and say why DNS failover takes twenty minutes when the TTL says sixty seconds.
>
> **Interview weight:** ★★★★☆ (asked directly in most backend interviews, and implicitly
> in every design question that touches latency, caching or real time)
>
> **Prerequisites:** [Module 01 — Requirements & NFRs](./01_Requirements_And_NFRs.md)

---

## Contents

| # | Topic | Interview weight |
|---|-------|------------------|
| 2.1 | The stack — the practical parts only | ★★★☆☆ |
| 2.2 | DNS — resolution, records, TTL, anycast, failover | ★★★★★ |
| 2.3 | TCP — handshake, congestion control, connection cost | ★★★★☆ |
| 2.4 | UDP — and QUIC as the modern answer | ★★★☆☆ |
| 2.5 | TLS / HTTPS — handshake cost, termination, mTLS | ★★★★☆ |
| 2.6 | HTTP/1.1 vs HTTP/2 vs HTTP/3 | ★★★★☆ |
| 2.7 | HTTP semantics for design — methods, codes, headers | ★★★★★ |
| 2.8 | WebSockets — and the scaling problem | ★★★★★ |
| 2.9 | Polling vs long polling vs SSE vs WebSockets | ★★★★★ |
| 2.10 | Real-time at scale — fan-out in production | ★★★★☆ |

---

## 2.1 The stack — the practical parts only

> **One-liner:** You need four layers, not seven: IP moves packets, TCP or UDP moves
> streams or datagrams, TLS encrypts, and HTTP carries meaning — and the only OSI question
> that ever matters in an interview is L4 versus L7 load balancing.

### Say this in the interview

> I think about four layers in practice. IP at layer three gets a packet to a host and is
> where anycast and BGP live. TCP or UDP at layer four gets it to a port, and that's the
> layer a network load balancer operates at — it forwards a connection without ever
> looking inside it, so it's fast and protocol-agnostic but it can't route on a URL path.
> TLS sits above that and encrypts the byte stream. HTTP at layer seven is where the
> request has meaning — a method, a path, headers — and that's what an application load
> balancer reads so it can route `/api` to one target group and `/static` to another,
> terminate TLS, and add a request ID. The practical consequence I care about is that once
> you terminate TLS at layer seven you can cache, rewrite and inspect, but you've also
> made the load balancer a trust boundary and a CPU cost centre. For raw TCP services like
> a database proxy or a game server, layer four is the right answer.

### Mental model

```text
   Layer   What it does            Where you meet it
  ┌──────┬────────────────────────┬──────────────────────────────────────┐
  │  L7  │ Meaning: method, path, │ HTTP, gRPC, WebSocket frames, DNS    │
  │      │ headers, body          │ ALB / nginx / Envoy / API gateway    │
  ├──────┼────────────────────────┼──────────────────────────────────────┤
  │(L6)  │ Encryption             │ TLS. Not really a layer; sits between│
  ├──────┼────────────────────────┼──────────────────────────────────────┤
  │  L4  │ Host:port, reliability │ TCP (ordered, reliable), UDP (not)   │
  │      │                        │ NLB, conntrack, ephemeral ports      │
  ├──────┼────────────────────────┼──────────────────────────────────────┤
  │  L3  │ Host-to-host routing   │ IP, BGP, anycast, MTU, VPC routing   │
  ├──────┼────────────────────────┼──────────────────────────────────────┤
  │  L2  │ Link-local frames      │ Ethernet, ARP, MTU 1500 (or 9000)    │
  └──────┴────────────────────────┴──────────────────────────────────────┘
```

**L4 vs L7 load balancer — the only comparison worth memorising:**

| | L4 (network LB) | L7 (application LB) |
|---|---|---|
| Routes on | IP + port | Path, host, header, cookie |
| Sees payload | No | Yes (terminates TLS) |
| Latency added | ~microseconds | ~1 ms |
| TLS | Passthrough or terminate | Terminates |
| Per-request LB | No — per *connection* | Yes — per *request* |
| Use for | Databases, gRPC passthrough, WebSocket at huge scale, non-HTTP | Public HTTP APIs, path routing, WAF, canaries |

The row that bites people: an L4 balancer balances *connections*, not requests. With HTTP
keep-alive or HTTP/2, one connection carries thousands of requests, so an L4 balancer in
front of an HTTP service will happily send 80% of your traffic to one backend.

### Follow-ups they will ask

**Q: You put an L4 load balancer in front of a gRPC service and one pod is at 90% CPU while others idle. Why?**
A: gRPC runs over HTTP/2, which multiplexes every call onto a single long-lived TCP
connection. The L4 balancer made one balancing decision when that connection was
established and has been pinning every subsequent RPC to the same pod ever since. The fix
is either an L7 proxy that understands HTTP/2 and balances per-stream — Envoy, or a service
mesh sidecar — or client-side load balancing where the client resolves all pod IPs and
round-robins RPCs itself. A cheap stopgap is a max-connection-age on the server so
connections churn and get rebalanced.

### Red flags — do not say this

- ❌ Reciting all seven OSI layers unprompted. → ✅ "Practically I care about L3, L4 and L7 — the interesting decision is whether the load balancer terminates TLS."
- ❌ "A load balancer distributes requests evenly." → ✅ "An L7 balancer distributes requests; an L4 balancer distributes connections, which with keep-alive is not the same thing."

---

## 2.2 DNS — resolution, records, TTL, anycast, failover

> **One-liner:** DNS is a globally distributed, aggressively cached, eventually consistent
> key-value store that every request depends on and nobody owns end to end — which is why
> it is both your cheapest global load balancer and your slowest failover mechanism.

### Say this in the interview

> A DNS lookup starts at the client's stub resolver, which checks its own cache, then asks
> a recursive resolver — usually the ISP's, or 8.8.8.8, or 1.1.1.1. If the recursive
> resolver doesn't have it cached, it walks the hierarchy: it asks a root server, which
> refers it to the `.com` TLD servers, which refer it to my domain's authoritative
> nameservers, which finally return the A record. That's three round trips on a cold cache,
> which is why a first lookup can be twenty to a hundred milliseconds and a warm one is
> effectively free. Everything in that chain caches by TTL. The part that matters for
> design is that the TTL is a *hint*, not a contract — some resolvers clamp it to their own
> minimum, some clients cache forever regardless, and negative answers get cached
> separately under the SOA minimum. So when I plan a failover I never assume a sixty-second
> TTL means sixty seconds of impact; I assume a long tail of stale clients and I make the
> old endpoint keep working, or I use anycast and health-checked load balancers so the IP
> never has to change in the first place. The best DNS failover is the one you don't have
> to do.

### Mental model

**Resolution walkthrough.** Numbers on the arrows are what each step costs cold.

```text
  browser
    │ 1. stub cache? (Chrome ~60s, OS resolver cache)
    ▼
  RECURSIVE RESOLVER  (ISP / 8.8.8.8 / 1.1.1.1)   <-- does all the work
    │  cache hit -> return in ~1-20 ms and stop
    │
    │ 2. "api.example.com A?"           ┌──────────────────┐
    ├──────────────────────────────────►│ ROOT (.)         │ 13 named
    │◄─ "ask the .com servers" ─────────│ anycast, global  │ addrs
    │                                    └──────────────────┘
    │ 3. "api.example.com A?"           ┌──────────────────┐
    ├──────────────────────────────────►│ TLD (.com)       │
    │◄─ "ask ns1.example.com" ──────────│ Verisign         │
    │                                    └──────────────────┘
    │ 4. "api.example.com A?"           ┌──────────────────┐
    ├──────────────────────────────────►│ AUTHORITATIVE    │ Route 53 /
    │◄─ "A 203.0.113.10, TTL 300" ──────│ your zone        │ Cloud DNS
    ▼                                    └──────────────────┘
  browser caches for TTL, opens TCP to 203.0.113.10

  Cold path: ~3 RTTs to the resolver's upstreams, 20-120 ms total.
  Warm path: 0-2 ms. >90% of real lookups are warm.
```

**Record types you must know.**

| Type | Maps | Notes for design |
|---|---|---|
| `A` | name → IPv4 | The workhorse |
| `AAAA` | name → IPv6 | Clients prefer it when both exist (Happy Eyeballs) |
| `CNAME` | name → another name | **Cannot coexist with any other record at the same name**, so it is illegal at the zone apex (`example.com`) |
| `ALIAS` / `ANAME` / CNAME-flattening | apex → another name | Provider-specific fix for the apex-CNAME problem (Route 53 alias, Cloudflare flattening). Resolved server-side; free on Route 53 |
| `NS` | zone → its nameservers | Delegation. Changing these is the slowest change in DNS |
| `SOA` | zone metadata | Its `minimum` field controls **negative caching** TTL |
| `MX` | domain → mail servers | Has a priority field |
| `TXT` | arbitrary text | SPF, DKIM, DMARC, domain-ownership proofs |
| `SRV` | service → host:port | Service discovery (used by Kubernetes DNS, SIP, XMPP) |
| `CAA` | which CAs may issue | Prevents mis-issuance; worth setting |
| `PTR` | IP → name | Reverse DNS; mail servers check it |

**TTL as an operational lever.**

| TTL | Use for | Cost |
|---|---|---|
| 30–60 s | Records you may need to fail over | ~50× more query volume; resolvers may clamp it up |
| 300 s (5 min) | Sensible default for service endpoints | Balanced |
| 3600 s (1 h) | Stable infrastructure records | 1 hour of staleness on any change |
| 86400 s (1 d) | `NS`, `MX`, apex records that never move | A mistake takes a day to undo |

The standard play before a planned migration: **lower the TTL to 60 s at least one old-TTL
period in advance**, migrate, then raise it back. If the old TTL was an hour, you must drop
the TTL more than an hour before the cutover, or the resolvers still holding the old record
never see the new short TTL.

**Caching layers — there are five, and you control two.**

```text
  ┌─────────────────┬──────────────────────┬─────────────────────────────┐
  │ Layer           │ Respects your TTL?   │ Do you control it?          │
  ├─────────────────┼──────────────────────┼─────────────────────────────┤
  │ App / runtime   │ Often NOT            │ Yes (JVM networkaddress.    │
  │                 │ (JVM historically    │ cache.ttl, Go resolver, DNS │
  │                 │  cached forever)     │ client libs)                │
  │ Connection pool │ No - holds the IP    │ Yes: max connection age     │
  │                 │ for the socket's life│                             │
  │ OS stub cache   │ Mostly               │ Partially                   │
  │ Recursive       │ Usually, but many    │ No                          │
  │ resolver        │ clamp to a min TTL   │                             │
  │ Authoritative   │ You set it           │ Yes                         │
  └─────────────────┴──────────────────────┴─────────────────────────────┘
```

**DNS-based load balancing and GeoDNS.**

```text
  Multiple A records (round robin)   -> client picks; no health awareness
  Weighted records                   -> 90/10 canary splits, cheap
  Latency-based routing              -> resolver's location -> nearest region
  GeoDNS                             -> country -> region (data residency)
  Failover records + health checks   -> swap the A record when a check trips
```

DNS load balancing is coarse: the resolver, not the user, is what gets geolocated, and the
granularity is "whole endpoint", not "this request". Use it to pick a *region*; use a real
load balancer inside the region.

**Why DNS failover is slow.** Four compounding reasons — name all four and you have
answered a senior-level question:

1. **TTL** — the floor. A 300 s TTL means up to 5 minutes of stale answers even from
   well-behaved resolvers.
2. **Negative caching** — if the name briefly returned NXDOMAIN or an empty answer, that
   *negative* result is cached under the SOA `minimum`, often 5–60 minutes, and it applies
   even after you fix the record.
3. **Resolver misbehaviour** — some recursive resolvers enforce a minimum TTL of their own
   and ignore yours; some serve stale entries deliberately when upstream is unreachable
   (RFC 8767 "serve-stale").
4. **The client never re-resolves** — an application with a warm connection pool holds the
   *socket*, not the name. It will keep using the old IP until that connection closes,
   regardless of DNS. Long-lived gRPC and HTTP/2 connections make this worse.

**Anycast.** The same IP address is announced from many physical locations via BGP; the
internet's own routing delivers each packet to the topologically nearest announcement.

```text
   1.1.1.1 announced from London, Mumbai, São Paulo, Tokyo, ...

   user in Mumbai  ──BGP picks nearest──►  Mumbai PoP   (~5 ms)
   user in Berlin  ──BGP picks nearest──►  London PoP   (~15 ms)
   Mumbai PoP dies ──BGP withdraws route─►  Singapore    (seconds, no DNS)
```

Anycast gives you geographic routing and failover **without touching DNS at all**, which
sidesteps every problem in the list above. That is why root nameservers, public resolvers
like 1.1.1.1 and 8.8.8.8, and every CDN are anycast. It works cleanly for stateless,
short-lived exchanges like DNS over UDP; for long-lived TCP it needs care, because a BGP
reconvergence mid-connection can land your packets at a different PoP that has no state
for that connection.

### Enterprise production example

**Amazon Web Services, us-east-1, 19–20 October 2025** — the best-documented DNS failure in
recent memory, and a story that covers TTL, negative caching, cascading dependencies and
recovery all at once.

DynamoDB's regional endpoint records in Route 53 were managed by internal automation: a
**DNS Planner** watched load-balancer health and produced plans, and three **DNS Enactors**
— one per Availability Zone, for resiliency — applied those plans. A latent race condition
fired: one Enactor was unusually delayed, checked plan freshness only at the *start* of its
run, and then applied a stale plan over a newer one. The cleanup process for that stale
plan then deleted it, and the result was that **`dynamodb.us-east-1.amazonaws.com` had no IP
addresses at all** — an empty answer, not an error. The automation could not repair the
inconsistent state without manual intervention.

The timeline, from the AWS summary: impact began at **11:48 PM PDT on 19 October**, engineers
identified the DNS issue by **12:38 AM**, applied temporary mitigations at **1:15 AM**, and all
DNS information was restored by **2:25 AM**. Customers recovered between **2:25 and 2:40 AM as
cached DNS records expired** — that fifteen-minute tail is the TTL, visible in a public
postmortem. But the event did not end there: EC2's DropletWorkflow Manager stores its state
in DynamoDB, so when DynamoDB became unreachable it marked hosts unavailable and then
suffered congestive collapse trying to renew every lease at once. **The DNS problem lasted
under three hours; the full event ran to 2:20 PM PDT — about fifteen hours.**

Four lessons to quote. **Redundancy was the failure mechanism** — three Enactors existed for
resiliency and their concurrency caused the outage. **An empty DNS answer is worse than an
error**, because there is nothing to retry against and no stale value to fall back on.
**Recovery was gated on cache expiry**, not on the fix. And **the blast radius was set by the
dependency graph**, not by the failing component: a DNS record for one database took down
services that had never heard of DynamoDB.

### Code

Two things break DNS-driven failover in real applications, and both are one-liners.

```javascript
// Node.js: by default the OS resolver is used and the result is NOT re-resolved
// for the life of a pooled socket. Two fixes.
import { Agent } from 'undici';
import dns from 'node:dns';

// 1. Prefer the DNS answer order the resolver gave you (Node >= 17 sorts by
//    default, which defeats round-robin A records).
dns.setDefaultResultOrder('verbatim');

// 2. Cap connection lifetime so pooled sockets are forced to re-resolve.
//    Without this, a failover that changes the A record is invisible to a
//    process that already has a warm pool - it will use the dead IP forever.
export const agent = new Agent({
  keepAliveTimeout: 30_000,       // idle sockets die after 30s
  keepAliveMaxTimeout: 120_000,
  connections: 64,
  connect: { timeout: 2_000 },
});
setInterval(() => agent.destroy().catch(() => {}), 5 * 60_000); // hard recycle
```

```python
# Python/FastAPI with httpx: same problem, same shape of fix.
import httpx

client = httpx.AsyncClient(
    limits=httpx.Limits(
        max_connections=100,
        max_keepalive_connections=20,
        keepalive_expiry=30.0,      # seconds; forces periodic re-resolution
    ),
    timeout=httpx.Timeout(connect=2.0, read=10.0, write=5.0, pool=1.0),
)
```

```hcl
# Route 53: health-checked failover. The health check is what makes DNS
# failover automatic; the TTL is what makes it slow.
resource "aws_route53_health_check" "primary" {
  fqdn              = "primary.example.com"
  type              = "HTTPS"
  resource_path     = "/readyz"
  failure_threshold = 3        # 3 x 30s = 90s to detect...
  request_interval  = 30
}

resource "aws_route53_record" "api_primary" {
  zone_id         = var.zone_id
  name            = "api.example.com"
  type            = "A"
  ttl             = 60         # ...plus up to 60s of TTL...
  records         = ["203.0.113.10"]
  set_identifier  = "primary"
  health_check_id = aws_route53_health_check.primary.id
  failover_routing_policy { type = "PRIMARY" }
}
# ...plus resolver clamping and warm client pools. Budget 5-10 min, not 60s.
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| DNS for coarse geo/region routing | You need per-request routing | Resolver-level granularity, not user-level |
| Low TTL (60 s) on failover-critical records | The record never changes | ~50× query volume; resolvers may ignore it anyway |
| Anycast for global entry points | Long-lived TCP that can't survive a reroute | BGP expertise or a provider that owns it (CDN) |
| DNS failover as your DR mechanism | You need sub-minute RTO | 5–10 minutes realistic, with a long stale tail |
| Health-checked failover records | Health check can't distinguish "down" from "slow" | Flapping if thresholds are tight |

### Follow-ups they will ask

**Q: Your TTL is 60 seconds. You fail over. Why are 5% of users still hitting the dead IP twenty minutes later?**
A: Four reasons stacking. Some recursive resolvers enforce their own minimum TTL and ignore
mine. If the name ever returned an empty or NXDOMAIN answer during the transition, that
negative result is cached under the SOA minimum, which is often much longer than 60 seconds.
Some clients — historically the JVM, and any app with a long-lived connection pool — cache
the resolved address for the life of the process or the socket and never re-resolve. And
RFC 8767 explicitly permits resolvers to serve stale data when they can't reach upstream. So
I plan for a long tail: keep the old endpoint answering, or better, avoid DNS failover
entirely by putting an anycast or health-checked load balancer IP in DNS so the address
never changes.

**Q: Why can't you put a CNAME at the apex of your domain?**
A: Because RFC 1034 says a CNAME cannot coexist with any other record at the same name, and
the apex must carry `SOA` and `NS` records by definition. So `example.com CNAME
lb.provider.net` is illegal. The workaround is a provider-side pseudo-record — Route 53
`ALIAS`, Cloudflare CNAME flattening, or an `ANAME` — where the DNS provider resolves the
target and returns the resulting A records itself. On Route 53 alias queries to AWS targets
are also free, which is a small bonus.

**Q: How would you do blue/green across two regions using DNS, and what's the failure mode?**
A: Weighted records — 100/0, shift to 90/10, then 50/50, then 0/100 — with a 60-second TTL
and health checks on both targets. The failure mode is that DNS weighting is statistical and
sticky per resolver, not per user: a large ISP resolver caches one answer for all its users,
so your 90/10 split can be very lumpy at the user level, and a user's session can flip
regions mid-flow when their cache expires. That means both regions must be able to serve any
user, so any session state has to be in a shared store or replicated. If I need true
per-request control I'd move the split into an anycast edge — a CDN worker or global load
balancer — rather than into DNS.

**Q: How does DNS interact with your service mesh or Kubernetes?**
A: Inside Kubernetes, `Service` names resolve through CoreDNS to a stable virtual IP, and
headless services resolve to the individual pod IPs, which is what gRPC clients use for
client-side load balancing. Two operational gotchas: CoreDNS has historically been a
scaling hot spot, since every pod resolves through it and `ndots:5` in the default
`resolv.conf` turns one external lookup into five search-domain queries — adding
`ndots:1` or a trailing dot to external hostnames is a real, measurable win. And node-local
DNS caching exists specifically because DNS latency shows up in application p99.

**Q: What is DNS-over-HTTPS and does it change anything for you as a backend engineer?**
A: DoH and DoT encrypt the query between the client and the recursive resolver, so ISPs
can't observe or tamper with lookups. For me as a backend engineer the practical effect is
that client-side DNS increasingly bypasses the OS resolver — browsers may use their own DoH
resolver — which means enterprise split-horizon DNS and any assumption that the client uses
the network's resolver can break. It also makes GeoDNS slightly less accurate, since the
resolver may be further from the user than the ISP's was, though EDNS Client Subnet
mitigates that where it's supported.

### Red flags — do not say this

- ❌ "We'll fail over with DNS, TTL is 60 seconds so it's fast." → ✅ "DNS failover is 5–10 minutes realistically once you account for negative caching and warm connection pools. I'd prefer an anycast or health-checked LB IP so the address never changes."
- ❌ "DNS load balancing distributes traffic evenly." → ✅ "It distributes per *resolver*, so a big ISP cache makes the split lumpy. Use it to pick a region; use a real LB inside it."
- ❌ "DNS is just name resolution, it's not part of the architecture." → ✅ "It's a dependency on the critical path of every request, and an empty DNS answer for one endpoint took out half of us-east-1 in October 2025."

---

## 2.3 TCP — handshake, congestion control, connection cost

> **One-liner:** TCP buys you reliable ordered bytes and charges you a round trip to start,
> a slow ramp to full speed, and head-of-line blocking whenever a packet is lost — which is
> why connection reuse is the highest-leverage network optimisation you will ever make.

### Say this in the interview

> TCP costs a round trip before a single byte of my request goes out — SYN, SYN-ACK, then
> the ACK carrying data. Add TLS 1.3 and that's two round trips before the server sees the
> request; on a hundred-millisecond intercontinental path that's two hundred milliseconds of
> pure setup. Then congestion control starts the connection deliberately slow: the initial
> window on Linux is ten segments, roughly fourteen kilobytes, and it doubles every round
> trip. So a fresh connection is both late and slow, and the fix is not to tune TCP, it's to
> not open new connections — keep-alive on the client, connection pooling to the database,
> and a long-lived pool to every upstream. The second thing I'd mention is head-of-line
> blocking: TCP guarantees in-order delivery, so a single lost segment stalls everything
> behind it even if those bytes already arrived. That's invisible on a clean datacenter
> network and very visible on mobile, and it's the reason HTTP/2 multiplexing doesn't fully
> deliver on a lossy link and HTTP/3 moved to QUIC. Concretely, in my services I set a
> connection pool sized from Little's Law, a max connection age so pooled sockets
> re-resolve DNS, and TCP_NODELAY on anything latency-sensitive.

### Mental model

**The handshake, and what it costs.**

```text
  client                                server        RTT accounting
    │──────────── SYN ────────────────►│              0.0 RTT
    │◄─────────── SYN-ACK ──────────────│              0.5 RTT
    │──────────── ACK + ClientHello ───►│              1.0 RTT  <- TCP up
    │◄─────────── ServerHello, cert ────│              1.5 RTT
    │──────────── Finished + REQUEST ──►│              2.0 RTT  <- TLS 1.3
    │◄─────────── RESPONSE ─────────────│              2.5 RTT  <- first byte

   On a 100 ms RTT path: 200 ms before the server reads the request.
   TLS 1.2 adds one more round trip. QUIC collapses this to 1 RTT.
   A reused keep-alive connection: 0 RTT of setup. That is the whole point.
```

**Congestion control in one paragraph.** TCP does not know how much bandwidth exists, so it
probes. **Slow start**: begin with an initial congestion window (`initcwnd`, 10 segments on
Linux ≈ 14 KB) and double it every RTT until loss occurs. **Congestion avoidance**: after
that, grow linearly. On loss, cut the window — CUBIC, the Linux default, cuts to about 70%
and probes back up; **BBR**, developed at Google and widely deployed on their edge, models
bottleneck bandwidth and round-trip time instead of treating loss as the only congestion
signal, which makes it much better on lossy long-haul links.

```text
  cwnd
   │            ╱╲    congestion avoidance (linear)
   │         ╱╲╱  ╲╱╲
   │      ╱─╯
   │   ╱─╯  slow start (exponential: 14KB -> 28 -> 56 -> 112 ...)
   │╱─╯
   └────────────────────────────────► time
   RTT: 1     2     3     4

   Consequence: to send 100 KB you need ~4 RTTs even on an idle gigabit link.
   The first 14 KB is free-ish; everything after waits for the window to open.
```

That 14 KB is why "get your critical CSS into the first 14 KB" is a real performance rule,
and why an API returning a 500 KB JSON blob on a fresh connection is slower than the
bandwidth math suggests.

**Head-of-line blocking at the transport layer.**

```text
  Sent:      [1][2][3][4][5]
  Arrived:   [1][X][3][4][5]        packet 2 lost

  TCP delivers to the application:  [1] ... then NOTHING ...
  Packets 3,4,5 sit in the kernel receive buffer, complete and useless,
  until the retransmission of 2 arrives one RTT later.

  With HTTP/2, streams A, B and C share this connection. A lost packet
  belonging to stream A stalls B and C too. HTTP/2 removed HOL blocking at
  the HTTP layer and left it fully intact at the TCP layer.
```

**What a connection actually costs.** Say these numbers; almost nobody does.

| Resource | Per TCP connection |
|---|---|
| Kernel socket buffers | ~4–16 KB minimum, auto-tuned up to MBs for high-BDP paths |
| File descriptor | 1 (check `ulimit -n`; default 1024 is a common outage) |
| Client ephemeral port | 1 of ~28,000 by default (`net.ipv4.ip_local_port_range`) |
| conntrack entry (NAT/firewall) | ~300 bytes, and the table has a hard limit |
| `TIME_WAIT` after close | The 4-tuple is reserved for 60 s on Linux (2×MSL) |
| Setup latency | 1 RTT (TCP) + 1 RTT (TLS 1.3) |
| Setup CPU | TLS asymmetric crypto: tens to hundreds of microseconds |

`TIME_WAIT` exhaustion is the classic production surprise: a service making many short-lived
outbound connections to one destination runs out of ephemeral ports at roughly 28,000
connections per 60 seconds — about 470/s — and then fails to connect while looking perfectly
healthy. The fix is connection reuse, not kernel tuning.

**Nagle plus delayed ACK.** Nagle's algorithm buffers small writes until the previous data is
acknowledged; delayed ACK holds acknowledgements up to ~40 ms hoping to piggyback them.
Together they produce a pathological 40 ms stall on request/response workloads that write a
header and a body as two separate small writes. Set `TCP_NODELAY` (most HTTP libraries do
already) and write your message in one call.

### Enterprise production example

**Google** deployed **BBR** congestion control on google.com and YouTube and published the
result: BBR replaces loss-based congestion control with an explicit model of the bottleneck
bandwidth and minimum round-trip time, so it does not collapse its window on the random
packet loss common in mobile and long-haul networks. Google reported substantial throughput
improvements on their global network and reduced queueing delay, and BBR was upstreamed into
the Linux kernel — you can enable it with `net.ipv4.tcp_congestion_control=bbr`. Two things
make this a good interview reference. It is a reminder that **loss is not the same thing as
congestion** on modern networks, where loss is often random radio interference rather than a
full buffer. And it is available to you for free on any modern Linux host, which makes it one
of the highest-yield single-line changes for a service serving mobile clients over long
distances.

### Code

The single highest-value TCP-related thing in application code is connection reuse. Here it
is done properly on both stacks, with the timeouts that make it safe.

```python
# FastAPI service calling an internal upstream. One shared client for the
# process lifetime - creating a client per request is the most common
# performance bug in Python services and costs 1 RTT + TLS on every call.
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(
        base_url="https://inventory.internal",
        http2=True,
        limits=httpx.Limits(
            max_connections=100,           # Little's Law: lambda * W
            max_keepalive_connections=20,
            keepalive_expiry=30.0,
        ),
        timeout=httpx.Timeout(
            connect=2.0,    # fail fast on a dead host
            read=5.0,       # the one people forget; without it a hung
                            # upstream holds your worker forever
            write=5.0,
            pool=1.0,       # time waiting for a free connection
        ),
        transport=httpx.AsyncHTTPTransport(retries=0),  # retry at the app
    )                                                    # layer, with backoff
    yield
    await app.state.http.aclose()

app = FastAPI(lifespan=lifespan)
```

```bash
# Host-level settings worth knowing by name in an interview.
sysctl -w net.ipv4.tcp_congestion_control=bbr      # better on lossy/long paths
sysctl -w net.core.somaxconn=4096                  # accept queue depth
sysctl -w net.ipv4.tcp_max_syn_backlog=8192        # half-open queue
sysctl -w net.ipv4.ip_local_port_range="10000 65535"  # ~55k ephemeral ports
sysctl -w net.ipv4.tcp_tw_reuse=1                  # reuse TIME_WAIT for
                                                   # outbound only - safe
ulimit -n 65535                                    # fds; 1024 default kills
                                                   # connection-heavy servers
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Keep-alive / pooling everywhere | Never — always do this | Pooled sockets hold stale DNS; cap connection age |
| Large receive buffers | Memory-constrained hosts with many connections | MBs per connection at high bandwidth-delay product |
| BBR congestion control | You're entirely inside one clean datacenter | Can be aggressive against CUBIC flows sharing a link |
| `TCP_NODELAY` | Bulk transfer where you want coalescing | Slightly more packets on the wire |

### Follow-ups they will ask

**Q: Your service intermittently fails to connect to an upstream under load, but the upstream is healthy. What is it?**
A: Most likely ephemeral port or `TIME_WAIT` exhaustion on the *client* side. Every
short-lived outbound connection to the same destination consumes one of roughly 28,000
ephemeral ports and holds the 4-tuple in `TIME_WAIT` for 60 seconds after close, which caps
you at about 470 new connections per second to a single destination. The symptom is
`EADDRNOTAVAIL` or connect timeouts while the upstream reports nothing wrong. The correct
fix is connection reuse — a keep-alive pool turns thousands of connections per second into a
few dozen persistent ones. Widening the port range and enabling `tcp_tw_reuse` are stopgaps.
Also check conntrack table limits if there is a NAT or stateful firewall in the path.

**Q: Why is HTTP/2 sometimes slower than HTTP/1.1 on a bad mobile network?**
A: Because HTTP/2 puts every stream on one TCP connection, so TCP head-of-line blocking now
affects everything at once. With HTTP/1.1 the browser opens six connections, and a lost
packet stalls one sixth of the work; with HTTP/2 a single lost packet stalls all of it until
the retransmission arrives. On a clean network HTTP/2 wins comfortably because it removes
per-connection setup and compresses headers; above roughly 2% packet loss the multiplexing
advantage inverts. That is precisely the problem QUIC solves by giving each stream its own
loss recovery.

**Q: How do you pick a connection pool size?**
A: Little's Law against the *downstream* resource, not the upstream one. If I take 3,000
requests per second and each spends 15 milliseconds in the database, I need `3000 × 0.015 =
45` connections busy at any instant, so I'd provision maybe 60 across the whole fleet for
burst. The number that matters is the total across all pods against the database's
`max_connections`, not the per-pod number — twenty pods with a default pool of ten is two
hundred connections, which is past the point where Postgres throughput starts *decreasing*.
Above a few hundred I'd front it with PgBouncer in transaction-pooling mode.

**Q: What's the actual latency benefit of keeping a connection warm?**
A: One TCP round trip plus one TLS 1.3 round trip, plus the slow-start ramp. Within a
datacenter, where the round trip is about 50 microseconds, that's negligible per request but
adds up in CPU for the TLS handshake. Across the internet at 100 ms RTT it's 200 milliseconds
of pure setup on every request — often more than the server-side work. Plus the reused
connection has an already-open congestion window, so a 100 KB response transfers in one round
trip instead of four.

### Red flags — do not say this

- ❌ "TCP is reliable so I don't need to think about it." → ✅ "Reliable and *in-order*, which means one lost packet stalls everything behind it — that's why HTTP/2 struggles on lossy links."
- ❌ "I'd create an HTTP client per request." → ✅ "One shared pooled client per process, with a max connection age so it still picks up DNS changes."
- ❌ "We'll increase the timeout." → ✅ "I'd set a read timeout at all — the common bug is no read timeout, which lets one hung upstream consume every worker."

---

## 2.4 UDP — and QUIC as the modern answer

> **One-liner:** UDP gives you a bare datagram with no handshake, no ordering and no
> retransmission, which is exactly right when a late packet is worthless — and QUIC is what
> happens when you rebuild TCP's guarantees on top of it, in userspace, done right.

### Say this in the interview

> UDP is the right choice when a retransmitted packet would arrive too late to be useful.
> In a voice or video call, a frame that shows up two hundred milliseconds late is worse
> than a frame that never shows up, because TCP would have stalled everything behind it
> waiting for the retransmission. Same reasoning for game state, for metrics where losing a
> few samples is fine, and for DNS where the whole exchange is one small question and one
> small answer and a handshake would double the cost. What you give up is everything —
> ordering, delivery, congestion control — so you either don't need it or you rebuild it.
> QUIC is the interesting case: it's built on UDP but it reimplements reliability,
> congestion control and TLS 1.3 in userspace, and because it controls its own framing it
> can keep each stream's loss recovery independent, which is what finally kills head-of-line
> blocking. It also identifies connections by a connection ID rather than the IP-and-port
> four-tuple, so a phone switching from Wi-Fi to cellular keeps the same connection instead
> of re-handshaking. That's HTTP/3.

### Mental model

```text
   TCP                             UDP
   ├─ connection setup: 1 RTT      ├─ setup: none, just send
   ├─ ordered delivery             ├─ arrives in any order, or not at all
   ├─ retransmission               ├─ you retransmit, or you don't care
   ├─ congestion control           ├─ none - you can melt a network
   ├─ flow control                 ├─ none
   └─ head-of-line blocking        └─ no HOL: each datagram is independent

   QUIC = UDP + (reliability, congestion control, TLS 1.3, multiplexing)
          all in userspace, PER STREAM.
```

**Where UDP is genuinely correct:** DNS (single small request/response), real-time media
(RTP inside WebRTC), multiplayer game state, NTP, syslog and StatsD-style metrics, VPN
tunnels (WireGuard), and QUIC.

**QUIC's four wins over TCP+TLS:**

```text
  1. Handshake     TCP+TLS1.3 = 2 RTT     QUIC = 1 RTT, 0 RTT on resume
  2. HOL blocking  one TCP stream stalls   each QUIC stream recovers
                   all HTTP/2 streams      independently
  3. Migration     4-tuple change = new    Connection ID survives an IP
                   connection              change (Wi-Fi -> LTE)
  4. Encryption    optional, layered on    mandatory, integrated; even most
                                           transport headers are encrypted
```

**The costs, which you must name:** QUIC runs in userspace, so it burns noticeably more CPU
per byte than kernel TCP with hardware offload — historically a multiple, narrowing as
GSO/GRO and offloads improve. Some corporate networks and middleboxes block UDP/443
outright, so every QUIC client needs a working fallback to TCP. And it's harder to debug:
`tcpdump` shows you encrypted UDP, not a readable handshake.

### Enterprise production example

**Cloudflare Radar's 2025 Year in Review** gives the honest adoption picture, which is more
useful in an interview than enthusiasm. Globally in 2025, of all requests to Cloudflare:
**HTTP/2 was 50%, HTTP/1.x was 29%, and HTTP/3 — that is, QUIC — was 21%.** Those shares were
largely unchanged from 2024, each moving only fractions of a percentage point. Cloudflare
also notes the geography is uneven: 15 countries sent more than a third of their requests
over HTTP/3, while several — including Hong Kong, Singapore and Ireland — were below 10%,
largely because of bot traffic that still speaks HTTP/1.x.

The lesson for design: QUIC is real, mainstream and worth enabling at the edge, but four
years after standardisation it carries about a fifth of traffic, so **HTTP/3 is an
optimisation, not a foundation.** Your origin can keep speaking HTTP/1.1 or HTTP/2 while the
CDN terminates HTTP/3 for the clients that support it — which is exactly how most
production deployments actually do it.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| UDP: late data is useless (media, games) | You need any delivery guarantee | You rebuild reliability yourself, badly |
| UDP: single-exchange protocols (DNS, NTP) | Payload exceeds path MTU (~1500 B) | IP fragmentation, which is unreliable |
| QUIC/HTTP/3 at the edge for mobile users | Purely server-to-server on a clean LAN | More CPU per byte; UDP/443 sometimes blocked |
| QUIC 0-RTT resumption | The request is a non-idempotent write | 0-RTT data is replayable by design |

### Follow-ups they will ask

**Q: QUIC gives 0-RTT resumption. Why is that dangerous?**
A: Because 0-RTT early data has no replay protection — an attacker who captures the
encrypted early-data packet can resend it, and the server will process it again. That is
fine for a `GET`, which is idempotent, and unacceptable for `POST /payments`. The standard
mitigation is to only permit 0-RTT for safe methods and require a full 1-RTT handshake for
anything that mutates state, which most servers implement as a policy switch. It's the same
class of problem as retrying a non-idempotent request, and the same answer applies: an
idempotency key makes replay harmless.

**Q: Should you enable HTTP/3 on your origin servers?**
A: Usually not, and this is a good "no" to have ready. The benefits of QUIC — head-of-line
blocking, connection migration, handshake round trips — all matter on lossy, high-latency,
mobile last-mile links. Between your CDN's edge and your origin, or between two services in
a VPC, packet loss is near zero and the round trip is under a millisecond, so QUIC's
advantages evaporate while its higher CPU cost per byte remains. The standard architecture is
HTTP/3 from client to edge, HTTP/2 or HTTP/1.1 from edge to origin.

### Red flags — do not say this

- ❌ "UDP is faster than TCP." → ✅ "UDP has no handshake and no head-of-line blocking, so it's lower latency for loss-tolerant data. It isn't faster for bulk transfer, and it has no congestion control."
- ❌ "We should move everything to HTTP/3." → ✅ "HTTP/3 at the edge for mobile clients; it's about 21% of Cloudflare's traffic and the wins don't apply inside the datacenter."

---

## 2.5 TLS / HTTPS — handshake cost, termination, mTLS

> **One-liner:** TLS costs you one extra round trip and some CPU on connection setup and
> essentially nothing per byte afterwards, so the entire design question is *where* you
> terminate it and how you rotate the certificates.

### Say this in the interview

> TLS 1.3 adds one round trip on top of the TCP handshake, so a cold HTTPS connection is
> two round trips before the server sees the request, versus three with TLS 1.2 — that's
> the main reason to be on 1.3. Once the connection is up, symmetric encryption with AES-NI
> hardware acceleration is essentially free, gigabytes per second per core, so the cost is
> entirely in setup: the asymmetric signature and key exchange. That means the optimisation
> is again connection reuse plus session resumption, not cipher tuning. Architecturally the
> decision is where TLS terminates. Terminating at the load balancer is the common choice
> because it lets the balancer route on path, cache, run a WAF and add a request ID, and it
> centralises certificate management — but it means traffic behind the balancer is
> plaintext, which most compliance regimes now reject, so I'd re-encrypt to the origin even
> if the internal network is private. For service-to-service I'd use mutual TLS, where both
> sides present certificates, because it gives me cryptographic identity for authorisation
> rather than trusting a network boundary. The thing that makes or breaks all of this is
> automated certificate rotation — ACME for public certs, and a short-lived internal CA for
> mTLS, because manually renewed certificates are the single most reliable way to schedule
> an outage.

### Mental model

**Handshake round trips.**

```text
  TLS 1.2:  TCP(1) + TLS(2) = 3 RTT before the request is sent
  TLS 1.3:  TCP(1) + TLS(1) = 2 RTT
  TLS 1.3 resumption (PSK):        1 RTT
  TLS 1.3 0-RTT early data:        0 RTT   (replayable - safe methods only)
  QUIC:                            1 RTT   (TLS is built in)
  QUIC 0-RTT:                      0 RTT

  At 100 ms RTT that is 300 / 200 / 100 / 0 ms of pure setup.
```

**Where the CPU goes.** Per handshake: one asymmetric operation (ECDSA P-256 signature, tens
of microseconds; RSA-2048 is several times slower on the server side) plus a key exchange.
Per byte afterwards: AES-GCM with AES-NI runs at gigabytes per second per core. So a server
doing 10,000 new TLS connections per second is doing real work; a server doing 10,000
requests per second over 100 reused connections is doing almost none. **Session resumption**
— stateless session tickets in TLS 1.2, pre-shared keys in 1.3 — skips the asymmetric step
entirely.

**Termination topologies.**

```text
  (a) Terminate at the edge/LB, plaintext behind    <- simplest, common
      client ══TLS══► ALB ──http──► app
      + one cert, LB can route/cache/WAF
      - plaintext inside the VPC; fails most compliance reviews

  (b) Terminate at LB, RE-ENCRYPT to origin         <- the usual right answer
      client ══TLS══► ALB ══TLS══► app
      + edge features AND encryption in transit end to end
      - two handshakes; origin cert can be a long-lived internal CA cert

  (c) TLS passthrough (L4)                       <- when the LB must not see
      client ══════════TLS══════════► app
      + true end-to-end, LB is a dumb pipe
      - no path routing, no WAF, no HTTP-level metrics at the LB

  (d) mTLS, service to service                      <- internal identity
      svc A ══TLS, both sides present certs══► svc B
      + cryptographic identity, not IP-based trust
      - a CA, rotation, and a mesh or library to enforce it
```

**mTLS.** In normal TLS only the server proves who it is. In mutual TLS the client presents a
certificate too, and the server authorises based on the identity in it — a SPIFFE ID, or a
subject like `spiffe://cluster/ns/payments/sa/checkout`. The value is that you stop
authorising by IP address or network location, which is the core idea of zero trust. The cost
is a certificate lifecycle for every workload: issuance at pod start, rotation every few
hours, and revocation. This is why people adopt a service mesh (Istio, Linkerd) or
SPIFFE/SPIRE rather than doing it by hand.

**Certificate management.** Public certificates from Let's Encrypt are valid for 90 days and
are issued via the ACME protocol, which means renewal must be automated — `cert-manager` in
Kubernetes, or your load balancer's managed certificates (AWS ACM, Google-managed certs),
which handle renewal for you and are the right default. Maximum certificate lifetimes are
being ratcheted downward across the industry, so any process involving a human with a
calendar reminder is already obsolete. Internal mTLS certificates go the other way — issue
them with lifetimes measured in hours, so revocation becomes unnecessary.

### Enterprise production example

**Let's Encrypt** changed the economics of HTTPS by pairing free certificates with the ACME
protocol, and the key design decision was the **90-day lifetime**. That was deliberate: it is
short enough that manual renewal is intolerable, which forces automation, which in turn makes
renewal reliable. The result is that the web went from HTTPS being a paid, annual, manual
purchase to being the default. **Cloudflare Radar** data shows the outcome — the large
majority of web traffic now uses modern TLS, with TLS 1.3 and QUIC together accounting for
well over 90% and legacy TLS 1.2 down in the single digits.

The transferable lesson is one you can apply in a design answer: **a short expiry is a
forcing function for automation.** The same reasoning is why internal mTLS certificates are
issued for hours rather than years, and why short-lived database credentials from a secrets
manager beat long-lived ones — if the credential cannot outlive the incident, rotation
stops being an emergency procedure.

### Code

```python
# FastAPI behind a load balancer that terminates TLS. Two things must be right:
# trust the forwarded protocol header ONLY from the LB, and enforce HSTS.
from fastapi import FastAPI, Request
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

app = FastAPI()
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["api.example.com"])
# Only honour X-Forwarded-* from the LB subnet; otherwise a client can spoof
# X-Forwarded-Proto: https and defeat your redirect-to-HTTPS logic.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="10.0.0.0/8")

@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["Strict-Transport-Security"] = \
        "max-age=63072000; includeSubDomains; preload"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp
```

```yaml
# cert-manager: automated issuance + renewal. The renewBefore is what turns
# a 90-day certificate into a non-event.
apiVersion: cert-manager.io/v1
kind: Certificate
metadata: { name: api-tls, namespace: prod }
spec:
  secretName: api-tls
  duration: 2160h        # 90d
  renewBefore: 720h      # renew at 30 days remaining, not at 1 day
  privateKey: { algorithm: ECDSA, size: 256, rotationPolicy: Always }
  dnsNames: ["api.example.com"]
  issuerRef: { name: letsencrypt-prod, kind: ClusterIssuer }
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Terminate at LB + re-encrypt | Ultra-low-latency internal hops | Two handshakes; slightly more CPU |
| TLS passthrough (L4) | You need path routing or a WAF | LB becomes blind: no HTTP metrics, no caching |
| mTLS service-to-service | Small system, few services, one team | A CA, rotation automation, and mesh complexity |
| TLS 1.3 0-RTT | Any non-idempotent request | Replayable early data |
| Managed certs (ACM, Google-managed) | You need the private key off-box | Vendor lock-in; key never exportable |

### Follow-ups they will ask

**Q: Is TLS expensive? Quantify it.**
A: Per byte, no — AES-GCM with AES-NI runs at gigabytes per second per core, so bulk
encryption is a rounding error. Per handshake, yes — an ECDSA P-256 signature plus key
exchange is tens of microseconds of CPU, so a server absorbing 10,000 new connections per
second spends real cores on it. That means the optimisation targets are connection reuse and
session resumption, not cipher suite selection. If handshakes really are the bottleneck, ECDSA
certificates are substantially cheaper on the server than RSA-2048, and session tickets let
you skip the asymmetric step entirely on resumption.

**Q: Your LB terminates TLS. Is the traffic behind it safe because the VPC is private?**
A: "Private network therefore trusted" is the assumption zero trust exists to kill. A VPC is
shared with every other workload in the account, an SSRF bug or a compromised sidecar gives an
attacker a position inside it, and most compliance frameworks now require encryption in
transit regardless of network boundary. So I'd re-encrypt from the load balancer to the
origin — the certificate there can be a long-lived internal CA cert, which is cheap to
operate — and for service-to-service I'd use mTLS so the authorisation decision is based on a
cryptographic identity rather than on a source IP that can be spoofed or reused.

**Q: How do you handle certificate rotation without downtime?**
A: Overlap and reload rather than replace and restart. Issue the new certificate well before
expiry — `renewBefore` of 30 days on a 90-day cert — write it to the same secret, and have
the server hot-reload its TLS configuration on file change rather than restarting; nginx and
Envoy both support this, and Go's `tls.Config.GetCertificate` makes it trivial. For mTLS with
short-lived certs the mesh sidecar handles rotation transparently. The failure mode to guard
against is the trust chain: if you're rotating the CA itself, you must distribute the new CA
to every verifier *before* you start issuing leaves from it, otherwise you get a mutual
outage.

**Q: What's the difference between HSTS and just redirecting HTTP to HTTPS?**
A: The redirect still involves one plaintext request, which is exactly where an attacker on
the path strips the upgrade. HSTS tells the browser to never use plaintext for this host
again for `max-age` seconds, so after the first visit the browser rewrites the scheme itself
before any packet leaves. The preload list closes the remaining first-visit gap by shipping
the policy in the browser binary. The caveat is that HSTS is hard to undo — if you set a
two-year `max-age` with `includeSubDomains` and a subdomain can't do TLS, you've broken it for
two years — so roll it out with a short max-age first.

### Red flags — do not say this

- ❌ "TLS is too slow, we'll use HTTP internally." → ✅ "Per-byte cost is negligible; the cost is handshakes, which connection reuse eliminates. I'd re-encrypt internally."
- ❌ "We renew certificates every year." → ✅ "ACME with automated renewal at 30 days remaining, plus alerting on expiry — a human with a calendar reminder is an outage waiting to happen."
- ❌ "mTLS everywhere, day one." → ✅ "mTLS where the identity actually gates a decision. It needs a CA and rotation automation, which is a mesh-sized commitment."

---

## 2.6 HTTP/1.1 vs HTTP/2 vs HTTP/3

> **One-liner:** HTTP/1.1 gives you one request at a time per connection, HTTP/2 multiplexes
> many onto one connection and moves head-of-line blocking down to TCP, and HTTP/3 moves the
> transport to QUIC so each stream recovers from loss independently.

### Say this in the interview

> HTTP/1.1 sends one request at a time per connection, so browsers open six connections per
> origin to get any parallelism — and that's why domain sharding used to be a real
> optimisation. Pipelining was supposed to fix it but it preserved response ordering, so one
> slow response blocked everything behind it, and every browser disabled it. HTTP/2 fixed it
> properly with a binary framing layer: many streams interleaved on one connection, plus
> HPACK header compression, which matters more than people expect because a typical request
> is mostly repeated headers. But HTTP/2's multiplexing sits on top of TCP, and TCP
> guarantees in-order delivery of the whole byte stream — so a single lost packet stalls
> every stream on that connection. Head-of-line blocking moved from the HTTP layer to the
> transport layer rather than disappearing. HTTP/3 fixes that by running over QUIC, where
> each stream has independent loss recovery, so a lost packet only stalls its own stream. In
> practice I'd enable HTTP/2 everywhere and HTTP/3 at the edge for mobile clients — it's
> about a fifth of Cloudflare's traffic — and keep HTTP/1.1 or HTTP/2 from edge to origin,
> because inside the datacenter there's no packet loss for QUIC to save me from.

### Mental model

```text
  HTTP/1.1  one request in flight per connection; browsers open 6
  ┌──────────────────────────────────────────────────────────────┐
  │ conn1: [--- req A ---][--- req D ---]                        │
  │ conn2: [------ req B ------]                                 │
  │ conn3: [-- req C --][- req E -]                              │
  └──────────────────────────────────────────────────────────────┘
     6 handshakes, 6 congestion windows, headers repeated in full

  HTTP/2   one connection, interleaved binary frames
  ┌──────────────────────────────────────────────────────────────┐
  │ conn1: [A1][B1][C1][A2][B2][C2][A3][B3]...                   │
  │        one TCP stream underneath -> ONE lost packet stalls    │
  │        A, B and C together                            <- HOL  │
  └──────────────────────────────────────────────────────────────┘

  HTTP/3   QUIC: independent streams over UDP
  ┌──────────────────────────────────────────────────────────────┐
  │ stream A: [A1][A2][ X ][A4]   <- only A waits for the retx    │
  │ stream B: [B1][B2][B3][B4]    <- B and C keep flowing         │
  │ stream C: [C1][C2][C3][C4]                                    │
  └──────────────────────────────────────────────────────────────┘
```

| | HTTP/1.1 | HTTP/2 | HTTP/3 |
|---|---|---|---|
| Transport | TCP | TCP | QUIC over UDP |
| Framing | Text | Binary | Binary |
| Concurrency | 1/connection (browsers use 6) | Multiplexed streams | Multiplexed streams |
| HOL blocking | At HTTP layer | At TCP layer | Eliminated |
| Header compression | None | HPACK | QPACK |
| Handshake to first byte | 1 RTT + TLS | 1 RTT + TLS | 1 RTT total; 0-RTT resume |
| TLS | Optional | Effectively required by browsers | Mandatory (TLS 1.3) |
| Connection migration | No | No | Yes (connection ID) |
| Server push | No | Yes — **removed from browsers** | No |

**Server push and why it died.** HTTP/2 let a server proactively push resources the client
had not asked for. It failed for a straightforward reason: the server does not know what the
client already has cached, so most pushes were wasted bandwidth, and the complexity of
getting it right exceeded the benefit. Chrome removed support in 2022. The replacement is
`103 Early Hints`, which sends `Link: rel=preload` headers before the real response so the
*client* decides what to fetch — the client knows its own cache, so it makes a better
decision. Knowing this history is a good signal in an interview; "we'd use HTTP/2 server
push" is a stale answer.

**When HTTP/3 actually matters:** mobile and lossy networks (independent stream recovery),
high-RTT paths (one fewer handshake round trip), and clients that change networks mid-session
(connection migration). **When it doesn't:** service-to-service inside a VPC, where loss is
near zero, RTT is sub-millisecond, and QUIC's userspace CPU cost is a pure loss.

### Enterprise production example

**Cloudflare Radar's 2025 Year in Review** gives the numbers to quote: globally in 2025,
**50% of requests to Cloudflare used HTTP/2, 29% used HTTP/1.x, and 21% used HTTP/3**, with
all three essentially flat year over year. Adoption is geographically uneven — 15 countries
sent more than a third of their requests over HTTP/3, led by Georgia at 38%, while several
territories were under 10% because of heavy bot traffic still speaking HTTP/1.x.

Two things worth saying out loud from this. First, **HTTP/1.x is still 29% of the internet
four years after HTTP/3 was standardised**, so any API you build must still work correctly
over HTTP/1.1 — which is a real constraint for SSE, because HTTP/1.1's six-connections-per-
origin limit applies. Second, **protocol adoption is driven by the edge, not by origins**:
Cloudflare terminates HTTP/3 for clients and speaks something older to origins, which is why
you get most of the benefit without touching your application servers.

### Code

```nginx
# nginx: HTTP/2 and HTTP/3 side by side. Alt-Svc is what tells a client that
# arrived over TCP that it may retry over QUIC next time - without it, nobody
# discovers your HTTP/3 endpoint.
server {
    listen 443 ssl;
    listen 443 quic reuseport;      # UDP/443
    http2 on;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_early_data off;             # 0-RTT is replayable; off unless you have
                                    # idempotency handled end to end

    add_header Alt-Svc 'h3=":443"; ma=86400' always;

    # HTTP/2 defaults are tuned for browsers, not for a gRPC/API workload.
    http2_max_concurrent_streams 256;
    keepalive_timeout 75s;

    location / {
        proxy_pass http://origin;   # origin speaks HTTP/1.1 - that is fine
        proxy_http_version 1.1;
        proxy_set_header Connection "";   # enable upstream keep-alive
    }
}
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| HTTP/2 for browsers and gRPC | You need per-request L4 balancing | One connection means an L4 LB pins all traffic to one pod |
| HTTP/3 at the edge | Server-to-server on a clean network | More CPU per byte; UDP/443 sometimes blocked |
| HTTP/1.1 to origin | You need multiplexing internally | Extra connections; fine at datacenter RTT |
| `103 Early Hints` | Your CDN or client doesn't support it | Falls back harmlessly to nothing |

### Follow-ups they will ask

**Q: You moved to HTTP/2 and one backend pod is now hot. Why?**
A: Because HTTP/2 puts everything on one long-lived connection, and any L4 load balancer in
front of it made its routing decision once, at connection setup. Every subsequent request
rides the same connection to the same pod. The fixes, in order of preference: use an L7 proxy
that balances per stream (Envoy, or an ALB with HTTP/2 target support); or set a max
connection age on the server so clients periodically reconnect and get rebalanced; or move to
client-side load balancing, which is what gRPC does natively with a headless service.

**Q: Does HTTP/2 make domain sharding obsolete?**
A: Yes, and it actively makes it harmful. Sharding assets across `static1.`, `static2.` and so
on existed purely to get around the six-connections-per-origin limit in HTTP/1.1. Under
HTTP/2 each extra origin costs a DNS lookup, a TCP handshake and a TLS handshake, and it
fragments header compression state and the congestion window across connections. Consolidating
onto one origin is the right move once HTTP/2 is in play.

**Q: Should the connection between your API gateway and your microservices be HTTP/2?**
A: Yes for gRPC, since gRPC requires it, and generally yes for high-volume internal HTTP
because multiplexing means far fewer connections and much better header compression on
repetitive internal calls. The thing to watch is the load-balancing problem above — internal
HTTP/2 needs either a mesh sidecar or client-side balancing, otherwise you get connection
pinning. For low-volume internal calls HTTP/1.1 with keep-alive is perfectly fine and simpler
to debug.

### Red flags — do not say this

- ❌ "HTTP/2 eliminates head-of-line blocking." → ✅ "It eliminates it at the HTTP layer and leaves it at the TCP layer — one lost packet still stalls every stream. That's what HTTP/3 fixes."
- ❌ "We'd use HTTP/2 server push to speed up first load." → ✅ "Server push was removed from browsers in 2022; `103 Early Hints` is the replacement and it's better because the client knows its own cache."
- ❌ "HTTP/3 everywhere." → ✅ "HTTP/3 at the edge — about 21% of Cloudflare's traffic — with HTTP/1.1 or HTTP/2 to origin, where there's no loss for QUIC to help with."

---

## 2.7 HTTP semantics for design — methods, codes, headers

> **One-liner:** HTTP already encodes idempotency, caching, concurrency control and
> backpressure — using the right method, status code and header means you get those
> behaviours from every proxy, CDN and client library for free instead of reinventing them.

### Say this in the interview

> The reason I care about HTTP semantics in a design discussion is that a huge amount of
> infrastructure behaves differently based on them, for free. A `GET` is safe and idempotent,
> so every CDN, proxy and client library will cache it and retry it. A `PUT` and a `DELETE`
> are idempotent but not safe, so they're retryable but not cacheable. `POST` is neither, so
> a client that retries a `POST` after a timeout can double-charge someone — which is exactly
> why I put an `Idempotency-Key` header on every mutating endpoint that matters and store the
> response keyed on it. On status codes, the ones that carry design meaning are `429` with a
> `Retry-After` for rate limiting, `503` with `Retry-After` for shed load, `409` for a
> business-rule conflict, `412` when an `If-Match` precondition fails, which is how you do
> optimistic concurrency over HTTP, and `202` when you've accepted work into a queue rather
> than done it. On headers, `ETag` plus `If-None-Match` gives me conditional reads that
> return a `304` with no body, and `Cache-Control` with `stale-while-revalidate` lets a CDN
> serve a slightly stale response instantly while it refreshes in the background — which is
> one of the cheapest availability wins available.

### Mental model

**Method properties. Memorise this table; it comes up constantly.**

| Method | Safe | Idempotent | Cacheable | Has body | Use for |
|---|---|---|---|---|---|
| `GET` | ✅ | ✅ | ✅ | No | Read |
| `HEAD` | ✅ | ✅ | ✅ | No | Metadata / existence check |
| `OPTIONS` | ✅ | ✅ | No | No | CORS preflight, capabilities |
| `PUT` | No | ✅ | No | Yes | Full replace at a known URI |
| `DELETE` | No | ✅ | No | No | Remove |
| `POST` | No | **No** | Rarely | Yes | Create, RPC-ish actions |
| `PATCH` | No | **No*** | No | Yes | Partial update |

*`PATCH` can be made idempotent by design (absolute values, not increments) — say that.

**Safe** means no observable side effect, so a crawler may call it. **Idempotent** means N
identical calls have the same effect as one, so a client or proxy may retry it. Those two
properties are what let infrastructure make decisions on your behalf.

**Status codes with design meaning.**

| Code | Means | When you'd use it in a design |
|---|---|---|
| `200` / `201` | OK / Created | `201` with a `Location` header on create |
| `202 Accepted` | Queued, not done | Async work; return a status URL |
| `204 No Content` | Done, nothing to say | `DELETE` success |
| `304 Not Modified` | Your cached copy is fine | Response to `If-None-Match` — no body, huge saving |
| `400` / `422` | Malformed / semantically invalid | `422` when the JSON parses but the value is illegal |
| `401` / `403` | Not authenticated / not authorised | `401` means "log in"; `403` means "you can't, even logged in" |
| `404` / `410` | Not found / gone permanently | `410` tells caches and crawlers to stop asking |
| `409 Conflict` | Business-rule conflict | Duplicate resource, concurrent state change |
| `412 Precondition Failed` | `If-Match` ETag didn't match | **Optimistic concurrency control over HTTP** |
| `428 Precondition Required` | You must send `If-Match` | Force clients into safe concurrent updates |
| `429 Too Many Requests` | Rate limited | **Always with `Retry-After`** |
| `499` / `408` | Client closed / request timeout | Useful for distinguishing abandonment |
| `500` | Your bug | Never retry automatically |
| `502` / `504` | Bad gateway / upstream timeout | Retryable with backoff |
| `503 Service Unavailable` | Overloaded or draining | **With `Retry-After`**; the correct load-shedding code |

The `429`/`503` + `Retry-After` pattern is backpressure expressed in the protocol: it tells a
well-behaved client exactly how long to wait, which converts a retry storm into a coordinated
back-off. Pair it with jitter — see
[Module 09 — Reliability Patterns](./09_Reliability_Patterns.md).

**Headers that carry design decisions.**

```text
  CACHING
  Cache-Control: public, max-age=60, s-maxage=300,
                 stale-while-revalidate=86400, stale-if-error=604800
      max-age   -> browser TTL          s-maxage -> CDN TTL (overrides)
      private   -> browser only, never a shared cache
      no-cache  -> may store, MUST revalidate    (NOT "don't cache")
      no-store  -> must not write to disk at all (that's "don't cache")
      immutable -> never revalidate; use with content-hashed filenames
      stale-while-revalidate -> serve stale instantly, refresh behind
      stale-if-error         -> serve stale when origin is DOWN  <- free
                                                                  availability
  Vary: Accept-Encoding, Authorization
      -> tells caches which request headers change the response. Forgetting
         Vary is how you leak one user's response to another.

  CONDITIONAL REQUESTS / CONCURRENCY
  ETag: "v3-9f2a"            server -> client, an opaque version
  If-None-Match: "v3-9f2a"   client -> server on READ  -> 304 if unchanged
  If-Match: "v3-9f2a"        client -> server on WRITE -> 412 if it changed
                             ^^^ this is optimistic locking, standardised

  IDEMPOTENCY
  Idempotency-Key: 8e0f...   client-generated UUID; server stores the
                             response and replays it on retry

  BACKPRESSURE
  Retry-After: 30            seconds, or an HTTP-date. Honour it.
```

**Cookies.** Four attributes are non-negotiable on a session cookie:

```text
  Set-Cookie: sid=...; Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=86400

  Secure     only over HTTPS
  HttpOnly   JavaScript cannot read it -> blunts XSS token theft
  SameSite   Lax (default-ish, safe) | Strict (no cross-site at all)
             | None (requires Secure; needed for third-party contexts)
  __Host-    name prefix: browser enforces Secure + Path=/ + no Domain
```

### Enterprise production example

**Stripe's** API is the reference implementation of HTTP idempotency, and it's worth
describing precisely because it's public and every payments interviewer knows it. Clients
send an `Idempotency-Key` header — a client-generated unique value — on `POST` requests.
Stripe stores the result of the first request against that key and, if the same key arrives
again, returns the **original saved response** rather than performing the operation a second
time. Keys are scoped per account and expire after a period, and Stripe surfaces the fact that
a response was a replay so the client can tell.

Why this matters architecturally: the network cannot tell you whether a timed-out `POST`
succeeded. Without idempotency the client's only safe choice is to *not* retry, which converts
every transient network blip into a failed payment. With it, retry becomes safe, and the
retry logic can live in a generic HTTP client rather than in every call site. When you design
any mutating API in an interview, add this header and say why — it is a two-sentence answer
that demonstrates you have shipped something.

### Code

```python
# Idempotency for a FastAPI mutating endpoint, backed by Redis.
# The subtle parts: reserve the key BEFORE doing work (so concurrent
# duplicates collide), and store the RESPONSE, not just a "done" flag.
import hashlib, json
from fastapi import APIRouter, Header, HTTPException, Response

router = APIRouter()
IDEM_TTL = 24 * 3600

@router.post("/payments", status_code=201)
async def create_payment(body: PaymentIn,
                         idempotency_key: str = Header(...),
                         response: Response = None):
    # Bind the key to the request body: the same key with a different body is
    # a client bug, and silently replaying the old response would hide it.
    fingerprint = hashlib.sha256(
        json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()
    slot = f"idem:{idempotency_key}"

    reserved = await redis.set(slot, json.dumps({"state": "in_progress",
                                                 "fp": fingerprint}),
                               nx=True, ex=IDEM_TTL)
    if not reserved:
        prior = json.loads(await redis.get(slot))
        if prior["fp"] != fingerprint:
            raise HTTPException(422, "Idempotency-Key reused with a "
                                     "different request body")
        if prior["state"] == "in_progress":
            # A concurrent duplicate is still running. 409 + Retry-After is
            # honest; returning a fabricated success is not.
            raise HTTPException(409, "Request in progress",
                                headers={"Retry-After": "1"})
        response.headers["Idempotent-Replay"] = "true"
        return prior["response"]

    try:
        result = await charge(body)                    # the real work
    except Exception:
        await redis.delete(slot)                       # allow a genuine retry
        raise
    await redis.set(slot, json.dumps({"state": "done", "fp": fingerprint,
                                      "response": result}), ex=IDEM_TTL)
    return result
```

```javascript
// Conditional GET + optimistic concurrency in one handler (Express).
app.get('/documents/:id', async (req, res) => {
  const doc = await db.getDocument(req.params.id);
  if (!doc) return res.sendStatus(404);

  const etag = `W/"${doc.id}-${doc.version}"`;
  res.set('ETag', etag);
  res.set('Cache-Control',
          'private, max-age=0, must-revalidate, stale-if-error=300');

  if (req.headers['if-none-match'] === etag) return res.sendStatus(304);
  res.json(doc);
});

app.put('/documents/:id', async (req, res) => {
  const expected = req.headers['if-match'];
  if (!expected) {
    return res.status(428).json({ error: 'If-Match header required' });
  }
  // Compare-and-swap in the DB, not in application memory - otherwise you
  // have a read-modify-write race that the ETag only pretends to solve.
  const updated = await db.updateIfVersionMatches(
    req.params.id, parseVersion(expected), req.body,
  );
  if (!updated) return res.sendStatus(412);   // someone else wrote first
  res.set('ETag', `W/"${updated.id}-${updated.version}"`).json(updated);
});
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| `ETag` + `If-None-Match` | Response is tiny and cheap to generate | You still pay the round trip; you save the body |
| `If-Match` for concurrency | Single-writer resources | Clients must handle `412` and re-read |
| `Idempotency-Key` | Read-only endpoints | A key store with TTL, and the concurrency case above |
| `stale-while-revalidate` | Data must be exact (balances, inventory) | Users can see stale data for the SWR window |
| `202 Accepted` + status URL | The caller genuinely needs the result now | Clients must poll or subscribe; more moving parts |

### Follow-ups they will ask

**Q: A client times out on `POST /payments` and retries. Walk me through what happens.**
A: Without an idempotency key, this is a double charge, because the timeout tells the client
nothing about whether the server processed the request — the response may simply have been
lost on the way back. With an `Idempotency-Key`, the retry hits the stored record for that
key: if the first attempt completed, the server returns the original response verbatim, so
the client sees exactly one payment; if it's still in flight, the server returns `409` with a
`Retry-After` rather than starting a second charge. The subtlety is that the key must be
reserved atomically *before* the work starts, with `SET NX`, otherwise two concurrent
duplicates both see "no record" and both charge.

**Q: What's the difference between `no-cache` and `no-store`?**
A: They're named almost backwards. `no-cache` means the response *may* be stored, but the
cache must revalidate with the origin before serving it — so with an `ETag` you get a cheap
`304` and no body transfer. `no-store` means it must not be written down anywhere, which is
what you want for a response containing a bearer token or PII. Most people who write
`no-cache` intending "never cache this" actually want `no-store, private`.

**Q: How do you rate limit in a way clients can cooperate with?**
A: Return `429` with a `Retry-After` in seconds, plus the `RateLimit-Limit`,
`RateLimit-Remaining` and `RateLimit-Reset` headers so a well-behaved client can pace itself
*before* it gets rejected. The critical part is that the client must add jitter to whatever
`Retry-After` says — if you tell ten thousand clients to retry in 30 seconds, they all retry
at exactly 30 seconds and you get the same thundering herd you were shedding. So: server
publishes the budget, client randomises within it.

**Q: When would you return `409` versus `412`?**
A: `412` is specifically for a failed precondition the client sent — they passed
`If-Match: "v3"`, the resource is now at v4, so the update is rejected and the client should
re-read and retry. `409` is for a conflict with business state that isn't expressible as a
precondition: creating a user with an email that already exists, or cancelling an order
that's already shipped. The practical difference is what the client should do — `412` means
"re-read and retry automatically", `409` usually means "stop and surface this to a human".

**Q: Your API returns 200 with `{"error": ...}` in the body. What's wrong with that?**
A: Every piece of infrastructure between you and the client now believes the request
succeeded. Load balancer error-rate metrics say zero, the CDN happily caches the error
response, client HTTP libraries don't trigger their retry logic, and your own SLO dashboard
is lying to you. Status codes are the only error signal that proxies, CDNs, tracing systems
and client libraries all understand, so the error must be in the code and the detail in the
body.

### Red flags — do not say this

- ❌ "`POST` is fine for everything." → ✅ "`GET` for reads so it's cacheable and retryable; `POST` with an `Idempotency-Key` for mutations so a timeout retry is safe."
- ❌ "We return 200 and put the error in the body." → ✅ "Status codes carry the error, because that's what proxies, CDNs and client retry logic act on."
- ❌ "We'll add a `version` field and check it in the app." → ✅ "`ETag` plus `If-Match`, with a compare-and-swap in the database and a `412` on mismatch — that's optimistic concurrency the whole stack understands."

---

## 2.8 WebSockets — and the scaling problem

> **One-liner:** A WebSocket is a persistent, bidirectional, full-duplex connection obtained
> by upgrading an HTTP request — and the moment you have more than one server, the connection
> being *stateful* is the entire engineering problem.

### Say this in the interview

> A WebSocket starts as a normal HTTP GET with an `Upgrade: websocket` header; the server
> answers `101 Switching Protocols` and from then on the same TCP connection carries binary
> frames in both directions with about two to fourteen bytes of framing overhead per message,
> versus several hundred bytes of headers for an HTTP request. That's why it's the right
> choice when both sides send frequently and latency matters — collaborative editing,
> multiplayer, trading, live cursors. The hard part isn't the protocol, it's that the
> connection is stateful and pinned to one process. If user A is connected to node one and
> user B to node two, and A sends B a message, node one has no way to reach B's socket. So I
> need a message bus between nodes — Redis Pub/Sub is the usual first answer, with each node
> subscribing to the channels for the rooms its connected clients care about, and Kafka or
> NATS when I need durability or replay. I also need to plan for connection limits — a Node
> process is comfortable somewhere in the tens of thousands of idle connections and far fewer
> if they're chatty — for load balancer idle timeouts, which will silently kill an idle
> socket at sixty seconds on a default ALB, and for the reconnect storm when a node dies and
> thirty thousand clients try to reconnect at the same instant. That last one is why
> exponential backoff with jitter is mandatory, not optional.

### Mental model

**The upgrade handshake.**

```text
  Client                                        Server
    │  GET /ws HTTP/1.1                           │
    │  Host: api.example.com                      │
    │  Upgrade: websocket                         │
    │  Connection: Upgrade                        │
    │  Sec-WebSocket-Key: dGhlIHNhbXBsZQ==        │
    │  Sec-WebSocket-Version: 13                  │
    │────────────────────────────────────────────►│
    │                                              │
    │  HTTP/1.1 101 Switching Protocols           │
    │  Upgrade: websocket                          │
    │  Sec-WebSocket-Accept: s3pPLM...            │
    │◄────────────────────────────────────────────│
    │                                              │
    │◄════════ binary frames, both ways ═════════►│
    │     2-14 bytes of framing per message        │
```

Note it is an HTTP/1.1 upgrade. That has consequences: some corporate proxies do not pass
`Upgrade` through, and the newer `Extended CONNECT` mechanism is what carries WebSockets over
HTTP/2 and HTTP/3 where supported.

**The scaling problem, drawn.**

```text
   WITHOUT a bus - broken as soon as you have 2 nodes
   ┌────────┐        ┌──────────┐
   │ user A │───────►│  node 1  │  A sends to room R
   └────────┘        └──────────┘
                          ╳  node 1 has no socket for B
   ┌────────┐        ┌──────────┐
   │ user B │───────►│  node 2  │  B is in room R but never hears it
   └────────┘        └──────────┘

   WITH a fan-out bus
   ┌────────┐    ┌──────────┐  PUBLISH room:R  ┌───────────────┐
   │ user A │───►│  node 1  │─────────────────►│ Redis Pub/Sub │
   └────────┘    └──────────┘                  │  (or NATS,    │
                                                │   Kafka)      │
   ┌────────┐    ┌──────────┐  SUBSCRIBE room:R└───────┬───────┘
   │ user B │◄───│  node 2  │◄────────────────────────┘
   └────────┘    └──────────┘
   Each node subscribes ONLY to rooms it currently holds sockets for.
```

**The five things that actually break.**

1. **Stickiness.** The connection lives on one node for its lifetime. An L4 balancer is fine;
   an L7 balancer needs to support `Upgrade` and long-lived connections. There's no
   "sticky session" problem *within* a connection, but there is one across reconnects if you
   keep per-connection state in local memory — so don't.
2. **Idle timeouts.** An AWS ALB defaults to a **60-second idle timeout** and will close a
   silent WebSocket. This is the single most common "WebSockets randomly disconnect" bug. Fix
   it with application-level pings well inside the timeout, and raise the LB timeout.
3. **Connection limits per node.** File descriptors (`ulimit -n`), kernel memory per socket,
   and heap per connection in your runtime. A Node.js process holding idle connections is
   typically fine into the tens of thousands; the ceiling drops sharply with message rate,
   because CPU, not memory, becomes the binding constraint. Measure with your real message
   size and rate; don't quote a number you haven't tested.
4. **Fan-out amplification.** One message to a 50,000-member room is 50,000 socket writes. If
   those members are spread over 20 nodes, that's one Pub/Sub message and 50,000 writes
   distributed 2,500 per node — fine. If they're all on one node, that node melts. This is
   why large rooms need to be sharded across nodes deliberately.
5. **The reconnect storm.** A node dies with 30,000 connections; all 30,000 clients reconnect
   within a second, hit the remaining nodes, re-authenticate, re-subscribe and re-fetch
   missed state. Without jittered backoff this cascades and takes down the rest of the fleet.

**Heartbeats.** WebSocket has protocol-level `ping`/`pong` control frames. Use them:

```text
  server ──ping──► client      every 30 s
  client ──pong──► server      library replies automatically
  server: if no pong within 2 intervals -> terminate() the socket

  Why: TCP will not tell you about a half-open connection. A client that
  lost power looks identical to an idle one until you try to write. Without
  heartbeats you leak sockets and deliver messages into the void.
```

**Reconnection with backoff and resume.**

```text
  attempt:  1     2     3     4     5     6+
  base:    0.5s  1s    2s    4s    8s    16s (cap 30s)
  actual:  base * random(0.5, 1.5)     <- JITTER IS THE POINT

  On reconnect, send the last event id you processed. Server replays
  from a bounded buffer (e.g. last 1000 events / 5 minutes) or tells the
  client to do a full resync. Without this, every reconnect is a cold start.
```

### Enterprise production example

**Discord** runs one of the largest WebSocket deployments in the world and has published real
numbers. Their gateway is written in Elixir on the BEAM VM, with **one lightweight process per
connected user** and a process per guild (server). As of the Elixir team's 2020 write-up they
had crossed **12 million concurrent users, pushing more than 26 million WebSocket events per
second to clients**, running on a cluster of **400–500 Elixir machines** — maintained by a
chat infrastructure team of **five engineers**.

Three specific engineering problems and their fixes are worth quoting:

**Fan-out concentration.** A single guild process broadcasting to every member becomes a
bottleneck, so Discord built **Manifold** to distribute the send across nodes: the guild
process sends one message per *node* rather than one per *recipient*, and each node fans out
locally. That turns an N-recipient broadcast into an M-node broadcast, where M is a few
hundred instead of hundreds of thousands.

**Large-room data structures.** Adding a member to a 100,000-member list meant rebuilding a
100,001-element list. Their Elixir implementation topped out around **250,000 members per
guild**. They replaced the hot data structure with a Rust `SortedSet` via Rustler, benchmarked
at **0.61 µs best case and 3.68 µs worst case across sets from 5,000 to 1,000,000 items**, and
scaled past the limit to serve **11 million concurrent users**.

**Bandwidth.** In 2024 Discord published how they cut gateway traffic by nearly 40%. Moving
from zlib to **streaming zstandard with a custom dictionary** raised the compression ratio from
about 6 to nearly 10 and dropped a representative payload from **270 bytes to 166 bytes**.
Separately, they found one dispatch type, `passive_update_v1`, was **over 30% of all gateway
traffic despite being only about 2% of messages**, because it re-sent full snapshots. Replacing
it with a delta-only `PASSIVE_UPDATE_V2` took that dispatch from **35% of gateway bandwidth
down to 5%** — a 20% cluster-wide reduction on its own.

The transferable lessons: **fan-out per node, not per recipient**; **profile bytes-on-the-wire
by message type, because one chatty message type usually dominates**; and **send deltas, not
snapshots**.

### Code

A horizontally scalable WebSocket server in Node.js. This is the shape to draw and describe:
local socket registry, Redis Pub/Sub for cross-node fan-out, heartbeats, and per-room
subscription so a node only receives traffic it can deliver.

```javascript
// server.js - horizontally scalable WebSocket gateway (Node 20+, ws + ioredis)
import { WebSocketServer } from 'ws';
import Redis from 'ioredis';
import { randomUUID } from 'node:crypto';

const NODE_ID = process.env.HOSTNAME ?? randomUUID();
const HEARTBEAT_MS = 30_000;

const pub = new Redis(process.env.REDIS_URL);
const sub = new Redis(process.env.REDIS_URL);   // a subscriber connection
                                                // cannot issue other commands

const wss = new WebSocketServer({ noServer: true, maxPayload: 64 * 1024 });

/** roomId -> Set<WebSocket> held by THIS process only. */
const localRooms = new Map();

async function join(ws, roomId) {
  if (!localRooms.has(roomId)) {
    localRooms.set(roomId, new Set());
    await sub.subscribe(`room:${roomId}`);      // subscribe once per node,
  }                                             // not once per client
  localRooms.get(roomId).add(ws);
  ws.rooms.add(roomId);
  // Presence: a TTL'd set so a hard crash expires membership automatically.
  await pub.zadd(`presence:${roomId}`, Date.now(), ws.userId);
}

async function leave(ws, roomId) {
  const set = localRooms.get(roomId);
  if (!set) return;
  set.delete(ws);
  await pub.zrem(`presence:${roomId}`, ws.userId);
  if (set.size === 0) {
    localRooms.delete(roomId);
    await sub.unsubscribe(`room:${roomId}`);    // stop paying for traffic we
  }                                             // can no longer deliver
}

// Cross-node delivery. One Redis message per room; each node fans out to its
// own sockets. This is the "fan out per node, not per recipient" pattern.
sub.on('message', (channel, payload) => {
  const roomId = channel.slice('room:'.length);
  const sockets = localRooms.get(roomId);
  if (!sockets) return;
  const { origin, data } = JSON.parse(payload);
  for (const ws of sockets) {
    if (ws.readyState !== ws.OPEN) continue;
    // Backpressure: never queue unboundedly into a slow client.
    if (ws.bufferedAmount > 1 << 20) { ws.terminate(); continue; }
    if (ws.userId !== origin) ws.send(data);
  }
});

wss.on('connection', (ws, req) => {
  ws.userId = req.userId;             // set during the upgrade auth step
  ws.rooms = new Set();
  ws.isAlive = true;
  ws.on('pong', () => { ws.isAlive = true; });

  ws.on('message', async (raw) => {
    let msg;
    try { msg = JSON.parse(raw); } catch { return ws.close(1003, 'bad json'); }
    switch (msg.type) {
      case 'join':  return join(ws, msg.room);
      case 'leave': return leave(ws, msg.room);
      case 'say':
        if (!ws.rooms.has(msg.room)) return;            // authorise every send
        return pub.publish(`room:${msg.room}`, JSON.stringify({
          origin: ws.userId,
          data: JSON.stringify({ type: 'say', room: msg.room,
                                 from: ws.userId, text: msg.text,
                                 id: randomUUID(), ts: Date.now() }),
        }));
    }
  });

  ws.on('close', async () => {
    for (const r of ws.rooms) await leave(ws, r);
  });
});

// Heartbeat: TCP will not tell you a client vanished. Ping well inside the
// load balancer idle timeout (ALB defaults to 60s - this is THE bug).
setInterval(() => {
  for (const ws of wss.clients) {
    if (!ws.isAlive) { ws.terminate(); continue; }
    ws.isAlive = false;
    ws.ping();
  }
}, HEARTBEAT_MS).unref();

// Graceful shutdown: close with 1001 so clients back off politely instead of
// treating it as a crash and reconnecting instantly.
process.on('SIGTERM', async () => {
  for (const ws of wss.clients) ws.close(1001, 'server shutting down');
  setTimeout(() => process.exit(0), 5_000);
});
```

```javascript
// client.js - reconnection with exponential backoff AND jitter.
// The jitter is the whole point: without it, N clients reconnect in lockstep.
function connect(url, { onEvent }) {
  let attempt = 0, lastEventId = null, ws;

  const open = () => {
    ws = new WebSocket(`${url}?since=${lastEventId ?? ''}`);
    ws.onopen = () => { attempt = 0; };
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      lastEventId = msg.id;                 // resume token for the next connect
      onEvent(msg);
    };
    ws.onclose = () => {
      const base = Math.min(500 * 2 ** attempt++, 30_000);
      const delay = base * (0.5 + Math.random());   // jitter: 0.5x - 1.5x
      setTimeout(open, delay);
    };
  };
  open();
  return () => ws?.close(1000, 'client done');
}
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Both directions send frequently (chat, cursors, games) | Server-to-client only (use SSE) | Stateful connections, a fan-out bus, reconnect handling |
| Message rate is high and per-message overhead matters | A poll every 30 s would do | Complexity that must be justified by the latency requirement |
| Binary payloads | Text-only and low volume | Custom framing and versioning of your own protocol |
| You control the client | Corporate proxies that strip `Upgrade` | Needs a long-polling fallback (what Socket.IO gives you) |

### Follow-ups they will ask

**Q: You have 1 million concurrent WebSocket connections. How do you deploy a new version without dropping everyone?**
A: Drain rather than cut. On `SIGTERM` the node stops accepting new connections, then closes
existing ones **gradually** — with a close code of `1001` (going away) and spread over
several minutes rather than all at once, because a simultaneous close is the reconnect storm.
Clients back off with jitter and land on the new nodes. To make that cheap, connection state
must be recoverable: authentication from a token, room membership from Redis, and missed
messages from a bounded replay buffer keyed on a last-event id. If reconnection requires a
cold rebuild of per-user state, a rolling deploy becomes a self-inflicted outage.

**Q: A node holding 30,000 connections crashes. What happens in the next 10 seconds?**
A: All 30,000 clients detect the close and reconnect. Without jitter, they arrive in a spike
that hits the remaining nodes simultaneously — 30,000 TLS handshakes, 30,000 auth token
validations, 30,000 Redis subscribe operations and 30,000 state resyncs. That spike is very
likely to knock over another node, which doubles the problem. The mitigations are jittered
backoff on the client, a connection-rate limiter at the gateway that sheds with `503` plus
`Retry-After` rather than queueing, capacity headroom sized for N−1 nodes, and making resync
cheap by using a last-event-id replay instead of a full snapshot.

**Q: Why does Redis Pub/Sub eventually stop being the right fan-out bus?**
A: Because it's fire-and-forget with no durability and no backpressure. A node that is
disconnected for two seconds simply misses those messages — there's no replay — and a slow
subscriber gets disconnected when its output buffer limit is exceeded. It also broadcasts to
every node subscribed to a channel, so at very high channel counts the subscription
bookkeeping itself becomes the cost. The upgrade path is Redis Streams if you want a
consumer-group model with replay inside Redis, NATS JetStream for a purpose-built low-latency
bus, or Kafka when you need durable ordered replay and are willing to accept higher latency.
Discord's answer was neither — they built node-level fan-out on top of the BEAM's own
distribution.

**Q: How do you authenticate a WebSocket?**
A: During the HTTP upgrade, not after, and not via a query-string token if you can avoid it —
query strings end up in access logs and proxy logs. The clean pattern is a short-lived ticket:
the client calls an authenticated HTTP endpoint to mint a single-use token with a 30-second
TTL, then opens the WebSocket presenting that ticket, and the server validates and burns it
during the upgrade. Browsers can't set custom headers on a `WebSocket` constructor, which is
why the ticket pattern exists. Then you need re-authorisation over time: a long-lived socket
outlives the access token, so either the server enforces a max connection lifetime or the
client refreshes credentials over the socket and the server re-checks.

**Q: How many WebSocket connections can one Node.js process hold?**
A: It depends entirely on message rate, and I'd want to measure rather than quote. Idle
connections are cheap — mostly a file descriptor plus socket buffers plus a few kilobytes of
heap — so tens of thousands is reasonable. But Node is single-threaded for JavaScript
execution, so once connections are chatty, CPU becomes the constraint long before memory does:
serialising and writing 26 million events a second is not something one Node process does.
That is exactly why Discord chose the BEAM, which schedules millions of lightweight processes
across cores pre-emptively. For a Node deployment I'd plan on many small processes behind an
L4 balancer rather than a few big ones, and I'd size from a load test at my actual message
rate.

### Red flags — do not say this

- ❌ "WebSockets scale horizontally like any HTTP service." → ✅ "The connection is pinned to one process, so cross-node delivery needs a bus — Redis Pub/Sub to start, and I'd fan out per node rather than per recipient."
- ❌ "We'll use WebSockets for the notification feed." → ✅ "Notifications are server-to-client only, so SSE gives me the same latency over plain HTTP with no sticky state."
- ❌ "The client reconnects when it drops." → ✅ "Exponential backoff with jitter and a last-event-id resume — otherwise a node failure turns into a synchronised reconnect storm."
- ❌ Forgetting heartbeats. → ✅ "Ping every 30 seconds, terminate after two missed pongs, and keep the interval well under the load balancer's 60-second idle timeout."

---

## 2.9 Polling vs long polling vs SSE vs WebSockets

> **One-liner:** Pick the weakest mechanism that meets the latency requirement — polling if
> minutes are fine, SSE if the data only flows server-to-client, WebSockets only when the
> client genuinely needs to push too.

### Say this in the interview

> I choose by asking two questions: how fresh does the data need to be, and does the client
> need to send anything mid-stream. If staleness of thirty seconds is acceptable, short
> polling is right — it's stateless, it works through every proxy, and it costs me nothing in
> operational complexity. If I need near-real-time but the data only flows one way, from
> server to client, Server-Sent Events is the answer: it's plain HTTP with a
> `text/event-stream` response that stays open, the browser's `EventSource` reconnects
> automatically and replays from `Last-Event-ID`, and because it's ordinary HTTP it passes
> through every load balancer, CDN and corporate proxy without special handling and needs no
> sticky sessions. That's the right transport for LLM token streaming, which is why every
> major provider — OpenAI, Anthropic, Google — streams over SSE rather than WebSockets. I'd
> only reach for WebSockets when the client genuinely pushes during the session: collaborative
> editing, live cursors, multiplayer, voice signalling, or an agent where the user interrupts
> mid-generation. Long polling I treat as a fallback for environments where streaming is
> broken, not as a first choice. The reason I care about this ordering is that each step up
> costs real operational complexity — WebSockets add stateful connections, a fan-out bus and
> reconnect logic — and I don't want to pay that for a one-way stream.

### Mental model

```text
  SHORT POLLING                     latency = interval/2 average
   C ──"anything?"──► S   "no"      cost = clients / interval  QPS, always
   ...wait 5s...                    100k clients @ 5s = 20,000 QPS of "no"
   C ──"anything?"──► S   "no"
   C ──"anything?"──► S   [data]

  LONG POLLING                      latency ~ 0
   C ──"anything?"──► S             server HOLDS the request open
        ...30s, or until data...    up to 30-60s per request
   S ─────────[data]──► C           client immediately re-asks
   C ──"anything?"──► S             one connection per client, constantly

  SSE  (Server-Sent Events)         latency ~ 0, one-way
   C ──GET, Accept: text/event-stream──► S
   S ══ data: {...}\n\n ═════════════► C   stays open indefinitely
   S ══ data: {...}\n\n ═════════════► C
   S ══ : keepalive\n\n ═════════════► C   comment frame every 15-30s
        auto-reconnect + Last-Event-ID replay, built into the browser

  WEBSOCKET                         latency ~ 0, two-way
   C ──GET Upgrade: websocket──► S
   S ──101 Switching Protocols──► C
   C ◄══════ frames both directions ══════► S
```

**The decision table.**

| | Short polling | Long polling | SSE | WebSocket |
|---|---|---|---|---|
| Direction | C→S | C→S | **S→C only** | Both |
| Latency | interval/2 | ~0 | ~0 | ~0 |
| Protocol | Plain HTTP | Plain HTTP | Plain HTTP | HTTP upgrade → frames |
| Stateful server? | No | Semi (held request) | Semi (held response) | **Yes** |
| Sticky routing needed? | No | No | **No** | Effectively yes |
| Auto-reconnect | N/A | Manual | **Built in (`EventSource`)** | Manual |
| Replay on reconnect | N/A | Manual | **Built in (`Last-Event-ID`)** | Manual |
| Binary payload | Yes | Yes | **No — UTF-8 text only** | Yes |
| Per-message overhead | Full HTTP headers | Full HTTP headers | ~10 bytes | 2–14 bytes |
| Works through corporate proxies | Always | Always | Almost always | Sometimes |
| Browser connection limit | n/a | n/a | **6 per origin on HTTP/1.1** | 255 |
| Server cost at 100k clients | 20k QPS @ 5 s | 100k held requests | 100k held responses | 100k sockets |
| Operational complexity | 1 | 2 | 3 | 8 |

**The cost math that decides it.** For 100,000 clients:

```text
  Short poll @ 5 s:  100,000 / 5 = 20,000 QPS.
    Each request: ~800 B of headers up, ~300 B down, TLS resumption, a
    handler invocation, an auth check, probably a cache lookup.
    ~20,000 x 1.1 KB = 22 MB/s of pure overhead to say "nothing new".
    And the average user still waits 2.5 s for an update.

  SSE:               100,000 open responses, ~0 QPS.
    Traffic only when there IS data. Memory is the constraint, not CPU.
    Latency is ~0.

  Short polling is cheaper ONLY when updates are rarer than the poll
  interval AND you can tolerate the staleness. That is a real case -
  a dashboard refreshed every 60 s should just poll.
```

**When SSE is specifically the right answer — and why it matters for LLM work.**

Token streaming from a language model is the canonical SSE shape: the client sends one
request and then only receives, for several seconds, until the stream ends. Every major
provider — OpenAI, Anthropic, Google — streams completions over SSE, and the Model Context
Protocol and agent-to-agent protocols have converged on it too. The reasons are all
architectural rather than performance:

```text
  1. It is plain HTTP. Your existing auth middleware, rate limiter, LB,
     CDN, WAF and tracing all keep working unchanged.
  2. It is stateless. No sticky sessions, no connection registry, no
     cross-node fan-out bus. Any pod can serve any stream.
  3. Reconnect and replay are in the browser. EventSource retries with a
     server-controlled interval and resends Last-Event-ID for free.
  4. The direction matches the workload. Bidirectionality would be unused.
```

**The three production gotchas** — these are what separate someone who has shipped streaming
from someone who has read about it:

```text
  1. PROXY BUFFERING. nginx buffers a response until it sees Content-Length
     or the connection closes. SSE sends neither, so the proxy holds every
     token and delivers the whole answer at the end - streaming silently
     becomes batching. Fix: `proxy_buffering off` AND send the response
     header `X-Accel-Buffering: no` as defence in depth.
  2. IDLE TIMEOUTS. A model that thinks for 100 s before its first token
     looks idle. Cloudflare and most LBs will cut the connection and may
     inject an HTML error page into your event stream. Fix: send a comment
     heartbeat (`: ping\n\n`) every 15 s and raise the read timeout.
  3. HTTP/1.1's SIX-CONNECTIONS-PER-ORIGIN LIMIT. Six open SSE streams and
     the tab is wedged - no other request to that origin can proceed. Fix:
     serve over HTTP/2, where streams are multiplexed and the limit is
     effectively gone.
```

Cross-link: [Module 14 — LLM System Design](./14_AI_LLM_System_Design.md) covers TTFT budgets,
partial-JSON parsing, cancellation propagation and multi-provider stream aggregation.

### Enterprise production example

The strongest signal here is convergence: **OpenAI, Anthropic and Google all stream LLM
completions over Server-Sent Events**, and the emerging agent protocols (MCP, A2A) adopted
SSE as their streaming transport too. None of these organisations lacks the engineering
capacity to build a WebSocket gateway. They chose SSE because the streaming workload is
unidirectional and SSE is the transport that requires no change to any existing HTTP
infrastructure — the same reason that makes it right for your own LLM gateway.

The production pattern that has emerged around this is worth naming: **SSE for the data plane,
plain REST for the control plane.** Tokens stream down over SSE; "cancel this generation",
"approve this tool call" and "here's more context" go up as ordinary `POST` requests
correlated by a stream ID. That keeps the high-volume path stateless and horizontally
scalable, and confines statefulness to a small control surface. Reach for WebSockets only
when the interaction is genuinely conversational mid-generation — live voice, or an agent UI
that pushes events into a running generation.

### Code

SSE done correctly in FastAPI, with all three gotchas handled.

```python
# FastAPI SSE endpoint for LLM token streaming.
import asyncio, json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()
HEARTBEAT_S = 15

async def sse_stream(request: Request, prompt: str, resume_from: str | None):
    seq = int(resume_from) if resume_from else 0
    queue: asyncio.Queue = asyncio.Queue(maxsize=256)   # bounded: backpressure

    async def produce():
        try:
            async for delta in llm.stream(prompt, skip=seq):
                await queue.put(delta)                  # blocks if consumer
        finally:                                        # is slow - correct
            await queue.put(None)

    task = asyncio.create_task(produce())
    try:
        while True:
            try:
                delta = await asyncio.wait_for(queue.get(), HEARTBEAT_S)
            except asyncio.TimeoutError:
                yield ": ping\n\n"        # comment frame: keeps proxies and
                continue                  # load balancers from timing us out
            if delta is None:
                yield "event: done\ndata: {}\n\n"
                return
            seq += 1
            # id: lets EventSource resume via Last-Event-ID after a drop.
            yield f"id: {seq}\nevent: token\ndata: {json.dumps(delta)}\n\n"
            # Stop generating (and stop paying the provider) if the client left.
            if await request.is_disconnected():
                return
    finally:
        task.cancel()

@router.get("/chat/stream")
async def chat_stream(request: Request, prompt: str):
    return StreamingResponse(
        sse_stream(request, prompt, request.headers.get("last-event-id")),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # nginx: do not buffer this response
        },
    )
```

```nginx
# The nginx half. Without proxy_buffering off, the code above streams
# perfectly into a buffer and the user sees nothing until it completes.
location /chat/stream {
    proxy_pass              http://api;
    proxy_http_version      1.1;
    proxy_set_header        Connection '';
    proxy_buffering         off;
    proxy_cache             off;
    proxy_read_timeout      300s;   # generations are long; default 60s cuts
    chunked_transfer_encoding on;
}
```

```javascript
// Browser side. EventSource gives you reconnect + Last-Event-ID for free;
// use fetch+ReadableStream only when you need POST bodies or custom headers.
const es = new EventSource('/chat/stream?prompt=' + encodeURIComponent(p));
es.addEventListener('token', (e) => render(JSON.parse(e.data)));
es.addEventListener('done', () => es.close());
es.onerror = () => { /* EventSource auto-retries; close() to stop it */ };
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Short polling: staleness of 30 s+ is fine | Latency matters | Wasted QPS proportional to client count |
| Long polling: need low latency, streaming is blocked | You can use SSE | A held request per client and manual reconnect |
| **SSE: one-way stream, browser client** | You need binary, or client→server mid-stream | Text only; 6-connection limit on HTTP/1.1 |
| WebSocket: genuine bidirectional traffic | The client only receives | Stateful nodes, fan-out bus, reconnect storms |

### Follow-ups they will ask

**Q: Why not just use WebSockets for LLM token streaming? It's real-time either way.**
A: Because bidirectionality is the only thing WebSockets add here, and the workload doesn't
use it — the client sends one prompt and then only receives. What it *costs* is significant:
the connection becomes stateful, so I need sticky routing or a connection registry, my
existing HTTP auth middleware and rate limiter no longer apply cleanly, corporate proxies that
strip `Upgrade` break the feature entirely, and I have to implement reconnection and replay
myself instead of getting them from `EventSource`. SSE gives identical latency with none of
that. When I do need mid-generation interaction — user interruption, live voice — I'd add a
control-plane REST endpoint or a WebSocket alongside the SSE data plane, rather than moving
the token stream onto it.

**Q: Your SSE stream works locally and delivers everything at once in production. What's wrong?**
A: A proxy is buffering the response. nginx buffers until it sees a `Content-Length` or the
connection closes, and SSE provides neither, so the whole generation accumulates and arrives
as one burst. The fix is `proxy_buffering off` in the location block plus `X-Accel-Buffering:
no` as a response header so it works even where I don't control the nginx config. If there's a
CDN in front, check it too — many buffer by default and need `no-transform` in `Cache-Control`
or an explicit bypass rule for `text/event-stream`.

**Q: 100,000 clients need updates within 2 seconds. Compare polling and SSE with numbers.**
A: Polling at a 2-second interval is 50,000 QPS, and the vast majority of those responses are
"nothing new" — at roughly a kilobyte of request and response overhead each, that's about
50 MB/s of pure waste, plus 50,000 auth checks and cache lookups per second, and the average
user still waits a second. SSE is 100,000 open responses with essentially zero request rate;
traffic flows only when there's actually an update, and latency is near zero. The trade is
that SSE turns a CPU-and-QPS problem into a memory-and-file-descriptor problem, which is much
cheaper — I'd budget roughly 10–50 KB per idle connection, so 100,000 connections is a few
gigabytes spread over a handful of pods.

**Q: What breaks about SSE at scale that people don't expect?**
A: Three things. Connections are long-lived, so a rolling deploy severs every stream at once
unless you drain gradually — and unlike WebSockets, `EventSource` reconnects instantly and
automatically, so a careless deploy produces a perfectly synchronised reconnect spike. Second,
each open stream holds a worker or connection slot, so an async framework is mandatory;
100,000 streams on a thread-per-request server is impossible. Third, `EventSource` cannot send
a request body or custom headers, so anything needing a large prompt or a bearer header ends
up using `fetch` with a `ReadableStream` instead — at which point you've given up the free
reconnect and have to implement it yourself.

**Q: When is short polling genuinely the best answer?**
A: When the update rate is lower than the acceptable staleness, and simplicity has value.
A dashboard refreshed every 60 seconds, a job-status page checked while a user waits, a
mobile app pulling on foreground — all of these are correctly served by polling. It's
stateless, it survives any proxy, it works when the app is backgrounded, it needs no
reconnect logic, and its failure mode is "slightly stale" rather than "silently
disconnected". Choosing polling deliberately and saying why is a stronger answer than
reaching for WebSockets by reflex.

### Red flags — do not say this

- ❌ "WebSockets for real-time, obviously." → ✅ "One-way stream, so SSE — same latency, plain HTTP, no sticky sessions, free reconnect. WebSockets only if the client pushes mid-stream."
- ❌ "SSE is old, WebSockets replaced it." → ✅ "SSE is what every major LLM provider uses for token streaming, precisely because it's ordinary HTTP."
- ❌ "Long polling is basically the same as SSE." → ✅ "Long polling is one response per event; SSE is one response carrying many events, with built-in reconnect and `Last-Event-ID` replay."
- ❌ Forgetting proxy buffering. → ✅ "`proxy_buffering off` plus `X-Accel-Buffering: no`, or your streaming endpoint silently becomes a batch endpoint in production."

---

## 2.10 Real-time at scale — fan-out in production

> **One-liner:** Real-time at scale is a fan-out problem, not a connection problem — the
> connection count is the easy part, and the message-amplification factor is what actually
> decides your architecture.

### Say this in the interview

> Once you have real-time working, the thing that determines whether it scales is
> amplification: how many socket writes does one logical event produce. A user posting in a
> hundred-thousand-member room isn't one message, it's a hundred thousand writes, and if
> those recipients are spread across twenty nodes the naive implementation sends a hundred
> thousand messages across the bus. The fix that every large system converges on is to fan
> out per node rather than per recipient — publish one message per node that holds relevant
> connections, and let that node do its local writes. Discord built exactly this and calls it
> Manifold. The second thing that matters is what you send. Discord found that one dispatch
> type was over thirty percent of all their gateway bandwidth while being about two percent
> of messages, because it re-sent full snapshots instead of deltas — switching to deltas took
> it from thirty-five percent of bandwidth down to five. So my checklist for a real-time
> system is: fan out per node, send deltas not snapshots, compress with a shared dictionary
> because these payloads are small and repetitive, shard large rooms deliberately, and treat
> presence as a TTL'd set so a crashed node's users expire instead of appearing online
> forever.

### Mental model

**Amplification is the number that matters.**

```text
  writes_per_second = events_per_second x average_recipients_per_event

  Small team chat:   10 events/s x 8 members       =        80 writes/s
  Large community:   50 events/s x 100,000 members = 5,000,000 writes/s
  Live sports feed:   1 event/s  x 2,000,000 fans  = 2,000,000 writes/s

  The connection count barely moved; the write rate moved 5 orders of
  magnitude. Design for the amplification factor, not the user count.
```

**Fan-out per node, not per recipient.**

```text
  NAIVE: publisher enumerates recipients
    1 event -> 100,000 bus messages -> 100,000 writes
    The bus is now the bottleneck and the publisher does O(N) work.

  PER-NODE: publisher enumerates NODES
                            ┌──────────┐
    1 event ──► room proc ─►│  bus     │─► node 1 -> 5,000 local writes
                (1 msg per  │ 20 msgs  │─► node 2 -> 5,000 local writes
                 node)      └──────────┘─► ...
                                         ─► node 20 -> 5,000 local writes

    Bus traffic: 100,000 -> 20 messages. Local writes are cheap and
    parallel. This is Discord's "Manifold".
```

**The four levers, in order of yield:**

1. **Fan out per node.** Turns O(recipients) bus traffic into O(nodes).
2. **Send deltas, not snapshots.** Almost every real-time payload is mostly unchanged from the
   last one.
3. **Compress with a shared dictionary.** Real-time payloads are small and highly repetitive
   — the same field names in every frame — so a dictionary-trained compressor beats generic
   compression substantially at these sizes.
4. **Shard large rooms.** A 500,000-member room should not have all its members on one node;
   distribute deliberately so no single process owns an unbounded fan-out.

**Presence** is the sub-problem that catches people out. Naively, presence is "who is
connected", which means a write on every connect and disconnect and a read on every room
join. At scale: store it as a **TTL'd or scored set** (`ZADD presence:room <now> <user>`) that
clients refresh via heartbeat, so a crashed node's users expire automatically instead of
appearing online forever; **debounce** transitions so a flaky mobile connection doesn't emit
an online/offline storm; and **aggregate** — send "1,204 online" rather than a list, unless
the client actually renders names.

### Enterprise production example

**Discord**, with published numbers throughout (see 2.8 for the full detail):

| Fact | Number | Source |
|---|---|---|
| Concurrent users | 12 M+ | Elixir team write-up, 2020 |
| WebSocket events pushed to clients | **26 M+ per second** | same |
| Elixir machines for chat messaging | 400–500 | same |
| Chat infrastructure team size | **5 engineers** | same |
| Largest guilds | approaching 600,000 members | same |
| Concurrently active in one large guild | 200,000+ | same |
| Guild size ceiling before the Rust rewrite | 250,000 members | Discord blog |
| Rust `SortedSet` op cost (5k–1M items) | 0.61 µs best, 3.68 µs worst | Discord blog |
| Scaled to | **11 M concurrent users** | Discord blog |
| zstd + custom dictionary, compression ratio | 6 → nearly 10 | Discord blog, 2024 |
| Representative payload size | **270 B → 166 B** | same |
| `passive_update_v1` share of gateway bandwidth | 30%+ of bytes, ~2% of messages | same |
| After delta-only `PASSIVE_UPDATE_V2` | **35% → 5%** of bandwidth | same |
| Total gateway bandwidth reduction | **~40%** | same |

The most quotable line for an interview is the pairing of **26 million events per second** with
**five engineers**. That ratio is only achievable because the architecture pushes fan-out to the
edge of the system — per-node distribution, per-connection lightweight processes, deltas
instead of snapshots — rather than because of heroic operational effort. And the
`passive_update_v1` finding is the practical lesson: **profile bytes on the wire by message
type**, because in almost every real-time system one message type you weren't thinking about
is the majority of your bandwidth.

### Code

The message-shape decisions that determine whether your fan-out is affordable.

```javascript
// Delta encoding + per-node fan-out. Two ideas, both from the Discord
// write-ups, in the shape you would actually ship them.

// 1. Send deltas, not snapshots. Keep the last-sent state per room and
//    publish only changed fields. This is what took Discord's worst
//    dispatch from 35% of gateway bandwidth to 5%.
const lastSent = new Map();   // roomId -> last published state object

function delta(roomId, next) {
  const prev = lastSent.get(roomId) ?? {};
  const out = {};
  for (const [k, v] of Object.entries(next)) {
    if (JSON.stringify(prev[k]) !== JSON.stringify(v)) out[k] = v;
  }
  lastSent.set(roomId, next);
  return Object.keys(out).length ? out : null;   // nothing changed: send none
}

// 2. Fan out per NODE, not per recipient. The room owner asks Redis which
//    nodes currently hold members of this room and publishes once per node.
async function broadcast(roomId, payload) {
  const d = delta(roomId, payload);
  if (!d) return;
  const nodes = await redis.smembers(`room:${roomId}:nodes`);
  const body = JSON.stringify({ room: roomId, delta: d, seq: nextSeq(roomId) });
  const pipe = redis.pipeline();
  for (const nodeId of nodes) pipe.publish(`node:${nodeId}`, body);
  await pipe.exec();          // 20 publishes for 100,000 recipients
}

// 3. Presence as a scored set so a crashed node's users expire on their own.
//    Clients refresh via heartbeat; a sweeper trims anything older than 90s.
async function heartbeat(roomId, userId) {
  await redis.zadd(`presence:${roomId}`, Date.now(), userId);
}
setInterval(async () => {
  for (const roomId of localRooms.keys()) {
    await redis.zremrangebyscore(`presence:${roomId}`, 0, Date.now() - 90_000);
  }
}, 30_000).unref();
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Per-node fan-out | Rooms are tiny (under ~50 members) | A node-membership index to keep consistent |
| Delta encoding | Clients may join mid-stream without a snapshot | Clients need a resync path; sequence numbers |
| Dictionary compression | Payloads are already large or binary | Dictionary versioning and negotiation |
| Sharding large rooms | Every room is small | Routing complexity; cross-shard ordering |
| Aggregated presence | The UI renders individual names | Loss of detail |

### Follow-ups they will ask

**Q: One room has 500,000 members and someone posts. Walk me through what happens.**
A: The logical event is one message; the physical cost is 500,000 socket writes. With per-node
fan-out and, say, 50 nodes holding those members, the bus carries 50 messages and each node
does about 10,000 local writes, which is a few milliseconds of work per node in parallel. The
dangerous version is the naive one where the publisher enumerates recipients — that's 500,000
bus messages and the bus becomes the bottleneck. I'd also apply per-room rate limiting and
coalescing, because in a room that size the events are bursty: batching several events into
one frame every 100 milliseconds cuts writes by an order of magnitude and nobody perceives the
difference.

**Q: How do you guarantee ordering and no message loss over a real-time fan-out?**
A: Honestly, I'd start by saying you usually shouldn't guarantee both over the socket. The
socket is a best-effort delivery channel; the durable record is the database. Each message gets
a monotonic per-room sequence number, the client tracks the highest sequence it has seen, and
on reconnect it sends that number and the server replays from a bounded buffer or tells it to
resync from the API. That gives you ordering within a room and recovery from loss, without
trying to make the transport itself reliable. If you genuinely need durable ordered delivery
you're describing Kafka, and you should put Kafka in the path and accept the added latency.

**Q: How would you load-test a real-time system?**
A: With the amplification factor, not the connection count, as the independent variable.
I'd establish the target number of connections first, then drive message rate and room-size
distribution to hit the write-per-second target, because 100,000 idle connections tell me
almost nothing. The metrics I'd watch are p99 end-to-end delivery latency measured at the
client, per-node socket write backlog (`bufferedAmount` in Node), bus publish latency, and CPU
per node. And I'd test the failure case explicitly — kill a node holding 30,000 connections and
measure whether the reconnect spike is absorbed or whether it cascades, because that is the
scenario that actually causes outages.

### Red flags — do not say this

- ❌ "We can handle a million connections, so we can handle a million users chatting." → ✅ "Connections are the easy part. The number that decides the architecture is writes per second, which is events times average recipients."
- ❌ "Redis Pub/Sub will handle the fan-out." → ✅ "Redis Pub/Sub distributes one message per node; the per-recipient writes happen locally on each node. Publishing per recipient would make Redis the bottleneck."
- ❌ "We send the full state so clients are always consistent." → ✅ "Deltas with a sequence number, plus a resync path. Discord found snapshot dispatches were 30% of their bandwidth for 2% of their messages."

---

## Module 02 — self-test

Answer out loud, without notes. If you stumble, reread that section.

1. Walk through a cold DNS resolution for `api.example.com`, naming every server involved.
2. Your TTL is 60 seconds. Give four independent reasons why failover still takes twenty
   minutes.
3. Why can't you put a `CNAME` at a zone apex, and what do providers do about it?
4. How many round trips before the server reads your request over TCP + TLS 1.3? Over QUIC?
5. Explain TCP head-of-line blocking and how HTTP/2 and HTTP/3 each relate to it.
6. Your service intermittently fails to open outbound connections under load. Name the two
   most likely causes.
7. Which HTTP methods are idempotent? Which are safe? Which are cacheable?
8. A `POST` times out and the client retries. Describe the exact mechanism that prevents a
   double charge, including the concurrency case.
9. What is the difference between `no-cache` and `no-store`? Between `409` and `412`?
10. Draw a horizontally scalable WebSocket architecture and name the component that makes
    cross-node delivery work.
11. Why is SSE, not WebSockets, the right transport for LLM token streaming? Give three
    reasons and two production gotchas.
12. A room has 100,000 members spread over 20 nodes. How many bus messages does one post
    generate under a naive design, and under the correct one?

---

## Key numbers from this module

| Fact | Number |
|------|--------|
| Cold DNS resolution (uncached, full walk) | 20–120 ms, ~3 upstream round trips |
| Warm DNS resolution | 0–2 ms |
| Sensible DNS TTL for a service endpoint | 300 s; 60 s if failover-critical |
| Negative-caching TTL source | SOA `minimum` field (often 5–60 min) |
| Realistic DNS failover time | 5–10 min, with a long stale tail |
| AWS us-east-1 DynamoDB DNS outage (19–20 Oct 2025) | DNS restored in **~2.5 h**; full event **~15 h** |
| — recovery mechanism | Clients recovered **as cached DNS records expired** (2:25 → 2:40 AM) |
| TCP handshake | 1 RTT |
| TCP + TLS 1.2 / TLS 1.3 to first request byte | 3 RTT / **2 RTT** |
| QUIC handshake / 0-RTT resume | 1 RTT / 0 RTT |
| Linux initial congestion window | 10 segments ≈ **14 KB** |
| Linux `TIME_WAIT` duration | 60 s (2 × MSL) |
| Default ephemeral port range | ~28,000 ports → ~470 new conns/s to one destination |
| Nagle + delayed ACK stall | up to 40 ms |
| Default `ulimit -n` on many systems | 1024 (raise it) |
| HTTP/1.1 browser connections per origin | 6 |
| HTTP version share of Cloudflare traffic, 2025 | **HTTP/2 50%, HTTP/1.x 29%, HTTP/3 21%** |
| HTTP/2 server push | Removed from Chrome in 2022; use `103 Early Hints` |
| Let's Encrypt certificate lifetime | 90 days (forces ACME automation) |
| AWS ALB default idle timeout | **60 s** — the classic WebSocket disconnect bug |
| WebSocket frame overhead | 2–14 bytes per message |
| SSE keep-alive interval | comment frame every 15–30 s |
| SSE required nginx settings | `proxy_buffering off` + `X-Accel-Buffering: no` |
| Polling cost, 100k clients @ 5 s | 20,000 QPS of mostly-empty responses |
| Discord concurrent users / events per second | **12 M+ / 26 M+ per second** |
| Discord chat fleet / team size | 400–500 Elixir machines / **5 engineers** |
| Discord guild ceiling before Rust `SortedSet` | 250,000 members |
| Discord Rust `SortedSet` op cost | 0.61 µs best, 3.68 µs worst (5k–1M items) |
| Discord zstd + dictionary | ratio 6 → ~10; payload **270 B → 166 B** |
| Discord `PASSIVE_UPDATE_V2` (deltas not snapshots) | 35% → **5%** of gateway bandwidth |
| Discord total gateway bandwidth reduction | **~40%** |
| Real-time amplification formula | writes/s = events/s × avg recipients/event |

---

**Next:** [Module 03 — APIs: REST, GraphQL, gRPC & API Gateways](./03_APIs.md)
