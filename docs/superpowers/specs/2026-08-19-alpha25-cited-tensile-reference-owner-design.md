# Alpha25 Citation-Aware Tensile Reference Owner Recovery

## Goal

Improve GLM Alpha25 owner precision without changing the reviewed prompt, adding
provider calls, changing `final.json`, or reducing Composition and claim recall.
The increment corrects numeric core-tensile facts copied from literature-comparison
tables when the provider attached them to a broad Target column owner.

The GPT expert ledger is used only after production output exists. Runtime rules
must remain paper-, GT-, model-, and provider-independent.

## Selected design

Recover one independent Reference owner per cited table column/value binding. The
recovery is fact-level: it moves only the cited numeric tensile fact and never
changes the role of the shared source item.

A fact is eligible only when all of the following are true:

1. it is a numeric yield-strength, ultimate-tensile-strength, or elongation fact;
2. its evidence contains a complete Markdown table header and value row (a cached
   `data_source=unknown` is allowed only when this literal table shape is present);
3. exactly one header cell names the fact's declared owner;
4. the value cell at that same column contains the complete fact value;
5. that cell, or its exact header cell, contains one terminal numeric citation,
   author-year attribution, or explicit external standard/designation;
6. the evidence does not identify the selected result as `this work`, `our work`,
   or `current study`; and
7. the column/value/citation binding is unique.

The new owner keeps the source material family and uses a citation-qualified sample
label with `Role=Reference` and `Data_Nature=Literature_Experimental`. The cited
fact is routed to this anchor before ordinary owner recovery. Other facts on the
original item remain untouched.

## Conservative cases

- A current-study column without a citation remains Target.
- A test method merely mentioning ASTM/ISO does not become a Reference; the marker
  must qualify the table owner or the fact's own value cell.
- A row with multiple matching owner columns, a value mismatch, multiple competing
  markers, prose-only indirect citation, or incomplete table evidence remains
  unchanged.
- Standards/specification values may become independent Reference facts when the
  table explicitly presents the standard as the compared owner. They are never
  reassigned to the experimental Target.
- Mixed items such as LPBF keep current-study facts on the Target while independently
  cited facts can split to a Reference owner.

## Audit and compatibility

Every move emits `reference_tensile_owner_recovered` in existing `issues.json` and
`issues.md`. The issue records the original fact, before/after owner, header, value
row, selected column, marker, and decision rule. No new audit artifact or internal
field is added to `final.json`.

Prompt files and hashes remain unchanged. The recovery is deterministic and linear
in the number of facts and evidence rows, so it adds no material latency.

## Verification

Focused tests cover numeric citations, standard-qualified reference columns,
current-study columns, method-only standards, value mismatch, ambiguous columns,
non-tensile facts, mixed Target/Reference items, and complete audit payloads.

A paper pilot must inspect every moved fact. The final 30-paper frozen-cache
rematerialization must retain 30/30 papers, 405/405 task responses, zero fatal
outputs, unchanged schema/skill/prompt digests, and no provider calls. Acceptance
requires:

- Composition loose/strict matched, recall, precision, and F1 do not decline;
- global and core-tensile loose/strict matched and recall do not decline;
- global and core-tensile precision do not decline;
- strict owner residuals decrease; and
- every moved fact has complete audit provenance.

If a gate fails, narrow or revert the cited-owner rule rather than weakening the
evidence requirements.
