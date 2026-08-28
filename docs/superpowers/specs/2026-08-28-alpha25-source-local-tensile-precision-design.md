# Alpha25 source-local tensile precision gates

## Goal

Improve GLM Alpha25 precision relative to the business and independent expert
GT by preventing cross-chunk tensile owner/condition projections while keeping
source-grounded recall. Composition, extraction prompts, schemas, OCR/VLM and
the public `final.json` contract remain unchanged.

## Design

The promotion layer will add only source-local decisions. A tensile fact may be
reassigned to an existing inventory owner or state only when the same source
assertion contains a unique literal specimen/state/orientation coordinate. If
more than one existing coordinate is possible, the fact remains out of formal
Properties and is recorded in the normal audit stream; no owner is created and
no GT-specific rule is used.

Near-duplicate tensile values from prose and a table are treated as a shadow
only when all of the following are true: the source blocks are linked to the
same paper-local assertion, owner role/data nature match, tensile family and
subtype match, unit dimension and test condition match, orientation/state
coordinates match, and the numeric values are within a conservative reporting
tolerance. A table value with uncertainty/greater precision is the survivor;
the prose evidence is appended to the survivor for auditability. Different
subtypes (for example total versus uniform or fracture elongation), different
conditions, or unresolved coordinates are never merged.

State binding uses only existing `OwnerGraph` nodes and source evidence. An
explicit state/specimen phrase can fill a missing `material_state` or move a
fact from a generic base label only when exactly one candidate matches. A
build/test orientation is a coordinate, not a structure feature, and is used
only to select an existing oriented tensile owner.

## Audit and compatibility

Every removal, merge, or reassignment emits a `PromotionIssue` with before/after
facts, source block/evidence, selected owner (if any), and a machine-readable
reason. No issue changes the public fact shape. Existing `quality_audit.json`
and `issues.json/.md` consumers continue to receive the same format.

## Verification

Add focused tests for unique state/orientation binding, ambiguous state
fail-closed behavior, prose/table tensile shadow handling, and subtype/condition
non-merging. Run the Alpha25 promotion suite and the full offline suite. The
regression gate is: Composition accepted facts and schema are unchanged,
core-tensile precision does not decrease, and strict owner/condition matching
improves or stays equal on the frozen five-paper candidate replay.
