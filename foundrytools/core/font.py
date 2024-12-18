import contextlib
import math
from collections.abc import Generator
from io import BytesIO
from pathlib import Path
from types import TracebackType
from typing import Any, Optional, Union

from fontTools.misc.cliTools import makeOutputFileName
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.statisticsPen import StatisticsPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.scaleUpem import scale_upem

from foundrytools import constants as const
from foundrytools.core.tables import (
    TABLES_LOOKUP,
    CFFTable,
    CmapTable,
    FvarTable,
    GdefTable,
    GlyfTable,
    GsubTable,
    HeadTable,
    HheaTable,
    HmtxTable,
    KernTable,
    NameTable,
    OS2Table,
    PostTable,
)
from foundrytools.lib.otf_builder import build_otf
from foundrytools.lib.qu2cu import quadratics_to_cubics
from foundrytools.lib.ttf_builder import build_ttf
from foundrytools.utils.path_tools import get_temp_file_path

__all__ = ["Font", "FontConversionError", "FontError"]


class FontError(Exception):
    """The ``FontError`` class is a custom exception class for font-related errors."""


class FontConversionError(Exception):
    """The ``FontConversionError`` class is a custom exception class for font conversion errors."""


class StyleFlags:
    """
    The ``Flags`` class is a helper class for working with font flags (e.g., bold, italic, oblique).

    :Example:

    .. code-block:: python

        from foundrytools import Font, Flags

        font = Font("path/to/font.ttf")
        flags = Flags(font)

        # Check if the font is bold
        if flags.is_bold:
            print("The font is bold.")

        # Set the font as italic
        flags.is_italic = True
    """

    def __init__(self, font: "Font"):
        """
        Initialize the ``Flags`` class.

        :param font: The ``Font`` object.
        :type font: Font
        """
        self._font = font

    def __repr__(self) -> str:
        return (
            f"<Flags is_bold={self.is_bold}, is_italic={self.is_italic}, "
            f"is_oblique={self.is_oblique}, is_regular={self.is_regular}>"
        )

    def __str__(self) -> str:
        return (
            f"Flags(is_bold={self.is_bold}, is_italic={self.is_italic}, "
            f"is_oblique={self.is_oblique}, is_regular={self.is_regular})"
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, StyleFlags):
            return False
        return all(
            getattr(self, attr) == getattr(other, attr)
            for attr in ("is_bold", "is_italic", "is_oblique", "is_regular")
        )

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)

    @property
    def font(self) -> "Font":
        """
        Gets the font used in the instance.

        This property returns the Font object associated with the instance, which can be used to
        modify text displays.

        :return: Font object associated with the instance.
        :rtype: Font
        """
        return self._font

    @font.setter
    def font(self, value: "Font") -> None:
        """
        Sets the font property with a Font object.

        :param value: Font object to set the font property
        :type value: Font
        """
        self._font = value

    @contextlib.contextmanager
    def _update_font_properties(self) -> Generator:
        try:
            yield
        except Exception as e:
            raise FontError("An error occurred while updating font properties") from e

    def _set_font_style(
        self,
        bold: Optional[bool] = None,
        italic: Optional[bool] = None,
        regular: Optional[bool] = None,
    ) -> None:
        if bold is not None:
            self.font.t_os_2.fs_selection.bold = bold
            self.font.t_head.mac_style.bold = bold
        if italic is not None:
            self.font.t_os_2.fs_selection.italic = italic
            self.font.t_head.mac_style.italic = italic
        if regular is not None:
            self.font.t_os_2.fs_selection.regular = regular

    @property
    def is_bold(self) -> bool:
        """
        A property for getting and setting the bold bits of the font.

        The font is considered bold if bit 5 of the ``fsSelection`` field in the ``OS/2`` table is
        set to 1 and bit 0 of the ``macStyle`` field in the ``head`` table is set to 1.

        At the same time, bit 0 of the ``fsSelection`` field in the ``OS/2`` table is set to 0.

        :return: ``True`` if the font is bold, ``False`` otherwise.
        :rtype: bool
        """
        try:
            return self.font.t_os_2.fs_selection.bold and self.font.t_head.mac_style.bold
        except Exception as e:
            raise FontError("An error occurred while checking if the font is bold") from e

    @is_bold.setter
    def is_bold(self, value: bool) -> None:
        with self._update_font_properties():
            self._set_font_style(bold=value, regular=not value if not self.is_italic else False)

    @property
    def is_italic(self) -> bool:
        """
        A property for getting and setting the italic bits of the font.

        The font is considered italic when bit 0 of the ``fsSelection`` field in the ``OS/2`` table
        is set to 1 and bit 0 of the ``macStyle`` field in the ``head`` table is set to 1.

        At the same time, bit 0 of the ``fsSelection`` field in the ``OS/2`` table is set to 0.

        :return: ``True`` if the font is italic, ``False`` otherwise.
        :rtype: bool
        """
        try:
            return self.font.t_os_2.fs_selection.italic and self.font.t_head.mac_style.italic
        except Exception as e:
            raise FontError("An error occurred while checking if the font is italic") from e

    @is_italic.setter
    def is_italic(self, value: bool) -> None:
        with self._update_font_properties():
            self._set_font_style(italic=value, regular=not value if not self.is_bold else False)

    @property
    def is_oblique(self) -> bool:
        """
        A property for getting and setting the oblique bit of the font.

        :return: ``True`` if the font is oblique, ``False`` otherwise.
        :rtype: bool
        """
        try:
            return self.font.t_os_2.fs_selection.oblique
        except Exception as e:
            raise FontError("An error occurred while checking if the font is oblique") from e

    @is_oblique.setter
    def is_oblique(self, value: bool) -> None:
        """Set the oblique bit in the OS/2 table."""
        try:
            self.font.t_os_2.fs_selection.oblique = value
        except Exception as e:
            raise FontError("An error occurred while setting the oblique bit") from e

    @property
    def is_regular(self) -> bool:
        """
        A property for getting and setting the regular bit of the font.

        :return: ``True`` if the font is regular, ``False`` otherwise.
        :rtype: bool
        """
        try:
            return self.font.t_os_2.fs_selection.regular
        except Exception as e:
            raise FontError("An error occurred while checking if the font is regular") from e

    @is_regular.setter
    def is_regular(self, value: bool) -> None:
        """Set the regular bit in the OS/2 table."""
        with self._update_font_properties():
            if value:
                self._set_font_style(regular=True, bold=False, italic=False)
            else:
                # Prevent setting the regular bit if the font is bold or italic
                self.font.t_os_2.fs_selection.regular = not (self.is_bold or self.is_italic)


