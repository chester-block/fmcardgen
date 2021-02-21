from PIL import Image, ImageFont, ImageDraw
from .config import CardGenConfig, PaddingConfig, TextFieldConfig, DEFAULT_FONT
from .frontmatter import get_frontmatter_value, get_frontmatter_formatted
from pydantic.color import Color
from typing import List, Tuple, Mapping, cast, Union
from textwrap import TextWrapper
import dateutil.parser


def draw(fm: dict, cnf: CardGenConfig) -> Image.Image:
    im = Image.open(cnf.template)

    for field in cnf.text_fields:

        if isinstance(field.source, list):
            if isinstance(field.default, Mapping):
                defaults = field.default
            else:
                defaults = {source: field.default or "" for source in field.source}

            value = get_frontmatter_formatted(
                fm,
                format=str(field.format),
                sources=field.source,
                defaults=defaults,
                missing_ok=field.optional,
            )

        else:
            parser = dateutil.parser.parse if field.parse == "datetime" else None
            value = get_frontmatter_value(
                fm,
                source=field.source,
                default=(
                    field.default.get(field.source, None)
                    if isinstance(field.default, Mapping)
                    else field.default
                ),
                missing_ok=field.optional,
                parser=parser,
            )
            if field.format:
                value = field.format.format(value, **{field.source: value})

        draw_text_field(im, str(value), field)

    return im


def draw_text_field(im: Image.Image, text: str, field: TextFieldConfig) -> None:
    if field.font == DEFAULT_FONT:
        font = ImageFont.load_default()
    else:
        font = ImageFont.truetype(str(field.font), size=field.font_size)

    if field.wrap:
        max_width = field.max_width if field.max_width else im.width - field.x
        text = wrap_font_text(font, text, max_width)

    draw = ImageDraw.Draw(im, mode="RGBA")

    if field.bg:
        x0, y0, x1, y1 = draw.textbbox(xy=(field.x, field.y), text=text, font=font)

        # expand the bounding box to account for padding
        assert isinstance(field.padding, PaddingConfig)  # for mypy
        x0 -= field.padding.left
        y0 -= field.padding.top
        x1 += field.padding.right
        y1 += field.padding.bottom

        # When drawing with any transparancy, just drawing directly on to
        # the background image doesn't actually do compositing, you just get
        # a semi-transparant "cutout" of the background. To work around this,
        # draw into a temporary image and then composite it.
        overlay = Image.new(mode="RGBA", size=im.size, color=(0, 0, 0, 0))
        ImageDraw.Draw(overlay).rectangle(
            xy=(x0, y0, x1, y1),
            fill=to_pil_color(field.bg),
        )
        im.alpha_composite(overlay)

    assert isinstance(field.fg, Color)  # for mypy
    draw.text(xy=(field.x, field.y), text=text, font=font, fill=to_pil_color(field.fg))


def wrap_font_text(font: ImageFont.ImageFont, text: str, max_width: int) -> str:
    wrapper = TextWrapper()
    chunks = wrapper._split_chunks(text)

    lines: List[List[str]] = []
    cur_line: List[str] = []
    cur_line_width = 0

    for chunk in chunks:
        width, _ = font.getsize(chunk)

        # If this chunk makes our line too long...
        if cur_line_width + width > max_width:
            # Special case: a single chunk that's too long to fit on one line.
            # In that case just use that chunk as a line by itself, otherwise
            # we'll enter an infinate loop here.
            if cur_line_width == 0:
                lines.append([chunk])
                cur_line = []
                cur_line_width = 0
                continue

            lines.append(cur_line)
            cur_line = [] if chunk.isspace() else [chunk]
            cur_line_width = width

        else:
            cur_line.append(chunk)
            cur_line_width += width

    if cur_line:
        lines.append(cur_line)

    return "\n".join("".join(line).strip() for line in lines)


PILColorTuple = Union[Tuple[int, int, int], Tuple[int, int, int, int]]


def to_pil_color(color: Color) -> PILColorTuple:
    """
    Convert a pydantic Color to a PIL color 4-tuple

    Color.as_rgb_tuple() _almost_ works, but it returns the alpha channel as
    a float between 0 and 1, and PIL expects an int 0-255
    """
    # cast() business is a mypy workaround for
    # https://github.com/python/mypy/issues/1178
    c = color.as_rgb_tuple()
    if len(c) == 3:
        return cast(Tuple[int, int, int], c)
    else:
        r, g, b, a = cast(Tuple[int, int, int, float], c)
        return r, g, b, round(a * 255)
