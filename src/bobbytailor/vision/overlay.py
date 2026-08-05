"""Set-of-Mark overlay renderer + crop gallery builder (21-08, V3-ACC-04).

Request-side machinery for the vision fusion protocol (21-RESEARCH.md §3
handoff patterns 1-2): the deterministic engine's candidates are rendered as
annotated images with boxed ID labels; Claude answers with candidate IDs only
(via ``bobbytailor.vision.schemas`` structured outputs). Vision never sees a
raw sheet and free-associates quantities.

Image budget rules (RESEARCH §3/§5, normative):
- ≤ :data:`MAX_MARKERS_PER_IMAGE` (40) markers per overlay image — beyond
  that the candidate set is partitioned into multiple images, each carrying
  its own ID subset so the caller builds one request per image.
- ≤ :data:`MAX_IMAGES_PER_REQUEST` (20) images per request — more than 20
  images per request drops the per-image resolution cap from 8000px to
  2000px, so galleries pack tiles into contact sheets and hard-cap the batch.

Pixel ↔ PDF-point grounding: every rendered image carries ``info["zoom"]``
(pixels per point) and ``info["marker_boxes_px"]`` so a marker's pixel bbox
maps back to its source PDF-point bbox exactly (``px / zoom``). Candidates
keep their authoritative bboxes in the caller's registry — the model is
never asked for coordinates.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence, Tuple, Union

import fitz
from PIL import Image, ImageDraw, ImageFont

from bobbytailor.pipeline.pdf_analyzer import render_clip_crop

logger = logging.getLogger(__name__)

# RESEARCH §3 handoff 1: keep marker density ≤ ~40 per image, else split.
MAX_MARKERS_PER_IMAGE = 40

# RESEARCH §5: ≤20 images/request keeps the relaxed 8000px per-image limit;
# >20 images triggers the 2000px per-image cap.
MAX_IMAGES_PER_REQUEST = 20

# Anthropic vision hard cap (same constant as pdf_analyzer._MAX_IMAGE_LONG_SIDE_PX).
_API_MAX_LONG_SIDE_PX = 8000

# Default outline palette cycled across candidate kinds when the caller does
# not supply kind_colors. High-contrast on white CAD backgrounds.
_DEFAULT_PALETTE: Tuple[str, ...] = (
    "#e11d48",  # red
    "#2563eb",  # blue
    "#16a34a",  # green
    "#d97706",  # amber
    "#9333ea",  # purple
    "#0891b2",  # cyan
    "#db2777",  # pink
    "#65a30d",  # olive
)

_CHIP_TEXT = "#ffffff"

# The chip is a VISUAL affordance, and a chip wider than the sheet is no
# affordance at all. The anchor forms 24-01 can produce are a contained word, a
# two-token material tag ("WC 01", "PT 04" — the longest measured across the
# four plan sets) or one nearest word, so 24 characters sits far above any
# genuine anchor and only ever bounds an accidental harvest. Nothing is lost by
# it: the per-candidate anchor table threaded into the user hint carries the
# FULL text, and that table — not the chip — is the authoritative delivery.
_CHIP_MAX_ANCHOR_CHARS = 24


def _anchor_text_for(anchors, candidate_id: str) -> str:
    """The anchor text to print on *candidate_id*'s chip, or ``""`` for none.

    Accepts either the 24-01 anchor RECORD (``{"anchor_text": ...}``, the shape
    ``bundle["candidate_anchors"]`` carries) or a bare string, so a caller may
    hand the bundle key straight through without unpacking it.

    ``anchor_text is None`` is 24-01's RECORDED ABSENCE and returns ``""`` —
    the chip then shows the bare ID, never a placeholder. Whitespace is
    collapsed because the chip is measured and drawn as a single line.
    """
    if not anchors:
        return ""
    try:
        record = anchors.get(candidate_id)
    except AttributeError:
        return ""
    if record is None:
        return ""
    text = record.get("anchor_text") if isinstance(record, dict) else record
    if text is None:
        return ""
    collapsed = " ".join(str(text).split())
    if len(collapsed) > _CHIP_MAX_ANCHOR_CHARS:
        collapsed = collapsed[:_CHIP_MAX_ANCHOR_CHARS - 1] + "…"
    return collapsed


def _marker_label(candidate_id: str, anchor_text: str = "") -> str:
    """The chip's text: the ID, plus the drawing's own nearest words when known.

    This is the single highest-leverage string in the vision request (V4-DET-01):
    a marker carrying only an ID asks the model to RECOGNISE a shape, whereas a
    marker carrying the plan's own printed callout asks it to READ a label.

    With no anchor the label is the bare ID — no placeholder, no dangling
    separator — so an unanchored candidate renders exactly as it always has.
    """
    if not anchor_text:
        return candidate_id
    return "{} {}".format(candidate_id, anchor_text)


def _chip_box(
    x0: int,
    y0: int,
    chip_w: int,
    chip_h: int,
    image_size: Optional[Tuple[int, int]] = None,
) -> Tuple[int, int, int, int]:
    """Place the label chip at the marker's top-left, clamped into the image.

    The chip sits just above the box when there is room and inside it when
    there is not (the pre-existing top-edge rule). Anchor-bearing labels are
    wider than a bare ID, so the same treatment is applied to the right edge
    (T-24-32): a chip that would run past the image is slid left until it fits.

    The clamp is a NO-OP for any chip that already fits, so a render whose
    chips all fit is byte-identical to the render before anchors existed.
    """
    chip_y0 = y0 - chip_h
    if chip_y0 < 0:  # no room above — place inside the box
        chip_y0 = y0
    chip_x0 = x0
    if image_size is not None:
        max_x0 = int(image_size[0]) - chip_w
        if chip_x0 > max_x0:
            chip_x0 = max(0, max_x0)
    return (chip_x0, chip_y0, chip_x0 + chip_w, chip_y0 + chip_h)


def _candidate_kind(candidate_id: str) -> str:
    """Kind prefix of a candidate ID: leading non-digit chars, dashes stripped.

    ``"R1" -> "R"``, ``"W12" -> "W"``, ``"SYM-3" -> "SYM"``.
    """
    prefix = []
    for ch in candidate_id:
        if ch.isdigit():
            break
        prefix.append(ch)
    return "".join(prefix).rstrip("-_") or candidate_id


def _kind_color(kind: str, kind_colors: Optional[Dict[str, str]], palette_index: Dict[str, str]) -> str:
    """Resolve the outline color for a candidate kind (caller map wins)."""
    if kind_colors and kind in kind_colors:
        return kind_colors[kind]
    if kind not in palette_index:
        palette_index[kind] = _DEFAULT_PALETTE[len(palette_index) % len(_DEFAULT_PALETTE)]
    return palette_index[kind]


def _page_zoom(page: fitz.Page, target_px: int) -> float:
    """Zoom factor placing the page long edge at *target_px* (API-capped)."""
    longest = max(page.rect.width, page.rect.height)
    if longest <= 0:
        return 1.0
    return min(target_px, _API_MAX_LONG_SIDE_PX) / longest


def _rasterize_page(page: fitz.Page, zoom: float) -> Image.Image:
    """Rasterize *page* at *zoom* into an RGB PIL image."""
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _draw_marker(
    draw: "ImageDraw.ImageDraw",
    candidate_id: str,
    bbox_px: Tuple[int, int, int, int],
    color: str,
    font: "ImageFont.ImageFont",
    anchor_text: str = "",
    image_size: Optional[Tuple[int, int]] = None,
) -> None:
    """Draw one Set-of-Mark marker: outline box + ID (+ anchor text) label chip.

    *anchor_text* is the drawing's own nearest printed words for this candidate
    (24-01). Empty string — the default, and what a recorded absence resolves
    to — draws exactly the bare-ID chip this function has always drawn.
    """
    x0, y0, x1, y1 = bbox_px
    draw.rectangle((x0, y0, x1, y1), outline=color, width=3)

    # Label chip anchored at the box's top-left corner (outside when room).
    label = _marker_label(candidate_id, anchor_text)
    tb = draw.textbbox((0, 0), label, font=font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    pad = 3
    chip = _chip_box(x0, y0, tw + 2 * pad, th + 2 * pad, image_size)
    draw.rectangle(chip, fill=color)
    draw.text((chip[0] + pad, chip[1] + pad - tb[1]), label, fill=_CHIP_TEXT, font=font)


def _render_one_overlay(
    page: fitz.Page,
    candidates: Dict[str, tuple],
    kind_colors: Optional[Dict[str, str]],
    palette_index: Dict[str, str],
    zoom: float,
    anchors: Optional[Dict[str, object]] = None,
) -> Image.Image:
    """Render a single overlay image for *candidates* at *zoom*."""
    img = _rasterize_page(page, zoom)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    marker_boxes_px: Dict[str, Tuple[int, int, int, int]] = {}
    for cid, bbox_pt in candidates.items():
        x0, y0, x1, y1 = (float(v) for v in bbox_pt)
        bbox_px = (
            int(round(x0 * zoom)),
            int(round(y0 * zoom)),
            int(round(x1 * zoom)),
            int(round(y1 * zoom)),
        )
        color = _kind_color(_candidate_kind(cid), kind_colors, palette_index)
        _draw_marker(
            draw, cid, bbox_px, color, font,
            anchor_text=_anchor_text_for(anchors, cid),
            image_size=img.size,
        )
        marker_boxes_px[cid] = bbox_px

    img.info["overlay_ids"] = list(candidates.keys())
    img.info["zoom"] = zoom
    img.info["marker_boxes_px"] = marker_boxes_px
    return img


def render_overlay(
    page: fitz.Page,
    candidates: Dict[str, tuple],
    kind_colors: Optional[Dict[str, str]] = None,
    target_px: int = 1568,
    anchors: Optional[Dict[str, object]] = None,
) -> Union[Image.Image, List[Image.Image]]:
    """Render a Set-of-Mark annotated overlay of *page* (handoff pattern 1).

    Each candidate ``{id: bbox_pt}`` gets a colored outline box and an ID
    label chip drawn on the page raster. Wall classes / regions / symbol
    kinds are color-coded via *kind_colors* (kind = ID prefix, e.g. ``"W"``
    for ``"W1"``); unmapped kinds cycle a default palette.

    When *anchors* is supplied, each chip also carries the drawing's own
    nearest printed words for that candidate (24-01, V4-DET-01), turning a
    symbol-conveyed decision into a text-anchored one — the model READS a
    label instead of RECOGNISING a shape. A candidate with a recorded
    absence, or one missing from the map, keeps the bare-ID chip.

    Marker budget: at most :data:`MAX_MARKERS_PER_IMAGE` (40) markers per
    image. Larger candidate sets are partitioned (insertion order) into
    multiple overlay images, each drawn with ONLY its own candidate subset —
    the caller issues one request per image using ``info["overlay_ids"]``.

    Args:
        page:        Open ``fitz.Page`` to rasterize.
        candidates:  Mapping of candidate ID → PDF-point bbox
                     ``(x0, y0, x1, y1)``.
        kind_colors: Optional mapping of candidate kind → PIL color for the
                     outline/chip (e.g. ``{"W": "red", "R": "blue"}``).
        target_px:   Long-edge render target in pixels (default 1568, the
                     model's standard downscale resolution; capped at the
                     8000px API limit).
        anchors:     Optional mapping of candidate ID → 24-01 anchor record
                     (or bare anchor string). Omitted / ``None`` renders the
                     bare-ID chips this function has always rendered.

    Returns:
        A single ``PIL.Image`` when ``len(candidates) <= 40``; otherwise a
        list of ``PIL.Image``. Every image carries ``info["overlay_ids"]``
        (its candidate subset), ``info["zoom"]`` (px per PDF point) and
        ``info["marker_boxes_px"]`` (drawn pixel bboxes keyed by ID).

    Raises:
        ValueError: If *candidates* is empty.
    """
    if not candidates:
        raise ValueError("render_overlay: candidates must be non-empty")

    zoom = _page_zoom(page, target_px)
    palette_index: Dict[str, str] = {}

    ids = list(candidates.keys())
    if len(ids) <= MAX_MARKERS_PER_IMAGE:
        return _render_one_overlay(
            page, candidates, kind_colors, palette_index, zoom, anchors
        )

    # Partition branch: >40 markers → split into chunks of ≤40, disjoint
    # subsets covering the full candidate set, one overlay image each.
    images: List[Image.Image] = []
    for start in range(0, len(ids), MAX_MARKERS_PER_IMAGE):
        chunk_ids = ids[start:start + MAX_MARKERS_PER_IMAGE]
        chunk = {cid: candidates[cid] for cid in chunk_ids}
        images.append(
            _render_one_overlay(page, chunk, kind_colors, palette_index, zoom, anchors)
        )
    logger.info(
        "render_overlay: %d candidates split into %d images (<=%d markers each)",
        len(ids), len(images), MAX_MARKERS_PER_IMAGE,
    )
    return images


# ── Crop galleries (handoff pattern 2) ───────────────────────────────────────


def _group_field(group, *names, default=None):
    """Read a field from a SymbolGroup-like object or dict."""
    for name in names:
        if isinstance(group, dict):
            if name in group:
                return group[name]
        elif hasattr(group, name):
            return getattr(group, name)
    return default


def _padded_rect(page: fitz.Page, bbox_pt: Sequence[float], pad_pt: float = 2.0) -> fitz.Rect:
    """Pad *bbox_pt* slightly and clamp it to the page rect (crop context)."""
    x0, y0, x1, y1 = (float(v) for v in bbox_pt)
    pad = max(pad_pt, 0.1 * max(x1 - x0, y1 - y0))
    rect = fitz.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad)
    rect.intersect(page.rect)
    return rect


def _caption_tile(crops: List[Image.Image], caption: str, crop_px: int) -> Image.Image:
    """Compose one gallery tile: crops side-by-side + ID caption strip below."""
    font = ImageFont.load_default()
    gap = 4
    caption_h = 18

    scaled = []
    for crop in crops:
        c = crop.copy()
        c.thumbnail((crop_px, crop_px), Image.LANCZOS)
        scaled.append(c)

    width = sum(c.width for c in scaled) + gap * (len(scaled) + 1)
    height = max(c.height for c in scaled) + caption_h + 2 * gap

    tile = Image.new("RGB", (max(width, crop_px), height), "#ffffff")
    x = gap
    for c in scaled:
        tile.paste(c, (x, gap))
        x += c.width + gap
    draw = ImageDraw.Draw(tile)
    draw.text((gap, height - caption_h), caption, fill="#000000", font=font)
    draw.rectangle((0, 0, tile.width - 1, tile.height - 1), outline="#999999")
    return tile


def _pack_contact_sheets(
    tiles: List[Image.Image],
    tiles_per_sheet: int,
    columns: int = 4,
) -> List[Image.Image]:
    """Pack *tiles* into contact sheet images (*tiles_per_sheet* per sheet)."""
    sheets: List[Image.Image] = []
    gap = 8
    for start in range(0, len(tiles), tiles_per_sheet):
        batch = tiles[start:start + tiles_per_sheet]
        cols = min(columns, len(batch))
        rows = (len(batch) + cols - 1) // cols
        cell_w = max(t.width for t in batch) + gap
        cell_h = max(t.height for t in batch) + gap
        sheet = Image.new("RGB", (cols * cell_w + gap, rows * cell_h + gap), "#ffffff")
        for i, tile in enumerate(batch):
            r, c = divmod(i, cols)
            sheet.paste(tile, (gap + c * cell_w, gap + r * cell_h))
        sheets.append(sheet)
    return sheets


def build_crop_gallery(
    page: fitz.Page,
    symbol_groups: list,
    legend_crop_rect=None,
    target_px: int = 1568,
) -> List[Image.Image]:
    """Build contact-sheet crop galleries for symbol groups (handoff pattern 2).

    For each symbol group, renders the representative instance plus up to 2
    additional member instances via :func:`render_clip_crop` (the shared zoom
    primitive), composes them into an ID-captioned tile, and packs tiles into
    contact sheets. When *legend_crop_rect* is given, the sheet's legend crop
    is included as the first image so the model can match symbols to legend
    items in one request.

    The returned batch is hard-capped at :data:`MAX_IMAGES_PER_REQUEST` (20)
    images: tiles-per-sheet is scaled up as needed so the budget always holds.

    Args:
        page:             Open ``fitz.Page`` the groups were clustered on.
        symbol_groups:    List of ``SymbolGroup`` objects or dicts exposing
                          ``candidate_id`` (or ``id``), ``representative_bbox_pt``
                          and optionally ``instance_bboxes_pt``.
        legend_crop_rect: Optional PDF-point rect of the legend region.
        target_px:        Long-edge target for the legend crop render; symbol
                          tiles are rendered at native-detail zoom via
                          ``render_clip_crop``.

    Returns:
        List of ``PIL.Image`` contact sheets (legend crop first when given),
        never more than 20 images. Each contact sheet carries
        ``info["gallery_ids"]`` — the symbol IDs it contains, in tile order.
    """
    if not symbol_groups:
        return []

    tiles: List[Image.Image] = []
    tile_ids: List[str] = []
    crop_px = 220  # per-crop long edge inside a tile — native-detail zoom

    for idx, group in enumerate(symbol_groups):
        cid = _group_field(group, "candidate_id", "id", default="SYM-{}".format(idx + 1))
        rep_bbox = _group_field(group, "representative_bbox_pt", "bbox_pt")
        if rep_bbox is None:
            logger.warning("build_crop_gallery: group %s has no representative bbox — skipped", cid)
            continue

        crops: List[Image.Image] = []
        try:
            crops.append(render_clip_crop(page, _padded_rect(page, rep_bbox), target_px=crop_px))
        except ValueError as exc:
            logger.warning("build_crop_gallery: representative crop failed for %s: %s", cid, exc)
            continue

        members = _group_field(group, "instance_bboxes_pt", default=None) or []
        extra = [b for b in members if tuple(b) != tuple(rep_bbox)][:2]
        for bbox in extra:
            try:
                crops.append(render_clip_crop(page, _padded_rect(page, bbox), target_px=crop_px))
            except ValueError as exc:
                logger.warning("build_crop_gallery: member crop failed for %s: %s", cid, exc)

        tiles.append(_caption_tile(crops, str(cid), crop_px))
        tile_ids.append(str(cid))

    if not tiles:
        return []

    images: List[Image.Image] = []
    legend_slots = 0
    if legend_crop_rect is not None:
        legend_img = render_clip_crop(page, legend_crop_rect, target_px=target_px)
        legend_img.info["gallery_ids"] = []
        legend_img.info["is_legend"] = True
        images.append(legend_img)
        legend_slots = 1

    # Choose tiles-per-sheet so total images never exceed the request budget.
    budget = MAX_IMAGES_PER_REQUEST - legend_slots
    tiles_per_sheet = 12
    needed = (len(tiles) + tiles_per_sheet - 1) // tiles_per_sheet
    if needed > budget:
        tiles_per_sheet = (len(tiles) + budget - 1) // budget
    sheets = _pack_contact_sheets(tiles, tiles_per_sheet)
    for i, sheet in enumerate(sheets):
        sheet.info["gallery_ids"] = tile_ids[i * tiles_per_sheet:(i + 1) * tiles_per_sheet]
    images.extend(sheets)

    if len(images) > MAX_IMAGES_PER_REQUEST:  # defensive — cannot happen after repack
        raise AssertionError(
            "build_crop_gallery: {} images exceeds the {}-image request budget".format(
                len(images), MAX_IMAGES_PER_REQUEST
            )
        )
    logger.info(
        "build_crop_gallery: %d groups -> %d tiles on %d contact sheet(s)%s",
        len(symbol_groups), len(tiles), len(sheets),
        " + legend crop" if legend_slots else "",
    )
    return images
