# From remembered text to a supported decision

## Topic: durable agent context

### Subproblem: what must survive a handoff?

I started with a small operational question: can a resumed worker identify the current rollback target and distinguish a pending launch from a completed release? That decision is narrower and more testable than asking whether an agent has "good memory."

The fixture uses a fictional grocery-planning workflow. It contains 35 facts, including 20 newer routine notes, explicit revisions, two competing region constraints, a withdrawn approval, a draft replacement, and a source edited after its recorded digest. There are no employer or customer records.

## The usual approach and its failure

A simple recent-first packer sorts by observation time and fills a byte budget. That is useful when recency approximates importance and all records remain valid. Here it can select status noise, choose one side of an unresolved conflict, or repeat a superseded approval.

Increasing the budget does not make an unsupported record current. Adding a similarity score does not authenticate its tenant or verify its source. I separated these checks from ranking so each failure has a visible reason.

## My approach

The ledger records identity, tenant, key, value, observation time, expiry, review status, explicit supersession, source identity, and source digest. Strict time ordering makes supersession cycles invalid. Competing terminal versions remain withheld until the data is reconciled.

The caller names the facts required for its decision. Those facts form an atomic minimum: include all of them, or return a refusal without a partial payload. Only after that reservation does a simple priority-and-tag score add optional context.

The byte limit covers the complete UTF-8 JSON payload, including the tenant, timestamp, trust label and evidence metadata. The implementation serializes each candidate addition before accepting it. Multi-byte text is tested at its exact acceptance boundary.

## Results and decision

The [committed experiment](../results/report.md) reports 14 of 14 authored contracts met by the guarded packer, versus one by recent-first packing. A stronger validity-aware recent-first ablation meets 10 of 14: it applies the same validity gates and checks whether required facts could fit, but does not reserve them during packing. That comparison isolates the reservation step. Five guarded cases produce ready context, eight refuse unavailable or oversized required context, and one denies an unauthorized tenant. Counts are protocol outcomes, not model-quality measurements.

My recommendation is to make required evidence and refusal behavior part of the handoff API. A compact context that loses a launch restriction is a failed handoff even when the JSON fits. A refusal is useful if it identifies the missing key and lets the host request a current source or a larger budget.

## What I would not infer

Hash matching does not establish factual truth. The trust label does not make an LLM immune to prompt injection. A local tenant filter does not replace upstream authentication. The experiment contains no live LLM, provider token count, latency claim, or production deployment.

The next test would use independently written cases and a validity-aware retrieval baseline with a learned relevance score, then measure downstream decisions under a fixed tokenizer budget. That is the evidence needed before claiming answer-quality gains.
