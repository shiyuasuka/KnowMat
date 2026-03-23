"""Heading detection and level assignment for OCR output.

This module provides functions to detect and classify section headings
in scientific documents, supporting both numbered sections (1., 1.1, 1.1.1)
and common section titles (Introduction, Methods, Results, etc.).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Heading pattern definitions
# ---------------------------------------------------------------------------

# Multi-level numbered heading patterns
# Level 1: 1. Introduction
# Level 2: 1.1 Material design
# Level 3: 1.1.1 Sample preparation
_NUMBERED_HEADING_PATTERNS: List[Tuple[re.Pattern, int]] = [
    # Level 3: 1.1.1 Title (three-level numbering)
    (re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{1,2})\.?\s+([A-Z][A-Za-z\s\-]+)$"), 3),
    # Level 2: 1.1 Title (two-level numbering)
    (re.compile(r"^(\d{1,2})\.(\d{1,2})\.?\s+([A-Z][A-Za-z\s\-]+)$"), 2),
    # Level 1: 1. Title (single-level numbering)
    (re.compile(r"^(\d{1,2})\.?\s+([A-Z][A-Za-z\s\-]+)$"), 1),
]


def _title_looks_like_figure_chart_axis(title: str) -> bool:
    """True if OCR line looks like a plot axis / LaTeX fragment, not a section title."""
    t = title.strip()
    if not t:
        return True
    low = t.lower()
    if "\\" in t or "/nm" in low or "isocomposition" in low:
        return True
    if "at.%" in low or "at. %" in low:
        return True
    if "theta" in low and any(c in t for c in "^\\/"):
        return True
    if re.search(r"\\circ|\\theta|/\^", t):
        return True
    if re.match(r"^\d+/\w", t):
        return True
    # Standalone axis labels (not "2. Introduction")
    if low in ("theta", "phi", "psi", "intensity", "strain"):
        return True
    # Supplementary / temperature fragments mis-split as "N. Title"
    if t.startswith("(SI)") or t.startswith("(si)"):
        return True
    if re.match(r"^K[, ]", t):
        return True
    return False

# Common section titles in scientific papers (case-insensitive)
# These are typically Level 1 headings
_COMMON_SECTION_TITLES: List[Tuple[str, int]] = [
    # Standard paper structure
    ("Abstract", 1),
    ("Introduction", 1),
    ("Materials and Methods", 1),
    ("Methods", 1),
    ("Experimental", 1),
    ("Experimental Procedures", 1),
    ("Experimental Details", 1),
    ("Results", 1),
    ("Results and Discussion", 1),
    ("Discussion", 1),
    ("Conclusions", 1),
    ("Conclusion", 1),
    ("Acknowledgements", 1),
    ("Acknowledgments", 1),
    ("References", 1),
    ("Bibliography", 1),
    ("Appendix", 1),
    ("Supplementary Material", 1),
    ("Supplementary Materials", 1),
    # Additional common sections
    ("Background", 1),
    ("Literature Review", 1),
    ("Theoretical Framework", 1),
    ("Theory", 1),
    ("Computational Methods", 1),
    ("Characterization", 1),
    ("Analysis", 1),
    ("Summary", 1),
    ("Data Availability", 1),
    ("Author Contributions", 1),
    ("Declaration of Interest", 1),
    ("Declaration of Competing Interest", 1),
    ("Funding", 1),
]

# Compile case-insensitive patterns for common titles
_COMMON_TITLE_PATTERNS: List[Tuple[re.Pattern, str, int]] = [
    (re.compile(rf"^(?:#+\s*)?{re.escape(title)}\s*$", re.IGNORECASE), title, level)
    for title, level in _COMMON_SECTION_TITLES
]


@dataclass
class Heading:
    """Represents a detected heading with its properties."""
    
    text: str
    level: int
    number: Optional[str] = None
    title: Optional[str] = None
    start_pos: int = 0
    end_pos: int = 0
    
    def to_markdown(self) -> str:
        """Convert heading to Markdown format with appropriate level."""
        prefix = "#" * self.level
        if self.number and self.title:
            return f"{prefix} {self.number}. {self.title}"
        elif self.number:
            return f"{prefix} {self.number}. {self.text}"
        else:
            return f"{prefix} {self.text}"


def detect_numbered_heading(line: str) -> Optional[Heading]:
    """Detect if a line is a numbered heading (e.g., "1. Introduction").
    
    Parameters
    ----------
    line : str
        The line to check for a numbered heading.
        
    Returns
    -------
    Optional[Heading]
        A Heading object if detected, None otherwise.
    """
    stripped = line.strip()
    
    for pattern, level in _NUMBERED_HEADING_PATTERNS:
        match = pattern.match(stripped)
        if match:
            groups = match.groups()
            
            if level == 1:
                # 1. Title
                number = groups[0]
                title = groups[1].strip()
            elif level == 2:
                # 1.1 Title
                number = f"{groups[0]}.{groups[1]}"
                title = groups[2].strip()
            else:
                # 1.1.1 Title
                number = f"{groups[0]}.{groups[1]}.{groups[2]}"
                title = groups[3].strip()

            if _title_looks_like_figure_chart_axis(title):
                continue
            
            return Heading(
                text=stripped,
                level=level + 1,  # Markdown levels start at 1 for H1, we want H2 for level-1 sections
                number=number,
                title=title,
            )
    
    return None


def detect_common_title(line: str) -> Optional[Heading]:
    """Detect if a line is a common section title (e.g., "Introduction").
    
    Parameters
    ----------
    line : str
        The line to check for a common section title.
        
    Returns
    -------
    Optional[Heading]
        A Heading object if detected, None otherwise.
    """
    stripped = line.strip()
    
    for pattern, title, level in _COMMON_TITLE_PATTERNS:
        if pattern.match(stripped):
            return Heading(
                text=title,  # Use standardized title
                level=2,  # Common sections are typically H2 in Markdown
                title=title,
            )
    
    return None


def detect_heading(line: str) -> Optional[Heading]:
    """Detect any type of heading in a line.
    
    This is the main entry point for heading detection, checking both
    numbered headings and common section titles.
    
    Parameters
    ----------
    line : str
        The line to check for a heading.
        
    Returns
    -------
    Optional[Heading]
        A Heading object if detected, None otherwise.
    """
    # First check for numbered headings (higher priority)
    heading = detect_numbered_heading(line)
    if heading:
        return heading
    
    # Then check for common section titles
    return detect_common_title(line)


def process_document_headings(text: str) -> str:
    """Process a document and convert detected headings to Markdown format.
    
    This function processes each line of text, detecting headings and
    converting them to appropriate Markdown heading levels.
    
    Parameters
    ----------
    text : str
        The input document text.
        
    Returns
    -------
    str
        The text with headings converted to Markdown format.
    """
    lines: List[str] = []
    
    for line in text.splitlines():
        heading = detect_heading(line)
        if heading:
            # Add blank lines around headings for proper Markdown formatting
            lines.append("")
            lines.append(heading.to_markdown())
            lines.append("")
        else:
            lines.append(line)
    
    result = "\n".join(lines)
    
    # Clean up excessive blank lines
    result = re.sub(r"\n{3,}", "\n\n", result)
    
    return result.strip()


def extract_heading_hierarchy(text: str) -> List[Heading]:
    """Extract all headings from a document with their hierarchy.
    
    This is useful for generating a table of contents or understanding
    the document structure.
    
    Parameters
    ----------
    text : str
        The input document text.
        
    Returns
    -------
    List[Heading]
        A list of all detected headings in document order.
    """
    headings: List[Heading] = []
    pos = 0
    
    for line in text.splitlines():
        heading = detect_heading(line)
        if heading:
            heading.start_pos = pos
            heading.end_pos = pos + len(line)
            headings.append(heading)
        pos += len(line) + 1  # +1 for newline character
    
    return headings


def infer_heading_level_from_font(
    text: str,
    font_size: Optional[float] = None,
    is_bold: bool = False,
) -> int:
    """Infer heading level from font characteristics.
    
    This function can be used when font metadata is available from
    the OCR engine to help determine heading levels.
    
    Parameters
    ----------
    text : str
        The text content.
    font_size : Optional[float]
        The font size (relative to normal text).
    is_bold : bool
        Whether the text is bold.
        
    Returns
    -------
    int
        The inferred heading level (1-6), or 0 if not a heading.
    """
    # Heuristics based on font size and boldness
    if font_size is None:
        return 0
    
    # Larger fonts are likely headings
    if font_size >= 1.5:  # 150% of normal
        return 1
    elif font_size >= 1.3:  # 130% of normal
        return 2
    elif font_size >= 1.15:  # 115% of normal
        return 3
    elif is_bold and len(text) < 100:  # Bold short text might be a heading
        return 4
    
    return 0