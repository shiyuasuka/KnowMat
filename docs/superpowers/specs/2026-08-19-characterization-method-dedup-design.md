# Alpha25 characterization-method precision design

## Goal

Improve GLM Alpha25 precision without reducing source-backed recall. The change targets duplicate Characterization records such as `TEM` plus `Transmission Electron Microscopy (TEM)` assigned to the same material/state. It does not change the expert prompt, provider calls, or `final.json` schema.

## Considered approaches

1. Merge every record in the same broad technique family. This removes the most noise, but can collapse different instruments, acquisition modes, states, or conditions and is rejected as unsafe.
2. Conservatively coalesce presentation aliases. This is selected. Records must have the same owner, material state, normalized technique family, compatible secondary metadata, and an agreeing technique-specific `method_class`. Only multiple bare aliases are merged. Detailed instruments or acquisition modes always remain separate from their umbrella method.
3. Normalize aliases only in the evaluator. This can improve reported matching but leaves production duplicates intact and is therefore insufficient.

## Data flow

After ordinary exact-record deduplication, the materializer classifies explicit technique names from `method_raw` and `method_class` using model-independent scientific aliases such as SEM, TEM, STEM, EBSD, EDS, XRD, APT, optical microscopy, and X-ray tomography. It groups only records whose non-method metadata and technique-specific provider classes agree. Evidence is unioned into the surviving bare alias record, with a full method spelling preferred over an acronym.

If any detailed record exists, no umbrella alias is absorbed because the records may represent distinct instruments or modes. Generic/conflicting method classes and conflicting state, equipment, condition, specimen, parameters, or other metadata also prevent merging.

## Audit and compatibility

Each removed alias is preserved in the existing `issues.json`/`.md` stream under a short `characterization_method_alias_merged` code, including the removed record, survivor before/after merge, canonical family, and evidence. No new audit file is introduced. The `final.json` schema and prompt hash remain unchanged.

## Acceptance gates

- Unit tests cover bare aliases, one detailed survivor, conflicting details, different states, evidence union, and audit completeness.
- A pilot must keep loose matched/recall and core tensile metrics unchanged while improving Characterization or overall precision/F1.
- A 30-paper rematerialization must retain 30/30 papers, 405/405 cached tasks, zero fatal outputs, and complete existing audits.
- If any loose matched claim is lost, the production change is rejected.
