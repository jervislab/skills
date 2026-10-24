# Entity Bootstrap

Guide the user through AskUserQuestion to build an entity page for a person or organization. Applies to the anchor entity created during wiki bootstrap, and to any entity met during everyday ingest that deserves its own page.

## When to Trigger

1. Bootstrap Phase 2, when creating the anchor entity page
2. Single Mode ingest, when the source surfaces a person or organization worth a standalone page
3. The user asks for an entity page

## Deep Capture Principles

Entity pages are the anchor nodes of the wiki's knowledge network. Every entry on the page should be a reasoning trigger, not a label.

Record the generating structure, not what it generates. Each schema field is fuel for the reasoning engine.

Depth audit: before writing an entry, ask two questions. (1) Can it be stated one layer deeper? If so, the current statement is surface; rewrite it at the deeper layer. (2) Could it be derived from other fields if deleted? If so, leave it out. An entry that fails the audit is rewritten or removed.

Write test: does the signal change how an agent will reason when it later consumes this entity page? Only signals that do are worth writing; the rest stay in the raw material in sources/ for lookup on demand.

## Ask Flow

Collect in rounds with AskUserQuestion. Branch the later rounds on the entity type chosen in Round 1.

### Round 1: Orientation

1. entity type: person / organization
2. existing material: what material on this entity do you already have? (multi-select: existing documents or notes / public information to capture / description from memory / Other)

### Round 2: Personality Kernel

If Round 1 = person. Concentric model: the inner circle holds generating structures such as drives and contradictions; the outer circle holds social coordinates such as name and position. Round 2 collects only the inner circle.

1. personality kernel: in one paragraph, describe what is most essential about this person. What drives them, what contradictions do they carry, and what are they capable of but choose not to do? (free input. Hint: go beyond labels and explain how the drives relate to each other)
2. vision & expertise: what long-term direction are they pursuing? What is their professional background and core ability? (free input)

### Round 2: Organization Kernel

If Round 1 = organization.

1. positioning: what does this organization do, and what problem does it solve? (free input)
2. core competence: where does its competitive strength come from? (free input)
3. key people & tension: who are the key people? What core contradiction or dilemma does the organization face? (free input)

### Round 3: Supplement (Optional)

Ask when the agent judges the information can support a deeper page. Applies to both people and organizations.

1. leverage: what abilities or resources give them more options than most of their peers? (free input. Information access, cross-border reach, social capital, a professional foundation, organizational structure, and the like all count)

## Extraction Principles

Separate three kinds of generating-layer signal from the user's answers:

- drive: the root motive behind behavior. Explain the generative relationships between drives, not just a list of them. Distinct from vision (the declared direction)
- tension: an irreducible structural contradiction. Admitted when two real forces pull against each other persistently and neither side can be chosen. Excluded: career-path narrative, universal human nature, behavior patterns derivable from other fields
- constraint: an observed boundary of behavior. When consuming the page, the agent works around limitations and respects restraint

Operational signals (interests, preferences) have value for conversational rapport but carry no identity function; deleting them should not reduce the model's understanding of what the entity fundamentally is.

## Page Structure

Write the output to `wiki/entities/<name>.md`, following the absorb-to-wiki page conventions. Headings follow the wiki's language.

```markdown
---
name: [Entity name]
description: One line on the entity's role in the knowledge network and its most distinguishing trait
source: user input
last_updated: YYYY-MM-DD
---

## Overview

The gestalt entry point. One or two sentences on the overall texture that structured fields cannot convey, without repeating the kernel dimensions, which speak for themselves below. Then move from kernel to coordinates: for a person, drives first, then professional background and social position; for an organization, positioning and core competence first, then scale and key people.

## Personality Kernel / Organization Kernel

drive, tension, and constraint unfolded in natural language. Explain the inner logic in connected paragraphs rather than listing fields. Each entry is a reasoning trigger: after reading it, the model can infer behavior patterns, not just know an attribute.

## Expertise / Core Competence

expertise, leverage.

## Direction

vision and current stage.

## Related

`[[wiki-link]]` to related pages in the wiki.
```

## Working with wiki-ingest

Pages produced by entity-bootstrap are anchor nodes of the wiki's knowledge network. When later ingests touch an existing entity, new facts are added to its page through the Fuse step; the page is not rebuilt. The Overview paragraph is revised as understanding deepens; the kernel description changes only when the user corrects it.

Later updates to generating-layer fields (drive / tension / constraint) must pass the depth audit: a new signal must go one layer deeper than the existing description, or cover an independent dimension it has not captured. Coordinate-layer fields can be supplemented freely as new material arrives.
