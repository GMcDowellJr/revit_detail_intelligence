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


def _paeth(a, b, c):
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _load_png_rgb(path):
    with open(path, "rb") as handle:
        data = handle.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not a PNG file")

    pos = 8
    width = height = None
    bit_depth = color_type = interlace = None
    compressed = b""
    while pos < len(data):
        length = struct.unpack("!I", data[pos : pos + 4])[0]
        pos += 4
        ctype = data[pos : pos + 4]
        pos += 4
        cdata = data[pos : pos + length]
        pos += length
        pos += 4

        if ctype == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack("!2I5B", cdata)
        elif ctype == b"IDAT":
            compressed += cdata
        elif ctype == b"IEND":
            break

    if not width or not height:
        raise ValueError("PNG missing IHDR")
    if bit_depth != 8 or interlace != 0:
        raise ValueError("Unsupported PNG format")

    if color_type == 2:
        bpp = 3
    elif color_type == 6:
        bpp = 4
    else:
        raise ValueError("Unsupported PNG color type")

    raw = zlib.decompress(compressed)
    stride = width * bpp
    recon_rows = []
    i = 0
    prev = bytearray(stride)
    for _ in range(height):
        f = raw[i]
        i += 1
        row = bytearray(raw[i : i + stride])
        i += stride

        if f == 0:
            pass
        elif f == 1:
            for x in range(stride):
                left = row[x - bpp] if x >= bpp else 0
                row[x] = (row[x] + left) & 0xFF
        elif f == 2:
            for x in range(stride):
                row[x] = (row[x] + prev[x]) & 0xFF
        elif f == 3:
            for x in range(stride):
                left = row[x - bpp] if x >= bpp else 0
                up = prev[x]
                row[x] = (row[x] + ((left + up) // 2)) & 0xFF
        elif f == 4:
            for x in range(stride):
                left = row[x - bpp] if x >= bpp else 0
                up = prev[x]
                ul = prev[x - bpp] if x >= bpp else 0
                row[x] = (row[x] + _paeth(left, up, ul)) & 0xFF
        else:
            raise ValueError("Unsupported PNG filter")

        recon_rows.append(bytes(row))
        prev = row

    rgb = bytearray(width * height * 3)
    out = 0
    for row in recon_rows:
        if bpp == 3:
            for idx in range(0, len(row), 3):
                rgb[out : out + 3] = row[idx : idx + 3]
                out += 3
        else:
            for idx in range(0, len(row), 4):
                r, g, b, a = row[idx], row[idx + 1], row[idx + 2], row[idx + 3]
                if a < 255:
                    r = (r * a + 255 * (255 - a)) // 255
                    g = (g * a + 255 * (255 - a)) // 255
                    b = (b * a + 255 * (255 - a)) // 255
                rgb[out : out + 3] = bytes((r, g, b))
                out += 3

    return width, height, bytes(rgb)


def _draw_preview_image(canvas, canvas_w, canvas_h, x, y, w, h, preview_path):
    if not preview_path or not os.path.exists(preview_path):
        return False
    try:
        src_w, src_h, src = _load_png_rgb(preview_path)
    except Exception:
        return False

    scale = min(float(w) / max(1, src_w), float(h) / max(1, src_h))
    draw_w = max(1, int(src_w * scale))
    draw_h = max(1, int(src_h * scale))
    off_x = x + (w - draw_w) // 2
    off_y = y + (h - draw_h) // 2

    for dy in range(draw_h):
        sy = min(src_h - 1, int((dy / float(draw_h)) * src_h))
        for dx in range(draw_w):
            sx = min(src_w - 1, int((dx / float(draw_w)) * src_w))
            si = (sy * src_w + sx) * 3
            color = (src[si], src[si + 1], src[si + 2])
            _set_px(canvas, canvas_w, canvas_h, off_x + dx, off_y + dy, color)
    return True


def write_contact_sheet_png(seed_tile, candidate_tiles, config, run_id=None):
    out_dir = ensure_dir(resolve_contact_sheets_dir(config))
    rid = run_id or run_stamp("contact")

    tile_w = int(config.get("contact_sheet", {}).get("tile_width", 480))
    tile_h = int(config.get("contact_sheet", {}).get("tile_height", 320))
    cols = int(config.get("contact_sheet", {}).get("columns", 3))
    rows = 1 + ((len(candidate_tiles) + (cols - 1)) // cols)
    width = cols * tile_w + (cols + 1) * 10
    height = rows * tile_h + (rows + 1) * 10

    canvas = _new_canvas(width, height, color=(246, 246, 246))

    tiles = [seed_tile] + list(candidate_tiles)
    for idx, tile in enumerate(tiles):
        row = idx // cols
        col = idx % cols
        x = 10 + col * (tile_w + 10)
        y = 10 + row * (tile_h + 10)

        bg = (220, 235, 255) if idx == 0 else (255, 255, 255)
        _fill_rect(canvas, width, height, x, y, tile_w, tile_h, bg)
        _fill_rect(canvas, width, height, x, y, tile_w, 2, (70, 70, 70))
        _fill_rect(canvas, width, height, x, y + tile_h - 2, tile_w, 2, (70, 70, 70))
        _fill_rect(canvas, width, height, x, y, 2, tile_h, (70, 70, 70))
        _fill_rect(canvas, width, height, x + tile_w - 2, y, 2, tile_h, (70, 70, 70))

        preview_w = tile_w - 20
        preview_h = int(tile_h * 0.65)
        px = x + 10
        py = y + 10
        pcol = (165, 205, 175) if idx == 0 else (230, 230, 230)
        _fill_rect(canvas, width, height, px, py, preview_w, preview_h, pcol)
        drew = _draw_preview_image(
            canvas, width, height, px, py, preview_w, preview_h, tile.get("preview_path")
        )
        if not drew:
            _draw_text(
                canvas,
                width,
                height,
                px + 20,
                py + (preview_h // 2) - 8,
                "PREVIEW",
                (20, 20, 20),
                scale=3,
            )

        lines = _tile_lines(tile, rank=idx if idx > 0 else None)
        line_y = y + preview_h + 20
        for line in lines[:4]:
            _draw_text(canvas, width, height, x + 10, line_y, line[:48], (10, 10, 10), scale=2)
            line_y += 16

    file_name = "{}_seed-{}.png".format(rid, int(seed_tile.get("view_id", 0)))
    file_path = os.path.join(out_dir, file_name)
    rgb = b"".join(bytes(pixel) for pixel in canvas)
    _save_png(file_path, width, height, rgb)
    return file_path
