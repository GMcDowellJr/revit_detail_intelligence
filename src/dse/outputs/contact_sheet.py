import os
import struct
import zlib

from dse.io_paths import ensure_dir, resolve_contact_sheets_dir, run_stamp


_FONT = {
    " ": ["000", "000", "000", "000", "000"],
    "A": ["010", "101", "111", "101", "101"],
    "B": ["110", "101", "110", "101", "110"],
    "C": ["011", "100", "100", "100", "011"],
    "D": ["110", "101", "101", "101", "110"],
    "E": ["111", "100", "110", "100", "111"],
    "F": ["111", "100", "110", "100", "100"],
    "G": ["011", "100", "101", "101", "011"],
    "H": ["101", "101", "111", "101", "101"],
    "I": ["111", "010", "010", "010", "111"],
    "J": ["001", "001", "001", "101", "010"],
    "K": ["101", "101", "110", "101", "101"],
    "L": ["100", "100", "100", "100", "111"],
    "M": ["101", "111", "111", "101", "101"],
    "N": ["101", "111", "111", "111", "101"],
    "O": ["010", "101", "101", "101", "010"],
    "P": ["110", "101", "110", "100", "100"],
    "Q": ["010", "101", "101", "011", "001"],
    "R": ["110", "101", "110", "101", "101"],
    "S": ["011", "100", "010", "001", "110"],
    "T": ["111", "010", "010", "010", "010"],
    "U": ["101", "101", "101", "101", "111"],
    "V": ["101", "101", "101", "101", "010"],
    "W": ["101", "101", "111", "111", "101"],
    "X": ["101", "101", "010", "101", "101"],
    "Y": ["101", "101", "010", "010", "010"],
    "Z": ["111", "001", "010", "100", "111"],
    "0": ["111", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "111"],
    "2": ["110", "001", "111", "100", "111"],
    "3": ["110", "001", "111", "001", "110"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"],
    "7": ["111", "001", "010", "100", "100"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "111"],
    ":": ["000", "010", "000", "010", "000"],
    ".": ["000", "000", "000", "010", "000"],
    "-": ["000", "000", "111", "000", "000"],
    "_": ["000", "000", "000", "000", "111"],
    "#": ["101", "111", "101", "111", "101"],
    "(": ["011", "100", "100", "100", "011"],
    ")": ["110", "001", "001", "001", "110"],
    "/": ["001", "001", "010", "100", "100"],
}


def _png_chunk(tag, data):
    return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def _save_png(path, width, height, rgb_bytes):
    raw = b""
    stride = width * 3
    for row in range(height):
        raw += b"\x00" + rgb_bytes[row * stride : (row + 1) * stride]
    png = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack("!2I5B", width, height, 8, 2, 0, 0, 0)
    png += _png_chunk(b"IHDR", ihdr)
    png += _png_chunk(b"IDAT", zlib.compress(raw, 9))
    png += _png_chunk(b"IEND", b"")
    with open(path, "wb") as handle:
        handle.write(png)


def _new_canvas(width, height, color=(255, 255, 255)):
    return [list(color) for _ in range(width * height)]


def _set_px(canvas, width, height, x, y, color):
    if x < 0 or y < 0 or x >= width or y >= height:
        return
    canvas[y * width + x] = [color[0], color[1], color[2]]


def _fill_rect(canvas, width, height, x, y, w, h, color):
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            _set_px(canvas, width, height, xx, yy, color)


def _draw_text(canvas, width, height, x, y, text, color=(0, 0, 0), scale=2):
    cursor = x
    for raw_ch in text.upper():
        ch = raw_ch if raw_ch in _FONT else " "
        glyph = _FONT[ch]
        for gy, row in enumerate(glyph):
            for gx, bit in enumerate(row):
                if bit != "1":
                    continue
                for sy in range(scale):
                    for sx in range(scale):
                        _set_px(canvas, width, height, cursor + gx * scale + sx, y + gy * scale + sy, color)
        cursor += (3 * scale) + scale


def _tile_lines(tile, rank=None):
    lines = []
    label = tile.get("display_name", "VIEW")
    if rank is not None:
        lines.append("#{} {}".format(rank, label))
    else:
        lines.append("SEED {}".format(label))
    lines.append("ID:{}".format(tile.get("view_id", "?")))
    if "score_total" in tile:
        lines.append("S:{:.3f}".format(float(tile.get("score_total", 0.0))))
    if tile.get("source_doc_name"):
        lines.append(str(tile.get("source_doc_name")))
    return lines


def write_contact_sheet_png(seed_tile, candidate_tiles, config, run_id=None):
    out_dir = ensure_dir(resolve_contact_sheets_dir(config))
    rid = run_id or run_stamp("contact")

    tile_w = 260
    tile_h = 140
    cols = 3
    rows = 1 + ((len(candidate_tiles) + (cols - 1)) // cols)
    width = cols * tile_w + (cols + 1) * 8
    height = rows * tile_h + (rows + 1) * 8

    canvas = _new_canvas(width, height, color=(246, 246, 246))

    tiles = [seed_tile] + list(candidate_tiles)
    for idx, tile in enumerate(tiles):
        row = idx // cols
        col = idx % cols
        x = 8 + col * (tile_w + 8)
        y = 8 + row * (tile_h + 8)

        bg = (220, 235, 255) if idx == 0 else (255, 255, 255)
        _fill_rect(canvas, width, height, x, y, tile_w, tile_h, bg)
        _fill_rect(canvas, width, height, x, y, tile_w, 2, (70, 70, 70))
        _fill_rect(canvas, width, height, x, y + tile_h - 2, tile_w, 2, (70, 70, 70))
        _fill_rect(canvas, width, height, x, y, 2, tile_h, (70, 70, 70))
        _fill_rect(canvas, width, height, x + tile_w - 2, y, 2, tile_h, (70, 70, 70))

        preview_w = tile_w - 16
        preview_h = 58
        pcol = (165, 205, 175) if idx == 0 else (215, 215, 215)
        _fill_rect(canvas, width, height, x + 8, y + 8, preview_w, preview_h, pcol)
        _draw_text(canvas, width, height, x + 14, y + 26, "PREVIEW", (20, 20, 20), scale=2)

        lines = _tile_lines(tile, rank=idx if idx > 0 else None)
        line_y = y + 74
        for line in lines[:4]:
            _draw_text(canvas, width, height, x + 8, line_y, line[:36], (10, 10, 10), scale=2)
            line_y += 14

    file_name = "{}_seed-{}.png".format(rid, int(seed_tile.get("view_id", 0)))
    file_path = os.path.join(out_dir, file_name)
    rgb = b"".join(bytes(pixel) for pixel in canvas)
    _save_png(file_path, width, height, rgb)
    return file_path
