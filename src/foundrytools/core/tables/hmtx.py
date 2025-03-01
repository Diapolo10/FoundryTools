"""HMTX table."""

from __future__ import annotations

from typing import TYPE_CHECKING

from foundrytools.constants import T_HMTX
from foundrytools.core.tables.default import DefaultTbl

if TYPE_CHECKING:
    from fontTools.ttLib import TTFont
    from fontTools.ttLib.tables._h_m_t_x import table__h_m_t_x


class HmtxTable(DefaultTbl):
    """Extend the fontTools ``hmtx`` table."""

    def __init__(self, ttfont: TTFont) -> None:
        """
        Initialize the ``hmtx`` table handler.

        :param ttfont: The ``TTFont`` object.
        :type ttfont: TTFont
        """
        super().__init__(ttfont=ttfont, table_tag=T_HMTX)

    @property
    def table(self) -> table__h_m_t_x:
        """The wrapped ``table__h_m_t_x`` table object."""
        return self._table

    @table.setter
    def table(self, value: table__h_m_t_x) -> None:
        """Wrap a new ``table__h_m_t_x`` object."""
        self._table = value

    def fix_non_breaking_space_width(self) -> bool:
        """
        Set the width of the non-breaking space glyph to be the same as the space glyph.

        :raises ValueError: If the space or non-breaking space glyphs do not exist.
        """
        best_cmap = self.ttfont.getBestCmap()
        space_glyph = best_cmap.get(0x0020)
        nbsp_glyph = best_cmap.get(0x00A0)
        if nbsp_glyph is None or space_glyph is None:
            msg = "Both the space and non-breaking space glyphs must exist."
            raise ValueError(msg)

        # Set the width of the non-breaking space glyph
        if self.table.metrics[nbsp_glyph] != self.table.metrics[space_glyph]:
            self.table.metrics[nbsp_glyph] = self.table.metrics[space_glyph]
            return True

        return False
