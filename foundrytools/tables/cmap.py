from copy import deepcopy

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._c_m_a_p import table__c_m_a_p

from foundrytools.constants import T_CMAP
from foundrytools.tables.default import DefaultTbl


class CmapTable(DefaultTbl):  # pylint: disable=too-few-public-methods
    """This class extends the fontTools ``cmap`` table."""

    def __init__(self, ttfont: TTFont) -> None:
        """
        Initializes the ``cmap`` table handler.

        :param ttfont: The ``TTFont`` object.
        :type ttfont: TTFont
        """
        super().__init__(ttfont=ttfont, table_tag=T_CMAP)
        self._copy = deepcopy(self.table)

    @property
    def table(self) -> table__c_m_a_p:
        """
        Returns the ``cmap`` table object.

        :return: The ``cmap`` table object.
        :rtype: table__c_m_a_p
        """
        return self._table

    @table.setter
    def table(self, value: table__c_m_a_p) -> None:
        """
        Sets the ``cmap`` table object.

        :param value: The ``cmap`` table object.
        :type value: table__c_m_a_p
        """
        self._table = value

    @property
    def is_modified(self) -> bool:
        """
        Returns whether the ``cmap`` table has been modified.

        :return: Whether the ``cmap`` table has been modified.
        :rtype: bool
        """
        return self._copy.compile(self.ttfont) != self.table.compile(self.ttfont)

    def get_codepoints(self) -> set[int]:
        """
        Returns all the codepoints in the ``cmap`` table.

        :return: A set of codepoints
        :rtype: set[int]
        """
        codepoints = set()
        for table in self.table.tables:
            if table.isUnicode():
                codepoints.update(table.cmap.keys())
        return codepoints

    def add_missing_nbsp(self) -> None:
        """Fixes the missing non-breaking space glyph by double mapping the space glyph."""
        # Get the space glyph
        best_cmap = self.table.getBestCmap()
        space_glyph = best_cmap.get(0x0020)
        if space_glyph is None:
            return

        # Get the non-breaking space glyph
        nbsp_glyph = best_cmap.get(0x00A0)
        if nbsp_glyph is not None:
            return

        # Copy the space glyph to the non-breaking space glyph
        for table in self.table.tables:
            if table.isUnicode():
                table.cmap[0x00A0] = space_glyph
