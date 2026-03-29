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
                return self._expand_variable_materials_in_target_schema(  # type: ignore[return-value]
                    data, paper_text
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
        target_count = len(target_compositions)

        groups: Dict[str, list] = defaultdict(list)
        for comp in target_compositions:
            comp_raw = comp.get("composition", "") or ""
            formula_norm = comp.get("composition_normalized")
            if not formula_norm:
                formula_norm = comp_raw.replace(" ", "")
            recovered_formula = self._recover_formula_from_paper_text(
                paper_text=paper_text,
                comp_raw=comp_raw,
                fallback_formula=formula_norm,
                target_count=target_count,
            )
            if recovered_formula:
                formula_norm = recovered_formula
            base_formula = re.sub(r"\s*\[.*?\]\s*$", "", formula_norm).strip()
            if not base_formula:
                base_formula = formula_norm
            groups[base_formula].append(comp)

        materials: List[Dict[str, Any]] = []

        for mat_idx, (base_formula, comps) in enumerate(sorted(groups.items()), start=1):
            first_comp = comps[0]
            comp_raw_first = first_comp.get("composition", "") or ""
            # Prefer metadata / regex DOI over LLM-filled source_doi to reduce fabrication.
            material_doi = (global_doi or "").strip() or (first_comp.get("source_doi") or "").strip() or ""

            samples: List[Dict[str, Any]] = []
            for s_idx, comp in enumerate(comps, start=1):
                samples.append(self._build_sample(comp, mat_idx, s_idx))

            raw_comp_json = self.build_composition_json(base_formula)
            validated_comp_json, comp_warnings = self.validate_composition_json(
                raw_comp_json, base_formula
            )
            for warning in comp_warnings:
                logger.warning("[COMPOSITION] %s", warning)

            material = {
                "description": f"--- Material {mat_idx}: {base_formula} ---",
                "Mat_ID": f"M{mat_idx:03d}",
                "Alloy_Name_Raw": comp_raw_first,
                "Formula_Normalized": base_formula,
                "Composition_JSON": validated_comp_json,
                "Source_DOI": material_doi or "",
                "Source_File": source_name,
                "Processed_Samples": samples,
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
            haystack = f"{mat.get('Alloy_Name_Raw', '')} {mat.get('Formula_Normalized', '')}".lower()
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
                code = self._extract_variant_code(
                    f"{mat.get('Alloy_Name_Raw', '')} {mat.get('Formula_Normalized', '')}",
                    family_spec["variable_element"],
                )
                if code in expected_codes:
                    new_family_materials.append(mat)

        for variant in family_spec["variants"]:
            if variant["code"] in existing_codes:
                continue
            clone = dict(base_material)
            clone["Alloy_Name_Raw"] = variant["label"]
            clone["Formula_Normalized"] = variant["normalized"]
            raw_comp_json = self.build_composition_json(variant["normalized"])
            validated_comp_json, _ = self.validate_composition_json(
                raw_comp_json, variant["normalized"]
            )
            clone["Composition_JSON"] = validated_comp_json
            # Do not fabricate per-variant properties when source variant is absent.
            clone["Processed_Samples"] = []
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
            mat["description"] = f"--- Material {idx}: {mat.get('Formula_Normalized', '')} ---"

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

    @staticmethod
    def parse_temperature_to_k(measurement_condition: Optional[str]) -> Optional[int]:
        """Best-effort parse of temperature from measurement condition text.

        Prioritises ``at XXX K`` format, then general patterns.
        Returns integer Kelvin.
        """
        if not measurement_condition:
            return None
        txt = measurement_condition.lower()

        m_at = re.search(r"at\s+(-?\d+(?:\.\d+)?)\s*k\b", txt)
        if m_at:
            return round(float(m_at.group(1)))

        m = re.search(r"(-?\d+(?:\.\d+)?)\s*(k|°c|\bc\b)\b", txt)
        if not m:
            return None
        value = float(m.group(1))
        unit = m.group(2)
        if unit in {"°c", "c"}:
            return round(value + 273.15)
        return round(value)

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
            if elem not in self.rules.valid_elements:
                warnings.append(f"Invalid element '{elem}' removed from {formula_source}")
                continue
            cleaned[elem] = val

        if cleaned:
            total = sum(cleaned.values())
            if total <= 0:
                warnings.append(f"Composition sum = {total:.2f}, invalid total. Formula: {formula_source}")
                return cleaned, warnings

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
        if params:
            return params

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

        if re.search(r"\bargon\b", process_text, re.IGNORECASE):
            params["Shielding_Gas"] = "Ar"
        elif re.search(r"\bnitrogen\b", process_text, re.IGNORECASE):
            params["Shielding_Gas"] = "N2"

        return params

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

    def normalize_property_name(self, name: Optional[str]) -> Optional[str]:
        """Map a free-text property name to a standardised column name."""
        if not name:
            return name
        key = name.strip().lower()
        mapped = self.rules.property_name_mapping.get(key)
        if mapped:
            return mapped
        return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")

    def infer_process_category(self, process_text: str) -> str:
        """Classify manufacturing process from free text."""
        t = (process_text or "").lower()
        for category, keywords in self.rules.process_category_keywords.items():
            if any(kw in t for kw in keywords):
                return category
        return "Unknown"

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
            tests.append({
                "Test_ID": f"T{j:03d}",
                "Test_Temperature_K": self.parse_temperature_to_k(p.get("measurement_condition")),
                "Property_Type": prop_std_name,
                "Property_Value": numeric_val,
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
        if not process_category or process_category == "Unknown":
            process_category = self.infer_process_category(process_text or "")

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
