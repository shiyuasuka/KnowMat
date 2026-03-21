"""OCR-only regression report for KnowMat.

Evaluates OCR output quality without any LLM involvement.  Metrics:

1. **Chemical formula parse rate** – fraction of ``ocr_items`` paragraphs that
   contain element-number sequences *with* LaTeX subscript notation
   (``_{N}``), indicating successful normalisation.
2. **Decimal error count** – occurrences of digit-comma-digit patterns
   (``61,3``) that should have been normalised to ``61.3``.
3. **Table structure rate** – fraction of table items that have structured
   ``rows`` (vs. only ``raw_html`` / plain text fallback).
4. **Section leakage** – whether Keywords / DOI / page numbers appear within
   ±5 lines of the Abstract heading in the final markdown.

Usage
-----
    python scripts/ocr_regression_report.py [sample_dir] [--json]

``sample_dir`` defaults to ``data/raw``.  Each sub-directory that contains a
``*_final_output.md`` and/or ``*.json`` file is treated as one paper sample.

With ``--json`` the report is printed as JSON; otherwise a human-readable
table is printed to stdout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure `import knowmat` works when the project is run from source.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

# ---------------------------------------------------------------------------
# Element pattern (same as section_normalizer but self-contained here).
# ---------------------------------------------------------------------------
_ELEMENT_SYMBOLS = (
    "He", "Li", "Be", "Ne", "Na", "Mg", "Al", "Si", "Cl", "Ar",
    "Ca", "Sc", "Ti", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Zr", "Nb",
    "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn", "Sb",
    "Te", "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd", "Pm", "Sm",
    "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu", "Hf",
    "Ta", "Re", "Os", "Ir", "Pt", "Au", "Hg", "Tl", "Pb", "Bi",
    "B", "C", "N", "O", "F", "P", "S", "K", "V", "Y", "I", "W", "U",
)
_ELEM_PAT = "|".join(re.escape(e) for e in _ELEMENT_SYMBOLS)

# Bare alloy formula (no subscript): e.g. Ti42Hf21
_BARE_ALLOY_RE = re.compile(
    r"\b(?:" + _ELEM_PAT + r")\d+(?:[.,]\d+)?(?:(?:" + _ELEM_PAT + r")\d+(?:[.,]\d+)?)+\b"
)
# Normalised alloy formula (with LaTeX subscript): e.g. Ti_{42}Hf_{21}
_NORM_ALLOY_RE = re.compile(
    r"\b(?:" + _ELEM_PAT + r")_\{\d+(?:\.\d+)?\}(?:(?:" + _ELEM_PAT + r")_\{\d+(?:\.\d+)?\})+\b"
)
# Decimal error: digit, comma/Chinese comma, digit
_DECIMAL_ERR_RE = re.compile(r"\d[，,]\d")

# Section leakage patterns
_ABSTRACT_RE = re.compile(r"^#+\s*ABSTRACT\s*$", re.IGNORECASE | re.MULTILINE)
_LEAKAGE_PATTERNS = [
    re.compile(r"\bKeywords?\s*:", re.IGNORECASE),
    re.compile(r"\b10\.\d{4,}/", re.IGNORECASE),  # DOI
    re.compile(r"^\s*\d{1,4}\s*$", re.MULTILINE),  # bare page number
]


# ---------------------------------------------------------------------------
# Per-sample analysis helpers
# ---------------------------------------------------------------------------

def _analyse_md(md_text: str) -> Dict[str, Any]:
    """Analyse a markdown string for OCR quality metrics."""
    bare_count = len(_BARE_ALLOY_RE.findall(md_text))
    norm_count = len(_NORM_ALLOY_RE.findall(md_text))
    total_alloy = bare_count + norm_count
    chem_rate = norm_count / total_alloy if total_alloy > 0 else None

    decimal_errors = len(_DECIMAL_ERR_RE.findall(md_text))

    # Section leakage: look ±5 lines around Abstract heading.
    leakage_found: List[str] = []
    lines = md_text.splitlines()
    abstract_lines = [
        i for i, ln in enumerate(lines) if _ABSTRACT_RE.match(ln.strip())
    ]
    for abs_line in abstract_lines:
        window_start = max(0, abs_line - 5)
        window_end = min(len(lines), abs_line + 6)
        window = "\n".join(lines[window_start:window_end])
        for pat in _LEAKAGE_PATTERNS:
            if pat.search(window):
                leakage_found.append(pat.pattern)

    return {
        "bare_alloy_count": bare_count,
        "norm_alloy_count": norm_count,
        "total_alloy_mentions": total_alloy,
        "chem_formula_rate": round(chem_rate, 3) if chem_rate is not None else None,
        "decimal_errors": decimal_errors,
        "section_leakage": list(set(leakage_found)),
        "has_section_leakage": bool(leakage_found),
    }


def _analyse_json(ocr_json: Any) -> Dict[str, Any]:
    """Analyse an OCR items JSON for table structure metrics."""
    # The project supports multiple JSON layouts:
    # 1) KnowMat local format: a list/dict containing items with `typer`.
    # 2) StarRiver format: a list of page results; each has prunedResult.parsing_res_list.
    #    We convert parsing_res_list blocks into our canonical items via block_to_item().
    from knowmat.pdf.blocks import block_to_item

    items: List[Dict[str, Any]] = []

    # Case A: already-canonical items list (has `typer`).
    if isinstance(ocr_json, list) and ocr_json:
        if isinstance(ocr_json[0], dict) and "typer" in ocr_json[0]:
            items = [it for it in ocr_json if isinstance(it, dict)]

    # Case B: KnowMat dict wrapper.
    if not items and isinstance(ocr_json, dict):
        maybe_items = ocr_json.get("ocr_items", [])
        if isinstance(maybe_items, list) and maybe_items and isinstance(maybe_items[0], dict) and "typer" in maybe_items[0]:
            items = [it for it in maybe_items if isinstance(it, dict)]

    # Case C: StarRiver-like layout (list of page result dicts).
    if not items and isinstance(ocr_json, list):
        for page in ocr_json:
            if not isinstance(page, dict):
                continue
            pr = page.get("prunedResult", {})
            if not isinstance(pr, dict):
                continue
            blocks = pr.get("parsing_res_list", []) or []
            if not isinstance(blocks, list):
                continue
            for blk in blocks:
                if not isinstance(blk, dict):
                    continue
                item = block_to_item(blk)
                if item:
                    items.append(item)

    table_items = [it for it in items if isinstance(it, dict) and it.get("typer") == "table"]
    formula_items = [it for it in items if isinstance(it, dict) and it.get("typer") == "formula"]
    paragraph_items = [it for it in items if isinstance(it, dict) and it.get("typer") == "paragraph"]

    structured_tables = 0
    raw_html_only_tables = 0
    for t in table_items:
        data = t.get("data", {})
        if isinstance(data, dict) and "rows" in data and data["rows"]:
            structured_tables += 1
        else:
            raw_html_only_tables += 1

    table_struct_rate = (
        structured_tables / len(table_items) if table_items else None
    )

    return {
        "total_items": len(items),
        "paragraph_items": len(paragraph_items),
        "table_items": len(table_items),
        "formula_items": len(formula_items),
        "structured_tables": structured_tables,
        "raw_html_only_tables": raw_html_only_tables,
        "table_struct_rate": round(table_struct_rate, 3) if table_struct_rate is not None else None,
    }


# ---------------------------------------------------------------------------
# Sample discovery
# ---------------------------------------------------------------------------

def _find_samples(sample_dir: Path) -> List[Tuple[str, Optional[Path], Optional[Path]]]:
    """Return list of (name, md_path, json_path) for each paper in *sample_dir*."""
    samples: List[Tuple[str, Optional[Path], Optional[Path]]] = []
    final_md_glob = "*_final_output.md"

    # StarRiver/社区在线输出格式：*_by_PaddleOCR-VL-1.5.md 与对应的 .json 在同目录。
    st_md_files = sorted(sample_dir.glob("*_by_PaddleOCR-VL-1.5.md"))
    if st_md_files:
        for md_path in st_md_files:
            json_path = md_path.with_suffix(".json")
            paper_name = md_path.stem.replace("_by_PaddleOCR-VL-1.5", "")
            samples.append((paper_name, md_path, json_path if json_path.exists() else None))
        return samples

    # KnowMat 本地格式：*_final_output.md 可能在任意层级出现。
    final_md_files = sorted(sample_dir.rglob(final_md_glob))
    if final_md_files:
        for md_path in final_md_files:
            json_path = md_path.with_suffix(".json")
            name = md_path.parent.name if md_path.parent != sample_dir else md_path.stem
            samples.append((name, md_path, json_path if json_path.exists() else None))
        return samples

    # Backward-compat: 旧的“每个 paper 单独目录”假设。
    for subdir in sorted(sample_dir.iterdir()):
        if not subdir.is_dir():
            continue
        md_files = list(subdir.glob(final_md_glob))
        json_files = list(subdir.glob("*.json"))
        parse_subdir = subdir / "paddleocrvl_parse"
        if parse_subdir.is_dir():
            md_files = list(parse_subdir.glob(final_md_glob)) or md_files
            json_files = list(parse_subdir.glob("*.json")) or json_files

        md_path = md_files[0] if md_files else None
        json_path = json_files[0] if json_files else None
        if md_path or json_path:
            samples.append((subdir.name, md_path, json_path))

    return samples


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _generate_report(sample_dir: Path) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []

    samples = _find_samples(sample_dir)
    if not samples:
        print(f"[warn] No samples found in {sample_dir}", file=sys.stderr)
        return results

    for name, md_path, json_path in samples:
        entry: Dict[str, Any] = {"paper": name}

        if md_path and md_path.exists():
            try:
                md_text = md_path.read_text(encoding="utf-8", errors="ignore")
                entry.update(_analyse_md(md_text))
            except OSError as exc:
                entry["md_error"] = str(exc)

        if json_path and json_path.exists():
            try:
                ocr_json = json.loads(json_path.read_text(encoding="utf-8", errors="ignore"))
                entry.update(_analyse_json(ocr_json))
            except (OSError, json.JSONDecodeError) as exc:
                entry["json_error"] = str(exc)

        results.append(entry)

    return results


def _print_table(results: List[Dict[str, Any]]) -> None:
    """Print a human-readable summary table."""
    cols = [
        ("paper", 40),
        ("chem_formula_rate", 18),
        ("decimal_errors", 15),
        ("table_struct_rate", 18),
        ("has_section_leakage", 20),
        ("total_items", 12),
        ("formula_items", 14),
    ]
    header = " | ".join(f"{name:<{w}}" for name, w in cols)
    sep = "-+-".join("-" * w for _, w in cols)
    print(header)
    print(sep)
    for r in results:
        row = " | ".join(
            f"{str(r.get(name, 'N/A')):<{w}}" for name, w in cols
        )
        print(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR-only regression report for KnowMat.")
    parser.add_argument(
        "sample_dir",
        nargs="?",
        default="data/raw",
        help="Directory containing paper sub-directories (default: data/raw).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON instead of a human-readable table.",
    )
    args = parser.parse_args()

    sample_dir = Path(args.sample_dir)
    if not sample_dir.exists():
        print(f"[error] Sample directory not found: {sample_dir}", file=sys.stderr)
        sys.exit(1)

    results = _generate_report(sample_dir)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        if not results:
            print("No samples found.")
            return
        _print_table(results)

        # Aggregate summary.
        chem_rates = [r["chem_formula_rate"] for r in results if r.get("chem_formula_rate") is not None]
        table_rates = [r["table_struct_rate"] for r in results if r.get("table_struct_rate") is not None]
        decimal_total = sum(r.get("decimal_errors", 0) for r in results)
        leakage_count = sum(1 for r in results if r.get("has_section_leakage"))

        print()
        print("=== AGGREGATE SUMMARY ===")
        if chem_rates:
            print(f"  Avg chemical formula rate : {sum(chem_rates)/len(chem_rates):.1%}  ({len(chem_rates)} papers)")
        else:
            print("  Avg chemical formula rate : N/A")
        if table_rates:
            print(f"  Avg table structure rate  : {sum(table_rates)/len(table_rates):.1%}  ({len(table_rates)} papers)")
        else:
            print("  Avg table structure rate  : N/A")
        print(f"  Total decimal errors      : {decimal_total}")
        print(f"  Papers with section leak  : {leakage_count} / {len(results)}")


if __name__ == "__main__":
    main()
