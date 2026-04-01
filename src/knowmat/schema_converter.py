"""
Schema converter for KnowMat 2.0.

Transforms the internal LLM extraction format into the target HEA dataset
schema.  All domain heuristics (phase inference, precipitate detection,
property-name normalisation, process-category classification, etc.) are
driven by :class:`~knowmat.domain_rules.DomainRules` so that materials
scientists can adjust behaviour via ``domain_rules.yaml``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

try:
    from pymatgen.core import Composition as _PymatgenComposition
except ImportError:
    _PymatgenComposition = None

from knowmat.domain_rules import DomainRules, default_rules
from knowmat.states import TargetSchema

logger = logging.getLogger(__name__)


class SchemaConverter:
    """Convert LLM-extracted data to the target HEA dataset schema."""

    def __init__(self, rules: DomainRules | None = None) -> None:
        self.rules = rules or default_rules

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def convert(
        self,
        data: dict,
        source_path: str,
        paper_text: Optional[str] = None,
        document_metadata: Optional[dict] = None,
    ) -> TargetSchema:
        """Convert internal extraction dict to target HEA schema.

        Mirrors the original ``_to_target_schema`` logic with 3-tier DOI
        priority, Key_Params_JSON population, dedicated microstructure text,
        grain-size backfill, and build-orientation encoding.
        """
        if not isinstance(data, dict):
            return {"Dataset_Description": "High Entropy Alloy Data Extraction Template", "Materials": []}
        if "Materials" in data and "Dataset_Description" in data:
            existing_materials = data.get("Materials", []) or []
            if existing_materials:
                repaired = self._harmonize_existing_target_materials(existing_materials)
                patched = dict(data)
                patched["Materials"] = repaired
                return self._expand_variable_materials_in_target_schema(  # type: ignore[return-value]
                    patched, paper_text
                )
            source_name = os.path.basename(source_path)
            if self._is_datasheet_like_document(paper_text, source_name):
                bootstrapped = self._bootstrap_datasheet_compositions(paper_text)
                if bootstrapped:
                    logger.warning(
                        "[COMPOSITION] Empty target schema received; "
                        "bootstrapped %d composition(s) from datasheet text.",
                        len(bootstrapped),
                    )
                    data = {"compositions": bootstrapped}
                else:
                    return self._expand_variable_materials_in_target_schema(  # type: ignore[return-value]
                        data, paper_text
                    )
            else:
                return self._expand_variable_materials_in_target_schema(  # type: ignore[return-value]
                    data, paper_text
                )

        compositions = data.get("compositions", []) or []
        source_name = os.path.basename(source_path)

        ocr_doi = (document_metadata or {}).get("doi") if document_metadata else None
        regex_doi = self.extract_first_doi(paper_text)
        global_doi = ocr_doi or regex_doi or ""

        target_compositions = [c for c in compositions if c.get("role", "Target") == "Target"]
        datasheet_like = self._is_datasheet_like_document(paper_text, source_name)
        if not target_compositions and compositions and datasheet_like:
            logger.warning(
                "[COMPOSITION] No Target entries found; datasheet-like document detected. "
                "Falling back to all extracted compositions (including Reference)."
            )
            target_compositions = list(compositions)
        if not target_compositions and datasheet_like:
            bootstrapped = self._bootstrap_datasheet_compositions(paper_text)
            if bootstrapped:
                logger.warning(
                    "[COMPOSITION] No extracted compositions available; "
                    "bootstrapped %d composition(s) from datasheet text.",
                    len(bootstrapped),
                )
                target_compositions = bootstrapped
        target_compositions = self._expand_variable_composition_families(
            target_compositions, paper_text
        )
        target_compositions = self._harmonize_system_element_sets(target_compositions)
        target_count = len(target_compositions)

        materials: List[Dict[str, Any]] = []
        for mat_idx, comp in enumerate(target_compositions, start=1):
            comp_raw_first = comp.get("composition", "") or ""
            formula_norm = comp.get("composition_normalized")
            if not formula_norm:
                formula_norm = comp_raw_first.replace(" ", "")
            recovered_formula = self._recover_formula_from_paper_text(
                paper_text=paper_text,
                comp_raw=comp_raw_first,
                fallback_formula=formula_norm,
                target_count=target_count,
            )
            if recovered_formula:
                formula_norm = recovered_formula

            # Prefer metadata / regex DOI over LLM-filled source_doi to reduce fabrication.
            material_doi = (global_doi or "").strip() or (comp.get("source_doi") or "").strip() or ""
            sample = self._build_sample(comp, mat_idx, 1)
            tests = self._order_properties(sample.get("Performance_Tests", []) or [])
            sample_no_tests = dict(sample)
            sample_no_tests["Performance_Tests"] = []

            nominal_comp = self._normalize_reported_composition(
                comp.get("nominal_composition")
            )
            nominal_type = comp.get("nominal_composition_type")
            measured_type = comp.get("measured_composition_type")

            inferred_nominal, inferred_nominal_type = self._infer_nominal_from_commercial_name(
                comp_raw_first
            )
            if inferred_nominal is None:
                process_context = comp.get("processing_conditions")
                if isinstance(process_context, dict):
                    process_context = json.dumps(process_context, ensure_ascii=False)
                inferred_nominal, inferred_nominal_type = self._infer_blend_nominal_from_name(
                    comp_raw_first,
                    context_text=str(process_context or ""),
                )
            if nominal_comp is None and inferred_nominal is not None:
                nominal_comp = inferred_nominal
                if not nominal_type:
                    nominal_type = inferred_nominal_type

            balance_element = self._pick_balance_element(
                nominal_comp, comp_raw_first
            )
            measured_comp = self._normalize_reported_composition(
                comp.get("measured_composition"),
                preferred_balance_element=balance_element,
            )

            composition_source = "formula_parse"
            if measured_comp:
                raw_comp_json = dict(measured_comp)
                composition_source = "measured_composition"
            elif nominal_comp:
                raw_comp_json = dict(nominal_comp)
                composition_source = "nominal_composition"
            elif self._is_commercial_shorthand(comp_raw_first, formula_norm):
                # Avoid turning commercial shorthand grades (e.g. Ti6Al4V) into
                # stoichiometric formulas via pymatgen.
                raw_comp_json = {}
                composition_source = "commercial_name_only"
            else:
                raw_comp_json = self.build_composition_json(formula_norm)

            validated_comp_json, comp_warnings = self.validate_composition_json(
                raw_comp_json, formula_norm
            )
            for warning in comp_warnings:
                logger.warning("[COMPOSITION] %s", warning)
            if composition_source == "commercial_name_only":
                logger.warning(
                    "[COMPOSITION] Commercial-grade shorthand detected ('%s'). "
                    "Skip formula parsing because no nominal/measured composition map was provided.",
                    comp_raw_first,
                )

            measured_method = (
                comp.get("measured_composition_method")
                or comp.get("measurement_method")
            )

            # If only parsed formula exists, keep it as nominal fallback so that
            # composition information stays entirely inside Composition_Info.
            nominal_out = nominal_comp
            nominal_type_out = nominal_type
            if (
                nominal_out is None
                and measured_comp is None
                and validated_comp_json
                and composition_source == "formula_parse"
            ):
                nominal_out = dict(validated_comp_json)
                nominal_type_out = nominal_type_out or "at%"

            process_text = str(sample.get("Process_Text_For_AI") or "not provided")
            micro_text = str(sample.get("Microstructure_Text_For_AI") or "not provided")
            process_payload = self._to_text_payload(process_text)
            micro_payload = self._to_text_payload(micro_text)

            item_label = comp.get("alloy_name_raw") or comp_raw_first or formula_norm or f"Material_{mat_idx}"
            material = {
                "description": f"--- Material {mat_idx}: {item_label} ---",
                "Mat_ID": f"M{mat_idx:03d}",
                "Composition_Info": {
                    "Alloy_Name_Raw": comp.get("alloy_name_raw") or comp_raw_first,
                    "Nominal_Composition": {
                        "Composition_Type": nominal_type_out,
                        "Elements_Normalized": nominal_out,
                    },
                    "Measured_Composition": {
                        "Composition_Type": measured_type,
                        "Elements_Normalized": measured_comp,
                        "Measurment_Method": measured_method,
                    },
                },
                "Composition_Source": composition_source,
                "Source_DOI": material_doi or "",
                "Source_File": source_name,
                "Process_Info": {
                    "Process_Category": sample.get("Process_Category") or "Unknown",
                    "Process_Text": process_payload,
                    "Key_Params": sample.get("Key_Params_JSON") or {},
                },
                "Microstructure_Info": {
                    "Microstructure_Text": micro_payload,
                    "Main_Phase": sample.get("Main_Phase") or None,
                    "Has_Precipitates": sample.get("Has_Precipitates"),
                    "Grain_Size_avg_um": sample.get("Grain_Size_avg_um"),
                },
                "Properties_Info": tests,
                "Processed_Samples": [sample_no_tests],
            }
            materials.append(material)

        result = {
            "Dataset_Description": "High Entropy Alloy Data Extraction Template",
            "schema_version": "2.2",
            "pipeline_version": "knowmat-2.1.0",
            "Materials": materials,
        }
        return self._expand_variable_materials_in_target_schema(result, paper_text)

    def _expand_variable_materials_in_target_schema(
        self, schema_data: dict, paper_text: Optional[str]
    ) -> dict:
        """Expand variable-family materials even when input is already target schema."""
        materials = list(schema_data.get("Materials", []) or [])
        if not materials or not paper_text:
            return schema_data

        family_spec = self._extract_variable_family_spec(paper_text)
        if not family_spec:
            return schema_data

        base_text = (family_spec["base_joined"] + family_spec["variable_element"]).lower()
        family_material_indices = []
        existing_codes: set[str] = set()
        for idx, mat in enumerate(materials):
            comp_info = mat.get("Composition_Info") or {}
            haystack = (
                f"{mat.get('Alloy_Name_Raw', '')} {mat.get('Formula_Normalized', '')} "
                f"{comp_info.get('Alloy_Name_Raw', '')} {comp_info.get('Formula_Normalized', '')}"
            ).lower()
            if base_text in haystack or "_x" in haystack or "mox" in haystack:
                family_material_indices.append(idx)
                code = self._extract_variant_code(haystack, family_spec["variable_element"])
                if code:
                    existing_codes.add(code)

        if not family_material_indices:
            return schema_data

        expected_codes = [v["code"] for v in family_spec["variants"]]
        if all(code in existing_codes for code in expected_codes):
            return schema_data

        first_idx = family_material_indices[0]
        base_material = materials[first_idx]
        new_family_materials: List[Dict[str, Any]] = []

        # If no explicit variants exist, replace the ambiguous family entry.
        replace_ambiguous = len(existing_codes) == 0 and len(family_material_indices) == 1
        if not replace_ambiguous:
            for idx in family_material_indices:
                mat = materials[idx]
                comp_info = mat.get("Composition_Info") or {}
                code = self._extract_variant_code(
                    (
                        f"{mat.get('Alloy_Name_Raw', '')} {mat.get('Formula_Normalized', '')} "
                        f"{comp_info.get('Alloy_Name_Raw', '')} {comp_info.get('Formula_Normalized', '')}"
                    ),
                    family_spec["variable_element"],
                )
                if code in expected_codes:
                    new_family_materials.append(mat)

        for variant in family_spec["variants"]:
            if variant["code"] in existing_codes:
                continue
            clone = dict(base_material)
            raw_comp_json = self.build_composition_json(variant["normalized"])
            validated_comp_json, _ = self.validate_composition_json(
                raw_comp_json, variant["normalized"]
            )
            comp_info = dict(clone.get("Composition_Info") or {})
            comp_info["Alloy_Name_Raw"] = variant["label"]
            comp_info["Nominal_Composition"] = {
                "Composition_Type": "at%",
                "Elements_Normalized": validated_comp_json,
            }
            measured = dict(comp_info.get("Measured_Composition") or {})
            measured.setdefault("Composition_Type", None)
            measured.setdefault("Elements_Normalized", None)
            measured.setdefault("Measurment_Method", None)
            comp_info["Measured_Composition"] = measured
            clone["Composition_Info"] = comp_info
            clone.pop("Alloy_Name_Raw", None)
            clone.pop("Formula_Normalized", None)
            clone.pop("Composition_JSON", None)
            # Do not fabricate per-variant properties when source variant is absent.
            clone["Processed_Samples"] = []
            clone["Properties_Info"] = []
            new_family_materials.append(clone)

        if not new_family_materials:
            return schema_data

        if replace_ambiguous:
            retained = [m for idx, m in enumerate(materials) if idx != first_idx]
        else:
            retained = [m for idx, m in enumerate(materials) if idx not in family_material_indices]
        retained.extend(new_family_materials)

        # Re-index Mat_ID and description to keep schema consistent.
        for idx, mat in enumerate(retained, start=1):
            mat["Mat_ID"] = f"M{idx:03d}"
            comp_info = mat.get("Composition_Info") or {}
            label = (
                comp_info.get("Alloy_Name_Raw")
                or mat.get("Alloy_Name_Raw")
                or comp_info.get("Formula_Normalized")
                or mat.get("Formula_Normalized")
                or ""
            )
            mat["description"] = f"--- Material {idx}: {label} ---"

        out = dict(schema_data)
        out["Materials"] = retained
        return out

    def _expand_variable_composition_families(
        self, target_compositions: List[dict], paper_text: Optional[str]
    ) -> List[dict]:
        """Expand variable families (e.g. ``FeCoCrNiMox``) into explicit variants.

        This is a conservative fallback for cases where the LLM keeps only the
        family name and misses per-variant targets like ``Mo0/Mo1/Mo3/Mo5``.
        The function only activates when:
        - there is a clear ``...Mox``-style family in extracted targets, and
        - the paper text contains matching variant metadata (x-list + Mo at% list).
        """
        if not target_compositions or not paper_text:
            return target_compositions

        family_spec = self._extract_variable_family_spec(paper_text)
        if not family_spec:
            return target_compositions

        family_idx = -1
        family_text = (family_spec["base_joined"] + family_spec["variable_element"]).lower()
        for idx, comp in enumerate(target_compositions):
            haystack = (
                f"{comp.get('composition', '')} {comp.get('composition_normalized', '')}"
            ).lower().replace(" ", "")
            if family_text in haystack or "mox" in haystack or "_x" in haystack:
                family_idx = idx
                break
        if family_idx < 0:
            return target_compositions

        existing_codes: set[str] = set()
        for comp in target_compositions:
            code = self._extract_variant_code(
                f"{comp.get('composition', '')} {comp.get('composition_normalized', '')}",
                family_spec["variable_element"],
            )
            if code:
                existing_codes.add(code)

        source_comp = target_compositions[family_idx]
        expanded: List[dict] = []
        for idx, variant in enumerate(family_spec["variants"], start=1):
            if variant["code"] in existing_codes:
                continue
            clone = dict(source_comp)
            clone["composition"] = variant["label"]
            clone["composition_normalized"] = variant["normalized"]
            # Keep only the first as possible carrier; others are placeholders
            # to avoid fabricating per-variant properties.
            if idx > 1 or existing_codes:
                clone["properties_of_composition"] = []
                clone["grain_size_avg_um"] = None
                clone["grain_size_text"] = None
            expanded.append(clone)

        if not expanded:
            return target_compositions

        updated = list(target_compositions)
        if not existing_codes:
            updated.pop(family_idx)
        updated.extend(expanded)
        return updated

    def _extract_variable_family_spec(self, paper_text: Optional[str]) -> Optional[Dict[str, Any]]:
        if not paper_text:
            return None
        x_values = self._extract_numeric_series_best(
            paper_text,
            [
                r"\bx\s*=\s*([0-9.,\sandto\-]+)",
                r"\bx\s*=\s*([^)]+)\)",
            ],
        )
        mo_at_values = self._extract_numeric_series_best(
            paper_text,
            [
                r"\bmo\s*content\s*=\s*([0-9.,\sandto\-]+)\s*at%?",
                r"\bmo\s*content\s*=\s*([^)]+)\)",
            ],
        )
        if not x_values or not mo_at_values:
            return None
        if len(x_values) != len(mo_at_values):
            return None

        token_candidates = re.findall(r"\b[A-Z][A-Za-z0-9.]*x\b", paper_text)
        family_token = ""
        for token in token_candidates:
            if len(re.findall(r"[A-Z][a-z]?", token)) >= 3:
                family_token = token
                break
        if not family_token:
            return None

        m = re.search(r"([A-Z][a-z]?)x\b", family_token)
        if not m:
            return None
        variable_element = m.group(1)
        base_formula = family_token[: m.start(1)]
        base_elements = [elem for elem, _ in re.findall(r"([A-Z][a-z]?)(\d*(?:\.\d+)?)", base_formula)]
        base_elements = [e for e in base_elements if e]
        if not base_elements:
            return None

        variants = []
        for x_val, mo_at in zip(x_values, mo_at_values):
            remaining = 100.0 - float(mo_at)
            if remaining < 0:
                continue
            each_base = remaining / float(len(base_elements))
            normalized = "".join(
                f"{elem}{self._format_pct(each_base)}" for elem in base_elements
            ) + f"{variable_element}{self._format_pct(float(mo_at))}"
            code = self._format_x_code(x_val)
            label = (
                f"{''.join(base_elements)}{variable_element}{self._format_x_label(x_val)} "
                f"({variable_element}{code})"
            )
            variants.append({"x": x_val, "mo_at": mo_at, "code": code, "label": label, "normalized": normalized})
        if len(variants) < 2:
            return None
        return {
            "variable_element": variable_element,
            "base_elements": base_elements,
            "base_joined": "".join(base_elements),
            "variants": variants,
        }

    @staticmethod
    def _extract_numeric_series(text: str, pattern: str) -> List[float]:
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            return []
        segment = m.group(1)
        nums = re.findall(r"\d+(?:\.\d+)?", segment)
        return [float(v) for v in nums]

    @classmethod
    def _extract_numeric_series_best(cls, text: str, patterns: List[str]) -> List[float]:
        best: List[float] = []
        for pattern in patterns:
            nums = cls._extract_numeric_series(text, pattern)
            if len(nums) > len(best):
                best = nums
        return best

    @staticmethod
    def _format_pct(value: float) -> str:
        return f"{value:.3f}".rstrip("0").rstrip(".")

    @staticmethod
    def _format_x_code(x_val: float) -> str:
        # x=0.1 -> Mo1, x=0.3 -> Mo3, x=0.5 -> Mo5
        return str(int(round(x_val * 10)))

    def _format_x_label(self, x_val: float) -> str:
        if abs(x_val) < 1e-9:
            return "0"
        return self._format_pct(x_val)

    @staticmethod
    def _extract_variant_code(text: str, variable_element: str) -> Optional[str]:
        if not text:
            return None
        m = re.search(rf"\b{re.escape(variable_element)}\s*(\d+)\b", text, re.IGNORECASE)
        if m:
            return m.group(1)
        return None

    @staticmethod
    def _is_datasheet_like_document(paper_text: Optional[str], source_name: str) -> bool:
        haystack = f"{source_name}\n{paper_text or ''}".lower()
        signals = [
            "datasheet",
            "technical note",
            "common name",
            "specifications and compositions",
            "summary of physical properties",
            "product conditions",
            "product forms",
        ]
        score = sum(1 for s in signals if s in haystack)
        # two or more signals is usually enough to distinguish from a normal paper
        return score >= 2

    def _recover_formula_from_paper_text(
        self,
        paper_text: Optional[str],
        comp_raw: str,
        fallback_formula: str,
        target_count: int,
    ) -> Optional[str]:
        """Recover explicit composition formula from paper text when available.

        This is designed to prevent LLM-hallucinated composition ratios from
        dominating the final schema when the source text contains an explicit
        balance-notation composition line (e.g. ``... - Bal Ni``).
        """
        if not paper_text or "bal" not in paper_text.lower():
            return None

        # Prefer lines mentioning the current alloy identifier (e.g. SD3230).
        hint_tokens = re.findall(r"[A-Za-z]{2,}\d+", comp_raw or "")
        lines = [ln.strip() for ln in paper_text.splitlines() if ln.strip()]
        candidates: List[Tuple[int, str]] = []
        for ln in lines:
            lower_ln = ln.lower()
            if "bal" not in lower_ln:
                continue
            if "-" not in ln and "composition" not in lower_ln:
                continue

            score = 0
            if "composition" in lower_ln:
                score += 3
            if "wt" in lower_ln or "at" in lower_ln:
                score += 2
            score += len(re.findall(r"\d+(?:\.\d+)?\s*[A-Z][a-z]?", ln))
            if hint_tokens and any(tok.lower() in lower_ln for tok in hint_tokens):
                score += 5
            elif target_count == 1:
                score += 1
            candidates.append((score, ln))

        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_line = candidates[0][1]

        parsed = self._parse_balance_composition_line(best_line)
        if not parsed:
            return None

        formula = "".join(f"{el}{self._format_pct(val)}" for el, val in parsed)
        if not formula:
            return None
        return formula

    @staticmethod
    def _parse_balance_composition_line(line: str) -> Optional[List[Tuple[str, float]]]:
        """Parse lines like ``21.49 Cr - ... - 0.48 C - Bal Ni``."""
        txt = line.replace("−", "-").replace("–", "-").replace("—", "-")
        segments = [seg.strip() for seg in re.split(r"\s*-\s*", txt) if seg.strip()]
        if len(segments) < 3:
            return None

        pairs: List[Tuple[str, float]] = []
        bal_elem: Optional[str] = None

        for seg in segments:
            seg_clean = re.sub(r"[()\[\],;]", " ", seg)
            seg_clean = re.sub(r"\s+", " ", seg_clean).strip()

            mb = re.search(r"(?i)\bBal\s*([A-Z][a-z]?)\b", seg_clean)
            if not mb:
                mb = re.search(r"(?i)\b([A-Z][a-z]?)\s*Bal\b", seg_clean)
            if mb:
                bal_elem = mb.group(1)
                continue

            m_num_first = re.search(r"\b(\d+(?:\.\d+)?)\s*([A-Z][a-z]?)\b", seg_clean)
            if m_num_first:
                val = float(m_num_first.group(1))
                elem = m_num_first.group(2)
                pairs.append((elem, val))
                continue

            m_elem_first = re.search(r"\b([A-Z][a-z]?)\s*(\d+(?:\.\d+)?)\b", seg_clean)
            if m_elem_first:
                elem = m_elem_first.group(1)
                val = float(m_elem_first.group(2))
                pairs.append((elem, val))

        if not pairs or bal_elem is None:
            return None

        # Deduplicate while keeping first occurrence.
        dedup: List[Tuple[str, float]] = []
        seen = set()
        for elem, val in pairs:
            if elem in seen:
                continue
            seen.add(elem)
            dedup.append((elem, val))

        known_total = sum(v for _, v in dedup if v is not None)
        bal_value = max(0.0, 100.0 - known_total)

        ordered: List[Tuple[str, float]] = [(bal_elem, bal_value)]
        for elem, val in dedup:
            if elem == bal_elem:
                continue
            ordered.append((elem, val))
        return ordered

    def _bootstrap_datasheet_compositions(self, paper_text: Optional[str]) -> List[dict]:
        """Bootstrap compositions from datasheet-style markdown tables/text.

        Used only as a last fallback when LLM extraction returns no compositions.
        """
        if not paper_text:
            return []
        boot: List[dict] = []
        seen_formula: set[str] = set()

        # 1) Parse markdown table with Tibal column (common in titanium datasheets).
        lines = paper_text.splitlines()
        header_idx = -1
        for i, ln in enumerate(lines):
            if "|" in ln and re.search(r"(?i)\bti\s*bal\b|\btibal\b", ln):
                header_idx = i
                break
        if header_idx >= 0:
            headers = [h.strip() for h in lines[header_idx].split("|") if h.strip()]
            header_keys: List[str] = []
            for h in headers:
                hh = h.lower().replace(" ", "")
                if hh in {"specificationdesignation", "specification", "form(s)", "forms", "form"}:
                    header_keys.append("_meta")
                elif hh in {"tibal", "tibalance", "tibal%"}:
                    header_keys.append("Ti")
                else:
                    m = re.match(r"([A-Z][a-z]?)", h.strip())
                    header_keys.append(m.group(1) if m else "_meta")

            for row in lines[header_idx + 2 :]:
                if "|" not in row:
                    # end of table block
                    if row.strip():
                        break
                    continue
                cells = [c.strip() for c in row.split("|") if c.strip()]
                if len(cells) < 2:
                    continue
                label = cells[0]
                values = cells[1:]
                comp_map: Dict[str, float] = {}
                for idx, cell in enumerate(values):
                    if idx >= len(header_keys) - 1:
                        break
                    elem = header_keys[idx + 1]
                    if elem == "_meta":
                        continue
                    if elem not in self.rules.valid_elements and elem != "Ti":
                        continue
                    mnum = re.search(r"<\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)", cell)
                    if not mnum:
                        continue
                    raw = mnum.group(1) or mnum.group(2)
                    if raw is None:
                        continue
                    val = float(raw)
                    comp_map[elem] = val

                if not comp_map:
                    continue
                if "Ti" not in comp_map:
                    tot = sum(comp_map.values())
                    if 0 < tot < 100:
                        comp_map["Ti"] = 100.0 - tot
                total = sum(comp_map.values())
                if total <= 0 or total > 101:
                    continue

                formula = "".join(
                    f"{el}{self._format_pct(v)}" for el, v in sorted(comp_map.items(), key=lambda kv: (kv[0] != "Ti", kv[0]))
                )
                if not formula or formula in seen_formula:
                    continue
                seen_formula.add(formula)
                boot.append(
                    {
                        "composition": label or formula,
                        "role": "Target",
                        "composition_normalized": formula,
                        "source_doi": None,
                        "properties_of_composition": [],
                    }
                )

        # 2) Parse strict inline "composition ... x% Ti ... y% Fe ..." sentences.
        for ln in lines:
            lower_ln = ln.lower()
            if "%" not in ln or "ti" not in lower_ln:
                continue
            if not any(k in lower_ln for k in ("composition", "wt%", "at.%", "analysis by weight", "impurities")):
                continue
            pairs = re.findall(r"(\d+(?:\.\d+)?)\s*%?\s*([A-Z][a-z]?)(?:2)?", ln)
            if len(pairs) < 2:
                continue
            comp_map: Dict[str, float] = {}
            for num, el in pairs:
                if el not in self.rules.valid_elements:
                    continue
                try:
                    v = float(num)
                    if v < 0 or v > 100:
                        continue
                    comp_map[el] = v
                except Exception:
                    continue
            if len(comp_map) < 3:
                continue
            if "Ti" not in comp_map:
                tot = sum(comp_map.values())
                if 0 < tot < 100:
                    comp_map["Ti"] = 100.0 - tot
            total = sum(comp_map.values())
            if total <= 0 or total > 101:
                continue
            formula = "".join(
                f"{el}{self._format_pct(v)}" for el, v in sorted(comp_map.items(), key=lambda kv: (kv[0] != "Ti", kv[0]))
            )
            if not formula or formula in seen_formula:
                continue
            seen_formula.add(formula)
            boot.append(
                {
                    "composition": formula,
                    "role": "Target",
                    "composition_normalized": formula,
                    "source_doi": None,
                    "properties_of_composition": [],
                }
            )
        return boot

    # ------------------------------------------------------------------
    # Helpers – each is independently testable
    # ------------------------------------------------------------------

    def _normalize_reported_composition(
        self,
        comp_map: Any,
        preferred_balance_element: Optional[str] = None,
    ) -> Optional[Dict[str, float]]:
        """Clean a reported composition map and add/adjust ``other`` to close sum to 100.

        This is used for LLM-extracted nominal/measured compositions where values
        are already in wt%/at% style and should stay faithful to source numbers.
        """
        if not isinstance(comp_map, dict):
            return None

        cleaned: Dict[str, float] = {}
        for raw_key, raw_val in comp_map.items():
            key = str(raw_key).strip()
            if not key:
                continue
            if key != "other" and key not in self.rules.valid_elements:
                continue
            try:
                val = float(raw_val)
            except Exception:
                m = re.search(r"-?\d+(?:\.\d+)?", str(raw_val))
                if not m:
                    continue
                try:
                    val = float(m.group(0))
                except Exception:
                    continue
            cleaned[key] = round(val, 6)

        if not cleaned:
            return None

        non_other_total = sum(v for k, v in cleaned.items() if k != "other")
        balance_delta = round(100.0 - non_other_total, 6)

        # When measured composition omits matrix element (e.g., Ti in EDX table),
        # prefer filling that matrix element by balance instead of pushing into "other".
        if (
            preferred_balance_element
            and preferred_balance_element not in cleaned
            and preferred_balance_element in self.rules.valid_elements
            and balance_delta > 0
        ):
            cleaned[preferred_balance_element] = balance_delta
            return cleaned

        if "other" not in cleaned:
            if balance_delta > 1e-9:
                cleaned["other"] = balance_delta
        else:
            total = sum(cleaned.values())
            if abs(total - 100.0) > 1e-9:
                adjusted_other = round(cleaned["other"] + (100.0 - total), 6)
                if adjusted_other > 1e-9:
                    cleaned["other"] = adjusted_other
                else:
                    cleaned.pop("other", None)

        if "other" in cleaned and cleaned["other"] <= 1e-9:
            cleaned.pop("other", None)

        return cleaned

    def _harmonize_system_element_sets(self, target_compositions: List[dict]) -> List[dict]:
        """Harmonize element sets inside one alloy system cluster.

        Goal: preserve explicit zero-columns (e.g. Ni/Cr/Nb/Mo = 0.00) when the
        paper reports multiple related materials under one shared chemistry table.
        The function is intentionally conservative:
        - clusters are built from configured commercial-alloy aliases;
        - only nominal/measured maps are padded; and
        - residual is always closed by ``other`` to keep sum near 100.
        """
        if not target_compositions:
            return target_compositions

        aliases = self.rules.commercial_alloy_aliases or {}
        if not aliases:
            return target_compositions

        # Union-find to connect aliases that co-occur in blended/graded labels.
        parents: Dict[str, str] = {k: k for k in aliases.keys()}

        def _find(x: str) -> str:
            p = parents.setdefault(x, x)
            while parents.get(p, p) != p:
                parents[p] = parents[parents[p]]
                p = parents[p]
            return p

        def _union(a: str, b: str) -> None:
            ra, rb = _find(a), _find(b)
            if ra != rb:
                parents[rb] = ra

        alias_sets: List[set[str]] = []
        for comp in target_compositions:
            comp_text = str(comp.get("composition") or "")
            norm_text = str(comp.get("composition_normalized") or "")
            alloy_text = str(comp.get("alloy_name_raw") or "")
            proc_text = comp.get("processing_conditions")
            if isinstance(proc_text, dict):
                proc_text = json.dumps(proc_text, ensure_ascii=False)
            joined_text = " ".join(
                part
                for part in (
                    comp_text,
                    norm_text,
                    alloy_text,
                    str(proc_text or ""),
                )
                if part
            )
            present = self._extract_alias_keys(joined_text)
            alias_sets.append(present)
            if len(present) >= 2:
                present_list = sorted(present)
                for i in range(len(present_list) - 1):
                    _union(present_list[i], present_list[i + 1])

        # Build alias-cluster labels so single-alloy rows can inherit zero-columns
        # from related blended/graded rows in the same paper.
        root_members: Dict[str, set[str]] = defaultdict(set)
        for a in parents.keys():
            root_members[_find(a)].add(a)

        group_to_indices: Dict[str, List[int]] = defaultdict(list)
        for idx, present in enumerate(alias_sets):
            if not present:
                continue
            roots = sorted({_find(a) for a in present})
            cluster_members: set[str] = set()
            for r in roots:
                cluster_members.update(root_members.get(r, {r}))
            if not cluster_members:
                cluster_members = present
            gkey = "alias_cluster:" + "+".join(sorted(cluster_members))
            group_to_indices[gkey].append(idx)

        for indices in group_to_indices.values():
            if not indices:
                continue

            union_elements: set[str] = set()
            for idx in indices:
                comp = target_compositions[idx]
                for field in ("nominal_composition", "measured_composition"):
                    cmap = comp.get(field)
                    if not isinstance(cmap, dict):
                        continue
                    for el in cmap.keys():
                        if el in self.rules.valid_elements:
                            union_elements.add(el)

            if not union_elements:
                continue

            for idx in indices:
                comp = target_compositions[idx]
                raw_name = str(comp.get("composition") or "")
                proc_text = comp.get("processing_conditions")
                if isinstance(proc_text, dict):
                    proc_text = json.dumps(proc_text, ensure_ascii=False)
                context_text = str(proc_text or "")

                nominal = comp.get("nominal_composition")
                if not isinstance(nominal, dict) or not nominal:
                    inferred_nominal, inferred_type = self._infer_nominal_from_commercial_name(raw_name)
                    if inferred_nominal is None:
                        inferred_nominal, inferred_type = self._infer_blend_nominal_from_name(
                            raw_name,
                            context_text=context_text,
                        )
                    if inferred_nominal is not None:
                        nominal = inferred_nominal
                        comp["nominal_composition"] = inferred_nominal
                        if not comp.get("nominal_composition_type"):
                            comp["nominal_composition_type"] = inferred_type

                measured = comp.get("measured_composition")
                balance_element = self._pick_balance_element(
                    nominal if isinstance(nominal, dict) else None,
                    raw_name,
                )

                if isinstance(nominal, dict) and any(el in self.rules.valid_elements for el in nominal.keys()):
                    patched_nominal = dict(nominal)
                    for el in union_elements:
                        patched_nominal.setdefault(el, 0.0)
                    normalized_nominal = self._normalize_reported_composition(
                        patched_nominal,
                        preferred_balance_element=balance_element,
                    )
                    if normalized_nominal is not None:
                        comp["nominal_composition"] = normalized_nominal

                if isinstance(measured, dict) and any(el in self.rules.valid_elements for el in measured.keys()):
                    patched_measured = dict(measured)
                    for el in union_elements:
                        patched_measured.setdefault(el, 0.0)
                    normalized_measured = self._normalize_reported_composition(
                        patched_measured,
                        preferred_balance_element=balance_element,
                    )
                    if normalized_measured is not None:
                        comp["measured_composition"] = normalized_measured

        return target_compositions

    def _extract_alias_keys(self, text: str) -> set[str]:
        """Extract known commercial-alloy alias keys from free text."""
        if not text:
            return set()
        txt = text.lower()
        found: set[str] = set()
        for key, syns in (self.rules.commercial_alloy_aliases or {}).items():
            for syn in syns:
                token = str(syn).strip().lower()
                if token and token in txt:
                    found.add(str(key))
                    break
        return found

    def _harmonize_existing_target_materials(self, materials: List[dict]) -> List[dict]:
        """Repair composition fields when input is already in target-schema shape."""
        if not materials:
            return materials

        pseudo: List[dict] = []
        for mat in materials:
            comp_info = mat.get("Composition_Info") or {}

            nominal_block = comp_info.get("Nominal_Composition") or {}
            measured_block = comp_info.get("Measured_Composition") or {}

            nominal_comp = nominal_block.get("Elements_Normalized")
            if nominal_comp is None:
                nominal_comp = comp_info.get("Composition")
            if nominal_comp is None:
                nominal_comp = mat.get("Composition_JSON")

            measured_comp = measured_block.get("Elements_Normalized")
            measured_method = measured_block.get("Measurment_Method")
            if measured_method is None:
                measured_method = measured_block.get("Measurement_Method")
            if measured_method is None:
                measured_method = comp_info.get("Measurement_Method")
            if measured_comp is None and isinstance(comp_info.get("Measured_Composition"), dict):
                maybe_legacy = comp_info.get("Measured_Composition")
                if "Elements_Normalized" not in maybe_legacy:
                    measured_comp = maybe_legacy

            proc_text = ""
            samples = mat.get("Processed_Samples") or []
            if samples and isinstance(samples, list):
                proc_text = str((samples[0] or {}).get("Process_Text_For_AI") or "")
            if not proc_text:
                pinfo = mat.get("Process_Info") or {}
                proc_text = str(pinfo.get("Process_Text_For_AI") or "")
                if not proc_text:
                    ptxt = pinfo.get("Process_Text")
                    if isinstance(ptxt, dict):
                        proc_text = str(ptxt.get("original") or ptxt.get("simplified") or "")
                    elif ptxt:
                        proc_text = str(ptxt)

            pseudo.append(
                {
                    "composition": mat.get("Alloy_Name_Raw")
                    or comp_info.get("Alloy_Name_Raw")
                    or "",
                    "composition_normalized": mat.get("Formula_Normalized")
                    or comp_info.get("Formula_Normalized")
                    or "",
                    "alloy_name_raw": comp_info.get("Alloy_Name_Raw") or mat.get("Alloy_Name_Raw") or "",
                    "processing_conditions": proc_text,
                    "nominal_composition": nominal_comp,
                    "nominal_composition_type": nominal_block.get("Composition_Type")
                    or comp_info.get("Composition_Type"),
                    "measured_composition": measured_comp,
                    "measured_composition_type": measured_block.get("Composition_Type"),
                    "measured_composition_method": measured_method,
                }
            )

        pseudo = self._harmonize_system_element_sets(pseudo)

        out: List[dict] = []
        for mat, p in zip(materials, pseudo):
            patched = dict(mat)
            comp_info = dict(patched.get("Composition_Info") or {})

            nominal_comp = self._normalize_reported_composition(p.get("nominal_composition"))
            measured_comp = self._normalize_reported_composition(
                p.get("measured_composition"),
                preferred_balance_element=self._pick_balance_element(
                    nominal_comp,
                    str(patched.get("Alloy_Name_Raw") or p.get("composition") or ""),
                ),
            )

            nominal_type = p.get("nominal_composition_type")
            measured_type = p.get("measured_composition_type")
            measured_method = p.get("measured_composition_method")

            comp_info["Alloy_Name_Raw"] = (
                comp_info.get("Alloy_Name_Raw")
                or patched.get("Alloy_Name_Raw")
                or p.get("composition")
            )
            comp_info["Nominal_Composition"] = {
                "Composition_Type": nominal_type,
                "Elements_Normalized": nominal_comp,
            }
            comp_info["Measured_Composition"] = {
                "Composition_Type": measured_type,
                "Elements_Normalized": measured_comp,
                "Measurment_Method": measured_method,
            }
            patched["Composition_Info"] = comp_info

            if measured_comp:
                raw_comp_json = dict(measured_comp)
                source = "measured_composition"
            elif nominal_comp:
                raw_comp_json = dict(nominal_comp)
                source = "nominal_composition"
            else:
                raw_comp_json = patched.get("Composition_JSON") or {}
                source = patched.get("Composition_Source") or "unknown"

            formula = str(patched.get("Formula_Normalized") or p.get("composition_normalized") or "")
            validated_comp_json, comp_warnings = self.validate_composition_json(raw_comp_json, formula)
            for warning in comp_warnings:
                logger.warning("[COMPOSITION] %s", warning)

            # Legacy top-level fields are removed; all composition information
            # is expressed under Composition_Info.
            if (
                comp_info.get("Nominal_Composition", {}).get("Elements_Normalized") is None
                and measured_comp is None
                and validated_comp_json
            ):
                comp_info["Nominal_Composition"]["Elements_Normalized"] = validated_comp_json
                comp_info["Nominal_Composition"]["Composition_Type"] = (
                    comp_info["Nominal_Composition"].get("Composition_Type") or "at%"
                )
                patched["Composition_Info"] = comp_info

            samples = patched.get("Processed_Samples") or []
            if not patched.get("Properties_Info"):
                flattened_tests: List[Dict[str, Any]] = []
                graded_hint_text = (
                    f"{patched.get('description', '')} "
                    f"{(patched.get('Composition_Info') or {}).get('Alloy_Name_Raw', '')}"
                ).lower()
                for s in samples:
                    sample_proc_text = str((s or {}).get("Process_Text_For_AI") or "").lower()
                    graded_context = bool(
                        re.search(
                            r"\b(graded|gradient|stepwise|multigraded|increasing|up to \d+(?:\.\d+)?\s*(?:wt\s*%|wt%|%))\b",
                            f"{graded_hint_text} {sample_proc_text}",
                        )
                    )
                    for t in s.get("Performance_Tests", []) or []:
                        if graded_context and t.get("Property_Value_Range"):
                            continue
                        flattened_tests.append(dict(t))
                patched["Properties_Info"] = self._order_properties(flattened_tests)
            else:
                patched["Properties_Info"] = self._order_properties(
                    [dict(t) for t in (patched.get("Properties_Info") or [])]
                )

            if not patched.get("Process_Info") and samples:
                first_sample = samples[0] or {}
                process_text = str(first_sample.get("Process_Text_For_AI") or "not provided")
                patched["Process_Info"] = {
                    "Process_Category": first_sample.get("Process_Category") or "Unknown",
                    "Process_Text": self._to_text_payload(process_text),
                    "Key_Params": self._canonicalize_key_params(first_sample.get("Key_Params_JSON") or {}),
                }
            elif patched.get("Process_Info"):
                pinfo = dict(patched.get("Process_Info") or {})
                key_params_raw = pinfo.get("Key_Params") or pinfo.get("Key_Params_JSON") or {}
                pinfo["Key_Params"] = self._canonicalize_key_params(key_params_raw)
                pinfo.pop("Key_Params_JSON", None)
                ptxt = pinfo.get("Process_Text")
                if isinstance(ptxt, str):
                    pinfo["Process_Text"] = self._to_text_payload(ptxt)
                elif not isinstance(ptxt, dict):
                    alt = pinfo.get("Process_Text_For_AI")
                    pinfo["Process_Text"] = self._to_text_payload(str(alt or "not provided"))
                pinfo.pop("Process_Text_For_AI", None)
                patched["Process_Info"] = pinfo

            if not patched.get("Microstructure_Info") and samples:
                first_sample = samples[0] or {}
                micro_text = str(first_sample.get("Microstructure_Text_For_AI") or "not provided")
                patched["Microstructure_Info"] = {
                    "Microstructure_Text": self._to_text_payload(micro_text),
                    "Main_Phase": first_sample.get("Main_Phase") or None,
                    "Has_Precipitates": first_sample.get("Has_Precipitates"),
                    "Grain_Size_avg_um": first_sample.get("Grain_Size_avg_um"),
                }
            elif patched.get("Microstructure_Info"):
                minfo = dict(patched.get("Microstructure_Info") or {})
                mtxt = minfo.get("Microstructure_Text")
                if isinstance(mtxt, str):
                    minfo["Microstructure_Text"] = self._to_text_payload(mtxt)
                elif not isinstance(mtxt, dict):
                    alt = minfo.get("Microstructure_Text_For_AI")
                    minfo["Microstructure_Text"] = self._to_text_payload(str(alt or "not provided"))
                minfo.pop("Microstructure_Text_For_AI", None)
                patched["Microstructure_Info"] = minfo

            if samples:
                for s in samples:
                    s["Performance_Tests"] = []
                    key_params_raw = s.get("Key_Params_JSON") or s.get("Key_Params") or {}
                    s["Key_Params_JSON"] = self._canonicalize_key_params(key_params_raw)
                    s.pop("Key_Params", None)
                patched["Processed_Samples"] = samples

            patched.pop("Composition_JSON", None)
            patched.pop("Alloy_Name_Raw", None)
            patched.pop("Formula_Normalized", None)
            if "Composition" in patched.get("Composition_Info", {}):
                patched["Composition_Info"].pop("Composition", None)
            patched["Composition_Source"] = source
            out.append(patched)
        return out

    def _pick_balance_element(
        self, nominal_comp: Optional[Dict[str, float]], raw_name: str
    ) -> Optional[str]:
        """Pick matrix element used for balance completion in measured maps."""
        if nominal_comp:
            ranked = sorted(
                ((k, v) for k, v in nominal_comp.items() if k != "other"),
                key=lambda kv: kv[1],
                reverse=True,
            )
            if ranked and ranked[0][0] in self.rules.valid_elements:
                return ranked[0][0]
        inferred_nominal, _ = self._infer_nominal_from_commercial_name(raw_name or "")
        if inferred_nominal:
            ranked = sorted(inferred_nominal.items(), key=lambda kv: kv[1], reverse=True)
            if ranked:
                return ranked[0][0]
        return None

    @staticmethod
    def _is_commercial_shorthand(raw_name: str, formula: str) -> bool:
        """Return True when the token likely represents a commercial grade name."""
        text = f"{raw_name} {formula}".lower().replace(" ", "")
        known = (
            "ti6al4v",
            "ti-6al-4v",
            "in718",
            "inconel718",
            "316l",
            "304l",
            "17-4ph",
            "174ph",
        )
        return any(tok in text for tok in known)

    def _infer_nominal_from_commercial_name(
        self, raw_name: str
    ) -> Tuple[Optional[Dict[str, float]], Optional[str]]:
        """Infer nominal composition for a small set of canonical commercial aliases."""
        if not raw_name:
            return None, None
        name = raw_name.lower().replace(" ", "")
        # Only infer for single-alloy aliases; avoid blended/graded/multi-alloy labels.
        if any(tok in name for tok in ("+", "/", "blend", "graded", "gradient", "wt%", "in718", "inconel")):
            return None, None
        aliases = self.rules.commercial_alloy_aliases or {}
        nominal_maps = self.rules.commercial_nominal_maps or {}
        for key, syns in aliases.items():
            if any(str(s).lower().replace(" ", "") in name for s in syns):
                comp = nominal_maps.get(key)
                if isinstance(comp, dict) and comp:
                    return {
                        str(k): float(v) for k, v in comp.items()
                    }, "wt%"
        return None, None

    def _infer_blend_nominal_from_name(
        self, raw_name: str, context_text: str = ""
    ) -> Tuple[Optional[Dict[str, float]], Optional[str]]:
        """Infer blended nominal composition from labels like 'A + 20 wt% B' or '0-20 wt% B'."""
        if not raw_name:
            raw_name = ""
        txt = f"{raw_name} {context_text or ''}".lower()
        known = self.rules.commercial_nominal_maps or {}
        aliases = self.rules.commercial_alloy_aliases or {}
        if not known or not aliases:
            return None, None

        present: List[str] = []
        for key, syns in aliases.items():
            if any(s in txt for s in syns):
                present.append(key)
        if len(present) < 2:
            return None, None

        pct = None
        additive_key = None
        alias_tokens: List[str] = []
        for syns in aliases.values():
            alias_tokens.extend(re.escape(str(s).lower()) for s in syns if str(s).strip())
        if not alias_tokens:
            return None, None
        alloy_alt = "|".join(sorted(set(alias_tokens), key=len, reverse=True))
        pct_pattern = re.compile(
            rf"(\d+(?:\.\d+)?)\s*(?:-\s*(\d+(?:\.\d+)?)\s*)?(?:wt\s*%|wt%|%\s*wt|%)\s*({alloy_alt})",
            re.IGNORECASE,
        )
        candidates: List[Tuple[float, float, str]] = []
        for m in pct_pattern.finditer(txt):
            lo = float(m.group(1))
            hi = float(m.group(2)) if m.group(2) else lo
            tok = m.group(3).replace(" ", "")
            key_hit = None
            for key, syns in aliases.items():
                if any(s.replace(" ", "") in tok for s in syns):
                    key_hit = key
                    break
            if key_hit:
                candidates.append((lo, hi, key_hit))

        if candidates:
            additive_key = candidates[0][2]
            lo_vals = [lo for lo, _hi, key in candidates if key == additive_key]
            hi_vals = [hi for _lo, hi, key in candidates if key == additive_key]
            lo = min(lo_vals) if lo_vals else None
            hi = max(hi_vals) if hi_vals else None

            # Graded descriptions often write "5% wt ... up to 20%" where upper
            # bound has no trailing alloy token. Use it as the range ceiling.
            if lo is not None and hi is not None:
                graded_hint = any(k in txt for k in ("graded", "gradient", "step"))
                up_to = re.search(r"up\s*to\s*(\d+(?:\.\d+)?)\s*(?:wt\s*%|wt%|%\s*wt|%)", txt)
                if graded_hint and up_to:
                    try:
                        up_to_val = float(up_to.group(1))
                        if up_to_val > hi:
                            hi = up_to_val
                        # Phrases like "steps of 5% ... up to 20%" usually imply
                        # a graded span from 0% to 20%, where 5% is step size.
                        if "step" in txt and lo <= up_to_val * 0.5:
                            lo = 0.0
                    except Exception:
                        pass
                pct = (lo + hi) / 2.0 if hi >= lo else lo
        else:
            # Fallback for graded phrasing like:
            # "increasing IN718 in steps of 5wt% up to 20wt%"
            up_to = re.search(
                r"up\s*to\s*(\d+(?:\.\d+)?)\s*(?:wt\s*%|wt%|%\s*wt|%)",
                txt,
                re.IGNORECASE,
            )
            if up_to and len(present) >= 2:
                graded_hint = any(k in txt for k in ("graded", "gradient", "step", "increasing", "increase"))
                hi = float(up_to.group(1))
                lo = 0.0 if graded_hint else None

                key_scores: Dict[str, int] = {}
                for key in present:
                    score = 0
                    for syn in aliases.get(key, []):
                        syn_l = str(syn).lower()
                        if not syn_l:
                            continue
                        # Strong signal: "increasing/addition ... <alloy>"
                        if re.search(
                            rf"(?:increase|increasing|adding|added|addition|enrich(?:ed|ment)?)\s+[^.]{{0,25}}{re.escape(syn_l)}",
                            txt,
                        ):
                            score += 3
                        # Moderate signal: "<alloy> ... up to xx wt%"
                        if re.search(
                            rf"{re.escape(syn_l)}[^.]{{0,30}}up\s*to\s*\d+(?:\.\d+)?\s*(?:wt\s*%|wt%|%\s*wt|%)",
                            txt,
                        ):
                            score += 2
                    key_scores[key] = score

                additive_key = max(key_scores.items(), key=lambda kv: kv[1])[0]
                if key_scores.get(additive_key, 0) == 0:
                    additive_key = present[-1]
                if lo is not None:
                    pct = (lo + hi) / 2.0 if hi >= lo else lo

        if pct is None or additive_key not in known:
            return None, None
        if pct < 0 or pct > 100:
            return None, None

        base_key = None
        for k in present:
            if k != additive_key and k in known:
                base_key = k
                break
        if base_key is None:
            return None, None

        add_frac = pct / 100.0
        base_frac = 1.0 - add_frac
        comp: Dict[str, float] = {}
        for el in set(known[base_key].keys()) | set(known[additive_key].keys()):
            try:
                base_v = float(known[base_key].get(el, 0.0))
            except Exception:
                base_v = 0.0
            try:
                add_v = float(known[additive_key].get(el, 0.0))
            except Exception:
                add_v = 0.0
            v = base_frac * base_v + add_frac * add_v
            comp[el] = round(v, 6)

        total = sum(comp.values())
        if abs(total - 100.0) > 1e-6:
            residual = round(comp.get("other", 0.0) + (100.0 - total), 6)
            if residual > 0:
                comp["other"] = residual
            else:
                comp.pop("other", None)
        return comp, "wt%"

    @staticmethod
    def parse_temperature_to_k(measurement_condition: Optional[str]) -> Optional[float]:
        """Best-effort parse of temperature from measurement condition text.

        Prioritises ``at XXX K`` format, then general patterns.
        Returns Kelvin as float.
        """
        if not measurement_condition:
            return None
        txt = measurement_condition.lower()

        if re.search(r"\b(rt|room temperature|ambient)\b", txt):
            return 298.15

        m_at = re.search(r"at\s+(-?\d+(?:\.\d+)?)\s*k\b", txt)
        if m_at:
            return round(float(m_at.group(1)), 2)

        m_at_c = re.search(r"at\s+(-?\d+(?:\.\d+)?)\s*(?:°c|\bc\b)\b", txt)
        if m_at_c:
            return round(float(m_at_c.group(1)) + 273.15, 2)

        m = re.search(r"(-?\d+(?:\.\d+)?)\s*(k|°c|\bc\b)\b", txt)
        if not m:
            return None
        value = float(m.group(1))
        unit = m.group(2)
        if unit in {"°c", "c"}:
            return round(value + 273.15, 2)
        return round(value, 2)

    @staticmethod
    def build_composition_json(formula: str) -> dict:
        """Convert formula string like ``Ti42Hf21Nb21V16`` to a composition dict.

        Preferentially uses ``pymatgen.core.Composition`` for robust parsing
        (handles complex formulas, parentheses, fractional stoichiometry, etc.)
        and converts to molar-percentage (at%). ``Bal`` notation (e.g. ``NiBal``)
        is first rewritten to explicit numeric residual content. Falls back to
        regex-based parsing only when *pymatgen* is unavailable or unparseable.
        """
        comp: Dict[str, float] = {}
        if not formula:
            return comp

        def _safe_float(token: Optional[str]) -> Optional[float]:
            if token in (None, ""):
                return None
            try:
                return float(token)
            except Exception:
                m = re.match(r"-?\d+(?:\.\d+)?", str(token))
                if m:
                    try:
                        return float(m.group(0))
                    except Exception:
                        return None
                return None

        subscript_map = str.maketrans(
            {
                "₀": "0",
                "₁": "1",
                "₂": "2",
                "₃": "3",
                "₄": "4",
                "₅": "5",
                "₆": "6",
                "₇": "7",
                "₈": "8",
                "₉": "9",
            }
        )
        cleaned = formula.translate(subscript_map)
        cleaned = cleaned.replace("（", "(").replace("）", ")")
        cleaned = re.sub(r"(?i)\b(at|wt)\s*%?\b", "", cleaned)
        cleaned = re.sub(r"\s+", "", cleaned)
        # Keep parentheses for pymatgen group parsing; strip other separators.
        cleaned = re.sub(r"[^A-Za-z0-9.()]", "", cleaned)

        # Resolve balance notation such as NiBal -> Ni(100 - others).
        token_pattern = r"([A-Z][a-z]?)(Bal|BAL|bal|\d+(?:\.\d+)?)?"
        resolved_for_parse = cleaned
        if "bal" in cleaned.lower():
            flat = re.sub(r"[()]", "", cleaned)
            tokens = re.findall(token_pattern, flat)
            bal_indices = [i for i, (_, amt) in enumerate(tokens) if (amt or "").lower() == "bal"]
            if len(tokens) >= 2 and len(bal_indices) == 1:
                bal_idx = bal_indices[0]
                known_total = 0.0
                for idx, (_, amt) in enumerate(tokens):
                    if idx == bal_idx:
                        continue
                    if amt in (None, ""):
                        known_total += 1.0
                    elif (amt or "").lower() == "bal":
                        continue
                    else:
                        parsed = _safe_float(amt)
                        if parsed is None:
                            logger.debug("Skip non-numeric amount token '%s' in formula '%s'", amt, formula)
                            continue
                        known_total += parsed
                bal_value = max(0.0, 100.0 - known_total)
                rebuilt: List[str] = []
                for idx, (elem, amt) in enumerate(tokens):
                    if idx == bal_idx:
                        value = bal_value
                    elif amt in (None, ""):
                        value = 1.0
                    elif (amt or "").lower() == "bal":
                        value = 1.0
                    else:
                        parsed = _safe_float(amt)
                        value = parsed if parsed is not None else 1.0
                    value_txt = f"{value:.6f}".rstrip("0").rstrip(".")
                    rebuilt.append(f"{elem}{value_txt}")
                resolved_for_parse = "".join(rebuilt)

        candidates: List[str] = []
        if resolved_for_parse:
            candidates.append(resolved_for_parse)
        if cleaned and cleaned != resolved_for_parse:
            candidates.append(cleaned)

        if _PymatgenComposition is not None:
            for candidate in candidates:
                try:
                    pmg_comp = _PymatgenComposition(candidate)
                    frac_dict = pmg_comp.fractional_composition.as_dict()
                    return {el: round(frac * 100, 6) for el, frac in frac_dict.items()}
                except Exception:
                    continue
            logger.debug("pymatgen failed to parse '%s', falling back to regex", formula)

        fallback_src = candidates[0] if candidates else cleaned
        for element, amount in re.findall(r"([A-Z][a-z]?)(\d+(?:\.\d+)?)?", re.sub(r"[()]", "", fallback_src)):
            if not element:
                continue
            comp[element] = float(amount) if amount not in (None, "") else 1.0
        return comp

    def validate_composition_json(
        self, comp_json: dict, formula_source: str = ""
    ) -> Tuple[dict, List[str]]:
        """Validate element symbols and ensure composition is in at% (sums to ~100).

        If values look like atomic ratios (e.g. sum far from 100 but > 0), the
        composition is normalised to 100 at%.
        """
        warnings: List[str] = []
        cleaned: Dict[str, float] = {}

        for elem, val in comp_json.items():
            try:
                parsed_val = float(val)
            except Exception:
                warnings.append(f"Invalid composition value '{val}' for '{elem}' removed from {formula_source}")
                continue
            if str(elem).lower() == "other":
                cleaned["other"] = parsed_val
                continue
            if elem not in self.rules.valid_elements:
                warnings.append(f"Invalid element '{elem}' removed from {formula_source}")
                continue
            cleaned[elem] = parsed_val

        if cleaned:
            total = sum(cleaned.values())
            if total <= 0:
                warnings.append(f"Composition sum = {total:.2f}, invalid total. Formula: {formula_source}")
                return cleaned, warnings

            if "other" in cleaned:
                # For reported wt%/at% maps, keep source values and use `other` to
                # absorb residual so total becomes 100.
                if abs(total - 100) > 1e-6:
                    adjusted_other = round(cleaned["other"] + (100.0 - total), 6)
                    if adjusted_other > 1e-9:
                        cleaned["other"] = adjusted_other
                        warnings.append(
                            f"Composition sum = {total:.2f}; adjusted 'other' to close sum to 100. Formula: {formula_source}"
                        )
                    else:
                        cleaned.pop("other", None)
            else:
                # If clearly not at% already, normalise to at%.
                if abs(total - 100) > 2:
                    normalised = {k: (v / total) * 100.0 for k, v in cleaned.items()}
                    warnings.append(
                        f"Composition sum = {total:.2f} (not ~100). Normalised to 100 at%. Formula: {formula_source}"
                    )
                    cleaned = normalised
        return cleaned, warnings

    @staticmethod
    def extract_first_doi(text: Optional[str]) -> str:
        """Extract first DOI-like token from *text*."""
        if not text:
            return ""
        m = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", text)
        return m.group(0) if m else ""

    def infer_main_phase(self, char_text: str) -> str:
        """Infer main phase from characterisation text using rule patterns."""
        if not char_text:
            return ""
        ctext = char_text.lower()
        phases: List[str] = []
        seen: set = set()
        for pattern, label in self.rules.phase_patterns.items():
            if pattern in ctext and label not in seen:
                phases.append(label)
                seen.add(label)
        if not phases:
            return ""
        return " + ".join(phases[:3])

    def infer_precipitates(self, char_text: str) -> bool:
        """Return *True* if precipitate keywords are found in *char_text*."""
        if not char_text:
            return False
        ctext = char_text.lower()
        return any(kw in ctext for kw in self.rules.precipitate_keywords)

    def parse_key_params(
        self, process_text: str, processing_params: Optional[dict] = None
    ) -> dict:
        """Build structured ``Key_Params_JSON`` from LLM output or regex."""
        params: Dict[str, Any] = {}

        if processing_params and isinstance(processing_params, dict):
            for k, v in processing_params.items():
                if v is not None:
                    params[k] = v

        if not process_text:
            return params

        def _safe_float(token: Any) -> Optional[float]:
            if token is None:
                return None
            txt = str(token).strip()
            try:
                return float(txt)
            except Exception:
                m_num = re.search(r"-?\d+(?:\.\d+)?", txt)
                if not m_num:
                    return None
                try:
                    return float(m_num.group(0))
                except Exception:
                    return None

        for param_name, compiled in self.rules._compiled_param_patterns.items():
            if param_name in params:
                continue
            for pat in compiled:
                m = pat.search(process_text)
                if m:
                    parsed = _safe_float(m.group(1))
                    if parsed is None:
                        logger.debug(
                            "Skip unparsable process param '%s' token '%s' in text '%s'",
                            param_name,
                            m.group(1),
                            process_text[:200],
                        )
                        continue
                    params[param_name] = parsed
                    break

        if re.search(r"\bargon\b", process_text, re.IGNORECASE) and "Protective_Atmosphere" not in params:
            params["Protective_Atmosphere"] = "Argon"
        elif re.search(r"\bnitrogen\b", process_text, re.IGNORECASE) and "Protective_Atmosphere" not in params:
            params["Protective_Atmosphere"] = "Nitrogen"

        for k, v in self._extract_energy_density_params(process_text).items():
            if k not in params:
                params[k] = v

        return self._canonicalize_key_params(params)

    def _canonicalize_key_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Canonicalise process-parameter key names to the current schema."""
        if not params:
            return {}

        out: Dict[str, Any] = {}
        key_alias = {
            "Scan_Speed_mm_s": "Scanning_Speed_mm_s",
            "Shielding_Gas": "Protective_Atmosphere",
            "Process_Gas": "Protective_Atmosphere",
            "Preheat_Temperature_C": "Build_Plate_Temperature_K",
            "Preheat_Temperature_K": "Build_Plate_Temperature_K",
            "Hatch_Distance_um": "Hatch_Spacing_um",
            "Hatch_Distance_um_Range": "Hatch_Spacing_um_Range",
            "Energy_Density_J_mm3": "Volumetric_Energy_Density_J_mm3",
            "Energy_Density_J_mm3_Range": "Volumetric_Energy_Density_J_mm3_Range",
            "Energy_Density_J_mm3_FullDensification": "Volumetric_Energy_Density_J_mm3_FullDensification",
            "Energy_Density_J_mm3_Optimal": "Volumetric_Energy_Density_J_mm3_Optimal",
            "Energy_Density_J_mm3_Optimal_Range": "Volumetric_Energy_Density_J_mm3_Optimal_Range",
        }

        for raw_key, raw_val in params.items():
            key = key_alias.get(str(raw_key), str(raw_key))
            val = raw_val

            if key == "Build_Plate_Temperature_K" and raw_val is not None:
                try:
                    num = float(raw_val)
                    if str(raw_key).endswith("_C"):
                        val = round(num + 273.15, 2)
                    else:
                        val = num
                except Exception:
                    val = raw_val

            if key == "Protective_Atmosphere" and isinstance(val, str):
                vv = val.strip().lower()
                if vv in {"ar", "argon"}:
                    val = "Argon"
                elif vv in {"n2", "nitrogen"}:
                    val = "Nitrogen"
                elif vv in {"vac", "vacuum"}:
                    val = "Vacuum"

            out[key] = val
        return out

    @staticmethod
    def _extract_energy_density_params(process_text: str) -> Dict[str, Any]:
        """Extract energy-density related parameters, preserving threshold ranges."""
        if not process_text:
            return {}
        txt = process_text
        out: Dict[str, Any] = {}

        patt = re.compile(r"(\d+(?:\.\d+)?)\s*J\s*/\s*mm(?:\^?3|3)", re.IGNORECASE)
        dens_vals: List[float] = []
        opt_vals: List[float] = []

        for m in patt.finditer(txt):
            try:
                val = float(m.group(1))
            except Exception:
                continue
            window = txt[max(0, m.start() - 80): min(len(txt), m.end() + 80)].lower()
            is_dens_ctx = any(
                kw in window for kw in ("full dens", "densification", "fully dense", "full dense")
            )
            is_opt_ctx = any(
                kw in window for kw in ("optimal", "optimum", "produced at", "sample shown", "selected")
            )
            if is_dens_ctx:
                dens_vals.append(val)
            elif is_opt_ctx:
                opt_vals.append(val)

        if not dens_vals and not opt_vals:
            all_vals = sorted({float(m.group(1)) for m in patt.finditer(txt)})
            if all_vals:
                if len(all_vals) == 1:
                    out["Energy_Density_J_mm3"] = all_vals[0]
                else:
                    out["Energy_Density_J_mm3_Range"] = (
                        f"{all_vals[0]:g}-{all_vals[-1]:g}"
                    )
            return out

        if dens_vals:
            uniq = sorted(set(dens_vals))
            if len(uniq) == 1:
                out["Energy_Density_J_mm3_FullDensification"] = uniq[0]
            else:
                out["Energy_Density_J_mm3_FullDensification"] = f"{uniq[0]:g}-{uniq[-1]:g}"
        if opt_vals:
            uniq = sorted(set(opt_vals))
            if len(uniq) == 1:
                out["Energy_Density_J_mm3_Optimal"] = uniq[0]
            else:
                out["Energy_Density_J_mm3_Optimal_Range"] = f"{uniq[0]:g}-{uniq[-1]:g}"
        return out

    @staticmethod
    def build_microstructure_text(comp: dict) -> str:
        """Build ``Microstructure_Text_For_AI`` from dedicated fields or legacy characterisation."""
        micro_desc = comp.get("microstructure_description")
        if micro_desc and micro_desc.strip():
            return micro_desc.strip()

        char = comp.get("characterisation")
        if isinstance(char, dict):
            parts = []
            for key in ("Microstructure", "EBSD", "SEM", "TEM"):
                val = char.get(key)
                if val and isinstance(val, str) and val.strip():
                    parts.append(f"{key}: {val.strip()}")
            if parts:
                return "; ".join(parts)
            all_parts = [f"{k}: {v}" for k, v in char.items() if isinstance(v, str) and v.strip()]
            if all_parts:
                return "; ".join(all_parts)

        return "not provided"

    @staticmethod
    def _to_text_payload(text: str) -> Dict[str, str]:
        """Return dual-track text payload with original and simplified variants."""
        original = (text or "not provided").strip() or "not provided"
        explicit = re.search(
            r"original\s*:\s*(.*?)\s*(?:\|\||\n|;\s*)\s*simplified\s*:\s*(.+)$",
            original,
            re.IGNORECASE | re.DOTALL,
        )
        if explicit:
            orig = explicit.group(1).strip() or "not provided"
            simp = explicit.group(2).strip() or orig
            return {"original": orig, "simplified": simp}
        chunks = [c.strip() for c in re.split(r"[;\n]+|(?<=\.)\s+", original) if c.strip()]
        if len(chunks) <= 1:
            simplified = original
        else:
            simplified = " -> ".join(chunks[:4])
        if len(simplified) > 500:
            simplified = simplified[:497].rstrip() + "..."
        return {"original": original, "simplified": simplified}

    def _order_properties(self, tests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Order properties by required priority tiers."""
        if not tests:
            return []

        alias = {
            "microhardness": "Hardness_HV",
            "hardness_hv": "Hardness_HV",
            "hardness": "Hardness_HV",
            "ultimate_compressive_strength": "Ultimate_Strength_Compressive",
            "elongation": "Fracture_Elongation",
            "fracture_strain": "Fracture_Elongation",
            "youngs_modulus": "Elastic_Modulus",
        }
        tier1 = [
            "Yield_Strength",
            "Yield_Strength_Compressive",
            "Ultimate_Tensile_Strength",
            "Ultimate_Strength_Compressive",
            "Fracture_Elongation",
            "Elongation_Compressive",
            "Elastic_Modulus",
            "Hardness_HV",
            "Hardness_HRC",
            "Hardness_HB",
        ]
        tier2 = [
            "Residual_Stress",
            "Impact_Toughness",
            "Fatigue_Strength",
            "Fracture_Toughness",
            "Thermal_Conductivity",
            "Specific_Heat",
            "Coefficient_of_Thermal_Expansion",
            "Electrical_Conductivity",
            "Electrical_Resistivity",
            "Corrosion_Rate",
            "Wear_Rate",
            "Friction_Coefficient",
        ]
        rank1 = {name: i for i, name in enumerate(tier1)}
        rank2 = {name: i for i, name in enumerate(tier2)}
        normalized_tests: List[Dict[str, Any]] = []
        for raw in tests:
            cur = dict(raw)
            prop = str(cur.get("Property_Type") or "").strip()
            canonical_key = re.sub(r"[^a-z0-9]+", "_", prop.lower()).strip("_")
            if canonical_key in alias:
                cur["Property_Type"] = alias[canonical_key]
            normalized_tests.append(cur)

        def _rank(test: Dict[str, Any]) -> Tuple[int, int, str]:
            p = str(test.get("Property_Type") or "")
            if p in rank1:
                return (0, rank1[p], p)
            if p in rank2:
                return (1, rank2[p], p)
            return (2, 9999, p.lower())

        return sorted(normalized_tests, key=_rank)

    def normalize_property_name(self, name: Optional[str]) -> Optional[str]:
        """Map a free-text property name to a standardised column name."""
        if not name:
            return name
        key = name.strip().lower()
        mapped = self.rules.property_name_mapping.get(key)
        if mapped:
            return mapped
        return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")

    def infer_process_category(self, process_text: str, comp_raw: str = "") -> str:
        """Classify manufacturing process from free text."""
        t = (process_text or "").lower()
        c = (comp_raw or "").lower()
        base = "Unknown"
        for category, keywords in self.rules.process_category_keywords.items():
            if any(
                re.search(rf"(?<![A-Za-z0-9]){re.escape(kw.lower())}(?![A-Za-z0-9])", t)
                for kw in keywords
            ):
                base = category
                break

        # SLM is a LPBF sub-family. Use LPBF as the canonical parent category.
        if base == "AM_SLM":
            base = "AM_LPBF"

        if base in {"AM_LPBF", "AM_SLM"}:
            suffixes: List[str] = []
            blend_kw = ("blend", "blending", "premix", "premixed", "double hopper", "mixing chamber")
            graded_kw = ("graded", "multigraded", "gradient", "stepwise", "layers per blend")
            if any(kw in t for kw in blend_kw):
                suffixes.append("Powder_Blending")
            if any(kw in t for kw in graded_kw) or "graded" in c or "gradient" in c:
                suffixes.append("Graded_Composition")
            if suffixes:
                return f"{base} + " + " + ".join(suffixes)

        return base

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_sample(self, comp: dict, mat_idx: int, s_idx: int) -> Dict[str, Any]:
        """Build a single ``Processed_Sample`` entry from a composition dict."""
        comp_raw = comp.get("composition", "") or ""

        match = re.search(r"\[(.*?)\]\s*$", comp_raw)
        bracket_suffix = match.group(1).replace(" ", "_") if match else ""
        orientation = comp.get("build_orientation") or ""
        orientation_suffix = orientation.replace(" ", "_").replace("/", "-") if orientation else ""

        if bracket_suffix and orientation_suffix:
            condition_suffix = f"{bracket_suffix}_{orientation_suffix}"
        elif bracket_suffix:
            condition_suffix = bracket_suffix
        elif orientation_suffix:
            condition_suffix = orientation_suffix
        else:
            condition_suffix = "Default"

        props = comp.get("properties_of_composition", []) or []
        tests: List[Dict[str, Any]] = []
        grain_size_from_props: Optional[float] = None
        process_text_raw = comp.get("processing_conditions")
        process_text_hint = ""
        if isinstance(process_text_raw, dict):
            process_text_hint = json.dumps(process_text_raw, ensure_ascii=False)
        elif process_text_raw:
            process_text_hint = str(process_text_raw)
        graded_context = bool(
            re.search(
                r"\b(graded|gradient|stepwise|multigraded|increasing|up to \d+(?:\.\d+)?\s*(?:wt\s*%|wt%|%))\b",
                f"{comp_raw} {process_text_hint}".lower(),
            )
        )
        for j, p in enumerate(props, start=1):
            numeric_val = p.get("value_numeric")
            prop_std_name = self.normalize_property_name(p.get("property_name"))

            if prop_std_name == "Grain_Size" and numeric_val is not None:
                unit = (p.get("unit") or "").lower().strip()
                if "nm" in unit:
                    grain_size_from_props = numeric_val / 1000.0
                else:
                    grain_size_from_props = numeric_val

            if numeric_val is None:
                continue
            value_range = p.get("value_range")
            if value_range is None and p.get("value_type") == "range":
                value_range = p.get("value")
            measurement_condition_txt = str(p.get("measurement_condition") or "").lower()
            has_spatial_anchor = any(
                kw in measurement_condition_txt for kw in ("top", "bottom", "layer", "height", "position", "zone")
            )
            # Gradient entries often report only an aggregate range across steps.
            # Do not synthesize a midpoint test-point for those aggregate ranges.
            if graded_context and value_range and not has_spatial_anchor:
                continue

            value_stddev = p.get("value_stddev")
            if value_stddev is None:
                value_txt = str(p.get("value") or "")
                m_std = re.search(r"±\s*(-?\d+(?:\.\d+)?)", value_txt)
                if m_std:
                    try:
                        value_stddev = float(m_std.group(1))
                    except Exception:
                        value_stddev = None
            tests.append({
                "Test_ID": f"T{j:03d}",
                "Test_Temperature_K": self.parse_temperature_to_k(p.get("measurement_condition")),
                "Property_Type": prop_std_name,
                "Property_Value": numeric_val,
                "Property_Value_Range": value_range,
                "Property_StdDev": value_stddev,
                "Property_Unit": p.get("unit"),
            })

        process_text = comp.get("processing_conditions")
        if isinstance(process_text, dict):
            process_text = json.dumps(process_text, ensure_ascii=False)

        microstructure_text = self.build_microstructure_text(comp)

        main_phase = comp.get("main_phase")
        if not main_phase:
            main_phase = self.infer_main_phase(microstructure_text)

        has_precipitates_val = comp.get("has_precipitates")
        if has_precipitates_val is None:
            has_precipitates_val = self.infer_precipitates(microstructure_text)

        grain_size_um = comp.get("grain_size_avg_um")
        if grain_size_um is None and grain_size_from_props is not None:
            grain_size_um = grain_size_from_props

        process_category = comp.get("process_category")
        inferred_process_category = self.infer_process_category(process_text or "", comp_raw=comp_raw)
        if (
            not process_category
            or process_category == "Unknown"
            or str(process_category).strip().upper() in {"AM", "ADDITIVE_MANUFACTURING"}
        ):
            process_category = inferred_process_category
        elif inferred_process_category != "Unknown":
            current = str(process_category).strip()
            # Prefer more specific inferred categories (e.g., + Powder_Blending / + Graded_Composition)
            if ("+" in inferred_process_category and "+" not in current) or (
                current == "AM_SLM" and inferred_process_category.startswith("AM_LPBF")
            ):
                process_category = inferred_process_category

        key_params = self.parse_key_params(process_text or "", comp.get("processing_params"))
        if orientation and "Build_Orientation" not in key_params:
            key_params["Build_Orientation"] = orientation

        return {
            "Sample_ID": f"S{mat_idx:03d}_{s_idx:02d}_{condition_suffix}",
            "Process_Category": process_category,
            "Process_Text_For_AI": process_text or "not provided",
            "Key_Params_JSON": key_params,
            "Main_Phase": main_phase or "",
            "Microstructure_Text_For_AI": microstructure_text,
            "Has_Precipitates": has_precipitates_val,
            "Grain_Size_avg_um": grain_size_um,
            "Performance_Tests": tests,
        }