class Font:  # pylint: disable=too-many-public-methods, too-many-instance-attributes
    """
    The ``Font`` class is a high-level wrapper around the ``TTFont`` class from ``fontTools``,
    providing an interface for manipulating fonts and their tables.

    The wrapped ``TTFont`` object is accessible via the ``ttfont`` attribute.

    Tables
    ------

    The ``Font`` class provides wrappers (properties prefixed with ``t_``, such as ``t_cff_``,
    ``t_cmap``, ``t_os_2``, etc.) for easy access to the most common font tables. Each table wrapper
    provides a set of methods for accessing and modifying the table data.

    :Example:

    .. code-block:: python

        from foundrytools import Font

        font = Font("path/to/font.otf")
        font.t_cff_.round_coordinates()
        font.t_os_2.recalc_unicode_ranges()

    Please see the Tables section for more information on the available table wrappers.

    Flags
    -----

    The ``Font`` class provides a ``flags`` attribute for working with font flags (e.g., regular,
    bold, italic, oblique). The ``flags`` attribute is an instance of the ``StyleFlags`` class.

    :Example:

    .. code-block:: python

        from foundrytools import Font

        font = Font("path/to/font.otf")

        # Check if the font is bold
        if font.flags.is_bold:
            print("The font is bold.")

        # Set the font as italic
        font.flags.is_italic = True

    Properties
    ----------

    The ``Font`` class provides the following properties, prefixed with ``is_``, for checking the
    font format:

    - ``is_ps``: Check if the font has PostScript outlines.
    - ``is_tt``: Check if the font has TrueType outlines.
    - ``is_woff``: Check if the font is a WOFF font.
    - ``is_woff2``: Check if the font is a WOFF2 font.
    - ``is_sfnt``: Check if the font is an SFNT font.
    - ``is_static``: Check if the font is a static font.
    - ``is_variable``: Check if the font is a variable font.

    :Example:

    .. code-block:: python

        from foundrytools import Font

        font = Font("path/to/font.otf")

        if font.is_ps:
            print("The font has PostScript outlines.")

        if font.is_tt:
            print("The font has TrueType outlines.")

        if font.is_woff:
            print("The font is a WOFF font.")


    Font conversion methods
    -----------------------

    The ``Font`` class provides methods for converting fonts to different formats:

    - ``to_otf``: Converts a TrueType font to PostScript.
    - ``to_ttf``: Convert a PostScript font to TrueType.
    - ``to_woff``: Converts a SFNT font to WOFF.
    - ``to_woff2``: Convert a SFNT font to WOFF2.
    - ``to_sfnt``: Converts a WOFF or WOFF2 font to SFNT.


    Methods
    -------

    The ``Font`` class provides few methods for saving the font to a file, closing the font, and
    converting the font to a different format.

    To keep the core package lightweight, most complex operations are performed using the
    table wrappers or the available utilities in the ``foundrytools.app`` package.

    Anyway, the ``Font`` class provides the following methods to save, close, and convert the font:

    - ``save``: Save the font to a file.
    - ``close``: Close the font.
    - ``convert``: Convert the font to a different format.

    """

    def __init__(
        self,
        font_source: Union[str, Path, BytesIO, TTFont],
        lazy: Optional[bool] = None,
        recalc_bboxes: bool = True,
        recalc_timestamp: bool = False,
    ) -> None:
        """
        Initialize a ``Font`` object.

        :param font_source: A path to a font file (``str`` or ``Path`` object), a ``BytesIO`` object
            or a ``TTFont`` object.
        :type font_source: Union[str, Path, BytesIO, TTFont]
        :param lazy: If ``True``, many data structures are loaded lazily, upon access only. If
            ``False``, many data structures are loaded immediately. The default is ``None``
            which is somewhere in between.
        :type lazy: Optional[bool]
        :param recalc_bboxes: If ``True`` (the default), recalculates ``glyf``, ``CFF``, ``head``
            bounding box values and ``hhea``/``vhea`` min/max values on save. Also compiles the
            glyphs on importing, which saves memory consumption and time.
        :type recalc_bboxes: bool
        :param recalc_timestamp: If ``True``, set the ``modified`` timestamp in the ``head`` table
            on save. Defaults to ``False``.
        :type recalc_timestamp: bool
        """

        self._file: Optional[Path] = None
        self._bytesio: Optional[BytesIO] = None
        self._ttfont: Optional[TTFont] = None
        self._temp_file: Path = get_temp_file_path()
        self._init_font(font_source, lazy, recalc_bboxes, recalc_timestamp)
        self._init_tables()  # Ensure tables are initialized before flags
        self.flags = StyleFlags(self)

    def _init_font(
        self,
        font_source: Union[str, Path, BytesIO, TTFont],
        lazy: Optional[bool],
        recalc_bboxes: bool,
        recalc_timestamp: bool,
    ) -> None:
        if isinstance(font_source, (str, Path)):
            self._init_from_file(font_source, lazy, recalc_bboxes, recalc_timestamp)
        elif isinstance(font_source, BytesIO):
            self._init_from_bytesio(font_source, lazy, recalc_bboxes, recalc_timestamp)
        elif isinstance(font_source, TTFont):
            self._init_from_ttfont(font_source, lazy, recalc_bboxes, recalc_timestamp)
        else:
            raise FontError(
                f"Invalid source type {type(font_source)}. Expected str, Path, BytesIO, or TTFont."
            )

    def _init_from_file(
        self,
        path: Union[str, Path],
        lazy: Optional[bool],
        recalc_bboxes: bool,
        recalc_timestamp: bool,
    ) -> None:
        self._file = Path(path).resolve()
        self._ttfont = TTFont(
            path, lazy=lazy, recalcBBoxes=recalc_bboxes, recalcTimestamp=recalc_timestamp
        )

    def _init_from_bytesio(
        self, bytesio: BytesIO, lazy: Optional[bool], recalc_bboxes: bool, recalc_timestamp: bool
    ) -> None:
        self._bytesio = bytesio
        self._ttfont = TTFont(
            bytesio, lazy=lazy, recalcBBoxes=recalc_bboxes, recalcTimestamp=recalc_timestamp
        )
        bytesio.close()

    def _init_from_ttfont(
        self, ttfont: TTFont, lazy: Optional[bool], recalc_bboxes: bool, recalc_timestamp: bool
    ) -> None:
        self._bytesio = BytesIO()
        ttfont.save(self._bytesio, reorderTables=False)
        self._bytesio.seek(0)
        self._ttfont = TTFont(
            self._bytesio, lazy=lazy, recalcBBoxes=recalc_bboxes, recalcTimestamp=recalc_timestamp
        )

    def _init_tables(self) -> None:
        """
        Initialize all font table attributes to None. This method sets up the initial state
        for each table in the font, ensuring that they are ready to be loaded when accessed.
        """
        self._cff: Optional[CFFTable] = None
        self._cmap: Optional[CmapTable] = None
        self._fvar: Optional[FvarTable] = None
        self._gdef: Optional[GdefTable] = None
        self._glyf: Optional[GlyfTable] = None
        self._gsub: Optional[GsubTable] = None
        self._head: Optional[HeadTable] = None
        self._hhea: Optional[HheaTable] = None
        self._hmtx: Optional[HmtxTable] = None
        self._kern: Optional[KernTable] = None
        self._name: Optional[NameTable] = None
        self._os_2: Optional[OS2Table] = None
        self._post: Optional[PostTable] = None

    def _get_table(self, table_tag: str):  # type: ignore
        table_attr, table_cls = TABLES_LOOKUP[table_tag]
        if getattr(self, table_attr) is None:
            if self.ttfont.get(table_tag) is None:
                raise KeyError(f"The '{table_tag}' table is not present in the font")
            setattr(self, table_attr, table_cls(self.ttfont))
        table = getattr(self, table_attr)
        if table is None:
            raise KeyError(f"An error occurred while loading the '{table_tag}' table")
        return table

    def __enter__(self) -> "Font":
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"<Font: ttfont={self.ttfont}, file={self.file}, bytesio={self.bytesio}>"

    @property
    def file(self) -> Optional[Path]:
        """
        A property with both getter and setter methods for the file path of the font. If the font
        was loaded from a file, this property will return the file path. If the font was loaded from
        a ``BytesIO`` object or a ``TTFont`` object, this property will return ``None``.

        :return: The file path of the font, if any.
        :rtype: Optional[Path]
        """
        return self._file

    @file.setter
    def file(self, value: Union[str, Path]) -> None:
        """
        Set the file path of the font.

        :param value: The file path of the font.
        :type value: Path
        """
        if isinstance(value, str):
            value = Path(value)
        self._file = value

    @property
    def bytesio(self) -> Optional[BytesIO]:
        """
        A property with both getter and setter methods for the ``BytesIO`` object of the font. If
        the font was loaded from a ``BytesIO`` object, this property will return the ``BytesIO``
        object. If the font was loaded from a file or a ``TTFont`` object, this property will return
        ``None``.

        :return: The ``BytesIO`` object of the font, if any.
        :rtype: Optional[BytesIO]
        """
        return self._bytesio

    @bytesio.setter
    def bytesio(self, value: BytesIO) -> None:
        """
        Set the ``BytesIO`` object of the font.

        :param value: The ``BytesIO`` object of the font.
        :type value: BytesIO
        """
        self._bytesio = value

    @property
    def ttfont(self) -> TTFont:
        """
        A property with both getter and setter methods for the underlying ``TTFont`` object of the
        font.

        :return: The ``TTFont`` object of the font.
        :rtype: TTFont
        """
        return self._ttfont

    @ttfont.setter
    def ttfont(self, value: TTFont) -> None:
        """
        Set the underlying ``TTFont`` object of the font.

        Args:
            value: The ``TTFont`` object of the font.
        """
        self._ttfont = value

    @property
    def temp_file(self) -> Path:
        """
        A placeholder for the temporary file path of the font, in case is needed for some
        operations.

        :return: The temporary file path of the font.
        :rtype: Path
        """
        return self._temp_file

    @property
    def t_cff_(self) -> CFFTable:
        """
        The ``CFF`` table wrapper.

        :return: The loaded ``CFFTable``.
        :rtype: CFFTable
        """
        return self._get_table(const.T_CFF)

    @property
    def t_cmap(self) -> CmapTable:
        """
        The ``cmap`` table wrapper.

        :return: The loaded ``CmapTable``.
        :rtype: CmapTable
        """
        return self._get_table(const.T_CMAP)

    @property
    def t_fvar(self) -> FvarTable:
        """
        The ``fvar`` table wrapper.

        :return: The loaded ``FvarTable``.
        :rtype: FvarTable
        """
        return self._get_table(const.T_FVAR)

    @property
    def t_gdef(self) -> GdefTable:
        """
        The ``GDEF`` table wrapper.

        :return: The loaded ``GdefTable``.
        :rtype: GdefTable
        """
        return self._get_table(const.T_GDEF)

    @property
    def t_glyf(self) -> GlyfTable:
        """
        The ``glyf`` table wrapper.

        :return: The loaded ``GlyfTable``.
        :rtype: GlyfTable
        """
        return self._get_table(const.T_GLYF)

    @property
    def t_gsub(self) -> GsubTable:
        """
        The ``GSUB`` table wrapper.

        :return: The loaded ``GsubTable``.
        :rtype: GsubTable
        """
        return self._get_table(const.T_GSUB)

    @property
    def t_head(self) -> HeadTable:
        """
        The ``head`` table wrapper.

        :return: The loaded ``HeadTable``.
        :rtype: HeadTable
        """
        return self._get_table(const.T_HEAD)

    @property
    def t_hhea(self) -> HheaTable:
        """
        The ``hhea`` table wrapper.

        :return: The loaded ``HheaTable``.
        :rtype: HheaTable
        """
        return self._get_table(const.T_HHEA)

    @property
    def t_hmtx(self) -> HmtxTable:
        """
        The ``hmtx`` table wrapper.

        :return: The loaded ``HmtxTable``.
        :rtype: HmtxTable
        """
        return self._get_table(const.T_HMTX)

    @property
    def t_kern(self) -> KernTable:
        """
        The ``kern`` table wrapper.

        :return: The loaded ``KernTable``.
        :rtype: KernTable
        """
        return self._get_table(const.T_KERN)

    @property
    def t_name(self) -> NameTable:
        """
        The ``name`` table wrapper.

        :return: The loaded ``NameTable``.
        :rtype: NameTable
        """
        return self._get_table(const.T_NAME)

    @property
    def t_os_2(self) -> OS2Table:
        """
        The ``OS/2`` table wrapper.

        :return: The loaded ``OS2Table``.
        :rtype: OS2Table
        """
        return self._get_table(const.T_OS_2)

    @property
    def t_post(self) -> PostTable:
        """
        The ``post`` table wrapper.

        :return: The loaded ``PostTable``.
        :rtype: PostTable
        """
        return self._get_table(const.T_POST)

    @property
    def is_ps(self) -> bool:
        """
        A read-only property for checking if the font has PostScript outlines. The font has
        PostScript outlines if the ``sfntVersion`` attribute of the ``TTFont`` object is ``OTTO``.

        :return: ``True`` if the font sfntVersion is ``OTTO``, ``False`` otherwise.
        :rtype: bool
        """
        return self.ttfont.sfntVersion == const.PS_SFNT_VERSION

    @property
    def is_tt(self) -> bool:
        """
        A read-only property for checking if the font has TrueType outlines. The font has TrueType
        outlines if the ``sfntVersion`` attribute of the ``TTFont`` object is ``\0\1\0\0``.

        :return: ``True`` if the font sfntVersion is ``\0\1\0\0``, ``False`` otherwise.
        :rtype: bool
        """
        return self.ttfont.sfntVersion == const.TT_SFNT_VERSION

    @property
    def is_woff(self) -> bool:
        """
        A read-only property for checking if the font is a WOFF font. The font is a WOFF font if the
        ``flavor`` attribute of the ``TTFont`` object is ``woff``.

        :return: ``True`` if the font flavor is ``woff``, ``False`` otherwise.
        :rtype: bool
        """
        return self.ttfont.flavor == const.WOFF_FLAVOR

    @property
    def is_woff2(self) -> bool:
        """
        A read-only property for checking if the font is a WOFF2 font. The font is a WOFF2 font if
        the ``flavor`` attribute of the ``TTFont`` object is ``woff2``.

        :return: ``True`` if the font flavor is ``woff2``, ``False`` otherwise.
        :rtype: bool
        """
        return self.ttfont.flavor == const.WOFF2_FLAVOR

    @property
    def is_sfnt(self) -> bool:
        """
        A read-only property for checking if the font is an SFNT font. The font is an SFNT font if
        the ``flavor`` attribute of the ``TTFont`` object is ``None``.

        :return: ``True`` if the font flavor is ``None``, ``False`` otherwise.
        :rtype: bool
        """
        return self.ttfont.flavor is None

    @property
    def is_static(self) -> bool:
        """
        A read-only property for checking if the font is a static font. The font is a static font if
        the ``TTFont`` object does not have a ``fvar`` table.

        :return: ``True`` if the font does not have a ``fvar`` table, ``False`` otherwise.
        :rtype: bool
        """
        return self.ttfont.get(const.T_FVAR) is None

    @property
    def is_variable(self) -> bool:
        """
        A read-only property for checking if the font is a variable font. The font is a variable
        font if the ``TTFont`` object has a ``fvar`` table.

        :return: ``True`` if the font has a ``fvar`` table, ``False`` otherwise.
        :rtype: bool
        """
        return self.ttfont.get(const.T_FVAR) is not None

    def save(
        self,
        file: Union[str, Path, BytesIO],
        reorder_tables: Optional[bool] = True,
    ) -> None:
        """
        Save the font to a file.

        :param file: The file path or ``BytesIO`` object to save the font to.
        :type file: Union[str, Path, BytesIO]
        :param reorder_tables: If ``True`` (the default), reorder the tables, sorting them by tag
            (recommended by the OpenType specification). If ``False``, retain the original order.
            If ``None``, reorder by table dependency (fastest).
        :type reorder_tables: Optional[bool]
        """
        self.ttfont.save(file, reorderTables=reorder_tables)

    def close(self) -> None:
        """Close the font and delete the temporary file."""
        self.ttfont.close()
        self._temp_file.unlink(missing_ok=True)
        if self.bytesio:
            self.bytesio.close()

    def reload(self) -> None:
        """Reload the font by saving it to a temporary stream and then loading it back."""
        recalc_bboxes = self.ttfont.recalcBBoxes
        recalc_timestamp = self.ttfont.recalcTimestamp
        buf = BytesIO()
        self.ttfont.save(buf)
        buf.seek(0)
        self.ttfont = TTFont(buf, recalcBBoxes=recalc_bboxes, recalcTimestamp=recalc_timestamp)
        self._init_tables()
        self.flags = StyleFlags(self)
        buf.close()

    def get_file_ext(self) -> str:
        """
        Get the real extension of the font (e.g., ``.otf``, ``.ttf``, ``.woff``, ``.woff2``).

        :return: The real extension of the font.
        :rtype: str
        """

        # Order of if statements is important.
        # WOFF and WOFF2 must be checked before OTF and TTF.
        if self.is_woff:
            return const.WOFF_EXTENSION
        if self.is_woff2:
            return const.WOFF2_EXTENSION
        if self.is_ps:
            return const.OTF_EXTENSION
        if self.is_tt:
            return const.TTF_EXTENSION
        raise ValueError("Unknown font type.")

    def get_file_path(
        self,
        file: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        overwrite: bool = True,
        extension: Optional[str] = None,
        suffix: str = "",
    ) -> Path:
        """
        Get the output file for a ``Font`` object. If ``output_dir`` is not specified, the output
        file will be saved in the same directory as the input file. It the output file exists and
        ``overwrite`` is ``False``, file name will be incremented by adding a number preceded by '#'
        before the extension until a non-existing file name is found. If ``suffix`` is specified, it
        will be appended to the file name. If the suffix is already present, it will be removed
        before adding it again.

        :param file: The file name to use for the output file.
        :type file: Optional[Path]
        :param output_dir: The output directory.
        :type output_dir: Optional[Path]
        :param overwrite: If ``True``, overwrite the output file if it exists. If ``False``,
            increment the file name until a non-existing file name is found.
        :type overwrite: bool
        :param extension: The extension of the output file. If not specified, the extension of the
            input file will be used.
        :type extension: Optional[str]
        :param suffix: The suffix to add to the file name.
        :type suffix: str
        :return: The output file.
        :rtype: Path
        """

        if file is None and self.file is None:
            raise ValueError(
                "Cannot get output file for a BytesIO object without providing a file name."
            )

        file = file or self.file
        if not isinstance(file, Path):
            raise ValueError("File must be a Path object.")

        out_dir = output_dir or file.parent
        extension = extension or self.get_file_ext()
        file_name = file.stem + extension

        # Clean up the file name by removing the extensions used as file name suffix as added by
        # possible previous conversions. This is necessary to avoid adding the suffix multiple
        # times, like in the case of a file name like 'font.woff2.ttf.woff2'. It may happen when
        # converting a WOFF2 font to TTF and then to WOFF2 again.
        if suffix != "":
            for ext in [
                const.OTF_EXTENSION,
                const.TTF_EXTENSION,
                const.WOFF2_EXTENSION,
                const.WOFF_EXTENSION,
            ]:
                file_name = file_name.replace(ext, "")

        out_file = Path(
            makeOutputFileName(
                input=file_name,
                outputDir=out_dir,
                extension=extension,
                overWrite=overwrite,
                suffix=suffix,
            )
        )
        return out_file

    def to_woff(self) -> None:
        """
        Convert a font to WOFF.

        :raises FontConversionError: If the font is already a WOFF font.
        """
        if self.is_woff:
            raise FontConversionError("Font is already a WOFF font.")

        self.ttfont.flavor = const.WOFF_FLAVOR

    def to_woff2(self) -> None:
        """
        Convert a font to WOFF2.

        :raises FontConversionError: If the font is already a WOFF2 font.
        """
        if self.is_woff2:
            raise FontConversionError("Font is already a WOFF2 font.")

        self.ttfont.flavor = const.WOFF2_FLAVOR

    def to_ttf(self, max_err: float = 1.0, reverse_direction: bool = True) -> None:
        """
        Converts a PostScript font to TrueType.

        :param max_err: The maximum error allowed when converting the font to TrueType. Defaults to
            1.0.
        :type max_err: float
        :param reverse_direction: If ``True``, reverse the direction of the contours. Defaults to
            ``True``.
        :type reverse_direction: bool
        :raises FontConversionError: If the font is already a TrueType font or if the font is a
            variable font.
        """
        if self.is_tt:
            raise FontConversionError("Font is already a TrueType font.")
        if self.is_variable:
            raise FontConversionError("Conversion to TrueType is not supported for variable fonts.")

        build_ttf(font=self.ttfont, max_err=max_err, reverse_direction=reverse_direction)

    def to_otf(self, tolerance: float = 1.0, correct_contours: bool = True) -> None:
        """
        Converts a TrueType font to PostScript.

        :param tolerance: The tolerance value used to convert quadratic curves to cubic curves.
            Defaults to 1.0.
        :type tolerance: float
        :param correct_contours: If ``True``, correct the contours of the font by removing overlaps
            and tiny paths and correcting the direction of contours. Defaults to ``True``.
        :type correct_contours: bool
        :raises FontConversionError: If the font is already a PostScript font or if the font is a
            variable font.
        """
        if self.is_ps:
            raise FontConversionError("Font is already a PostScript font.")
        if self.is_variable:
            raise FontConversionError(
                "Conversion to PostScript is not supported for variable fonts."
            )
        self.t_glyf.decompose_all()

        charstrings = quadratics_to_cubics(
            font=self.ttfont, tolerance=tolerance, correct_contours=correct_contours
        )
        build_otf(font=self.ttfont, charstrings_dict=charstrings)

        self.t_os_2.recalc_avg_char_width()

    def to_sfnt(self) -> None:
        """
        Convert a font to SFNT.

        :raises FontConversionError: If the font is already a SFNT font.
        """
        if self.is_sfnt:
            raise FontConversionError("Font is already a SFNT font.")
        self.ttfont.flavor = None

    def scale_upm(self, target_upm: int) -> None:
        """
        Scale the font to the specified Units Per Em (UPM) value.

        :param target_upm: The target UPM value. Must be in the range 16 to 16384.
        :type target_upm: int
        """

        if target_upm < const.MIN_UPM or target_upm > const.MAX_UPM:
            raise ValueError(
                f"units_per_em must be in the range {const.MAX_UPM} to {const.MAX_UPM}."
            )

        if self.t_head.units_per_em == target_upm:
            return

        scale_upem(self.ttfont, new_upem=target_upm)

    def correct_contours(
        self,
        remove_hinting: bool = True,
        ignore_errors: bool = True,
        remove_unused_subroutines: bool = True,
        min_area: int = 25,
    ) -> set[str]:
        """
        Correct the contours of a font by removing overlaps and tiny paths and correcting the
        direction of contours.

        This tool is an implementation of the ``removeOverlaps`` function in the ``fontTools``
        library to add support for correcting contours winding and removing tiny paths.

        If one or more contours are modified, the glyf or CFF table will be rebuilt.
        If no contours are modified, the font will remain unchanged and the method will return an
        empty list.

        The minimum area default value, 25, is the same as ``afdko.checkoutlinesufo``. All subpaths
        with a bounding box less than this area will be deleted. To prevent the deletion of small
        subpaths, set this value to 0.

        :param remove_hinting: If ``True``, remove hinting instructions from the font if one or more
            contours are modified. Defaults to ``True``.
        :type remove_hinting: bool
        :param ignore_errors: If ``True``, ignore skia pathops errors during the correction process.
            Defaults to ``True``.
        :type ignore_errors: bool
        :param remove_unused_subroutines: If ``True``, remove unused subroutines from the font.
            Defaults to ``True``.
        :type remove_unused_subroutines: bool
        :param min_area: The minimum area expressed in square units. Subpaths with a bounding box
            less than this area will be deleted. Defaults to 25.
        :type min_area: int
        :return: A set of glyph names that have been modified.
        :rtype: set[str]
        """
        if self.is_variable:
            raise NotImplementedError("Contour correction is not supported for variable fonts.")

        if self.is_ps:
            return self.t_cff_.correct_contours(
                remove_hinting=remove_hinting,
                ignore_errors=ignore_errors,
                remove_unused_subroutines=remove_unused_subroutines,
                min_area=min_area,
            )
        if self.is_tt:
            return self.t_glyf.correct_contours(
                remove_hinting=remove_hinting,
                ignore_errors=ignore_errors,
                min_area=min_area,
            )

        raise FontError("Unknown font type.")

    def calc_italic_angle(self, min_slant: float = 2.0) -> float:
        """
        Calculates the italic angle of a font by measuring the slant of the glyph 'H' or 'uni0048'.

        :param min_slant: The minimum slant value to consider the font italic. Defaults to 2.0.
        :type min_slant: float
        :return: The italic angle of the font.
        :rtype: float
        :raises FontError: If the font does not contain the glyph 'H' or 'uni0048' or if an error
            occurs while calculating the italic angle.
        """

        glyph_set = self.ttfont.getGlyphSet()
        pen = StatisticsPen(glyphset=glyph_set)
        for g in ("H", "uni0048"):
            with contextlib.suppress(KeyError):
                glyph_set[g].draw(pen)
                italic_angle = -1 * math.degrees(math.atan(pen.slant))
                if abs(italic_angle) >= abs(min_slant):
                    return italic_angle
                return 0.0
        raise FontError("The font does not contain the glyph 'H' or 'uni0048'.")

    def get_glyph_bounds(self, glyph_name: str) -> dict[str, float]:
        """
        Get the bounding box of a glyph.

        :param glyph_name: The glyph name.
        :type glyph_name: str
        :return: The bounding box of the glyph.
        :rtype: dict[str, float]
        """
        glyph_set = self.ttfont.getGlyphSet()

        if glyph_name not in glyph_set:
            raise ValueError(f"Glyph '{glyph_name}' does not exist in the font.")

        bounds_pen = BoundsPen(glyphSet=glyph_set)

        glyph_set[glyph_name].draw(bounds_pen)
        bounds = {
            "xMin": bounds_pen.bounds[0],
            "yMin": bounds_pen.bounds[1],
            "xMax": bounds_pen.bounds[2],
            "yMax": bounds_pen.bounds[3],
        }

        return bounds
