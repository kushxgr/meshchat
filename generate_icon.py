from pathlib import Path

from PIL import Image, ImageDraw


def main():
    out = Path(__file__).with_name("assets") / "mesh_chat.ico"
    size = 256
    img = Image.new("RGBA", (size, size), (15, 23, 42, 255))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle(
        (18, 18, size - 18, size - 18),
        radius=42,
        fill=(31, 41, 55, 255),
        outline=(245, 158, 11, 255),
        width=6,
    )

    nodes = [(66, 82), (126, 58), (194, 88), (92, 168), (164, 178)]
    links = [(0, 1), (1, 2), (0, 3), (1, 3), (1, 4), (2, 4), (3, 4)]
    for a, b in links:
        draw.line((*nodes[a], *nodes[b]), fill=(148, 163, 184, 255), width=6)

    for x, y in nodes:
        draw.ellipse(
            (x - 12, y - 12, x + 12, y + 12),
            fill=(245, 158, 11, 255),
            outline=(255, 251, 235, 255),
            width=3,
        )

    draw.rounded_rectangle((84, 108, 172, 148), radius=18, fill=(17, 24, 39, 255), outline=(245, 158, 11, 255), width=3)
    draw.text((99, 118), "M", fill=(229, 231, 235, 255))

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(out)


if __name__ == "__main__":
    main()