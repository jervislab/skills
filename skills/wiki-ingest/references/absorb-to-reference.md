# Absorb to Reference

Read one source, extract transferable methods, and absorb them into the target skill's references/. Complements absorb-to-wiki and can run in parallel on the same source. This path keeps only principles and methods, stripping narrative context and argument by example.

## Rules

Absorb transferable methods — concrete operating patterns that hold across domains. Leave behind details bound to the source's particular framework. The absorbed version improves on the source's decomposition rather than mirroring it.

## Workflow

### 1. Assess

Read the whole source, then judge its core thesis and decomposition. Settle the scope: is the source a self-contained methodology, or a patch to existing knowledge? Existing knowledge means LLM pre-training plus the target skill's current references — the source's value is the delta beyond both.

A self-contained methodology gets its own reference file. Scattered insights fuse into existing files. Splitting a self-contained methodology across several existing files breaks its architectural integrity.

### 2. Extract

Target: methods transferable at the operating level — counter-intuitive insights, concrete patterns, explicit priority orderings, design constraints that narrow the solution space.

Abstraction level: concrete enough to execute, general enough to transfer. Discard generic best practice (already known to the LLM), domain-specific implementation detail, and restatements of principles the target skill already holds.

### 3. Restructure

Do not keep the source's decomposition. Question every classification axis: are mechanism and outcome conflated? Are infrastructure and behavioral traits entangled? Does domain-specific terminology hide the underlying invariant?

Rebuild independently. The absorbed reference decomposes better than the original — a reconstructed method, not a reordered copy.

### 4. Fuse

Standalone reference: create a new file and add a pointer in the target skill's SKILL.md. Patch: insert beside the related content, not appended at the end. Strengthen weaker statements in place; add no duplicates. Meta-principles route to SKILL.md, operating guidance to the matching reference file.

### 5. Audit

Reread every insertion and modification. Check knowledge accuracy, decomposition quality, and conformance to the target skill's writing standards.
