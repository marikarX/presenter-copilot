"""File-type parser adapters."""

from .base import SourceParser
from .pdf import PdfParser
from .pptx import PptxParser
from .registry import parser_for
from .text import TextParser

__all__ = ["PdfParser", "PptxParser", "SourceParser", "TextParser", "parser_for"]
