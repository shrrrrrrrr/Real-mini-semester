"""素材预处理：
1. 从校徽 PNG 抠出三个素材（去纯色蓝背景）：
   - 校徽（中心圆形主体）
   - 校名（下方文字）
   - 组合体（上方 校徽+校名 横排）
2. 两张背景图：提亮 + 提饱和 + 像素化（与参考站像素风一致）。
产物输出到 frontend/src/assets/ 供前端直接引用。
"""

from PIL import Image, ImageEnhance

SRC = r"C:\Users\shr\Desktop\UI\buaa photos\2025072815560858.png"
BG_DAY = r"C:\Users\shr\Desktop\UI\buaa photos\春.jpg"
BG_NIGHT = r"C:\Users\shr\Desktop\UI\buaa photos\7F64F5267EC599519AA79441A21_1BEC5FD1_36918.jpg"
OUT = r"C:\Users\shr\Desktop\Real mini semester\frontend\src\assets"

BLUE = (0, 63, 149)  # 实测背景色


def is_bg(px, tol=60):
    """近似背景蓝判定（JPEG 压缩带来的色差容忍）。"""
    return all(abs(px[i] - BLUE[i]) <= tol for i in range(3))


def crop_nonbg_bbox(im, region, tol=60):
    """在指定区域内找非背景内容的最小包围盒。"""
    box = im.crop(region).convert("RGBA")
    xs, ys = [], []
    w, h = box.size
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            px = box.getpixel((x, y))
            if px[3] > 0 and not is_bg(px[:3], tol):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (region[0] + min(xs), region[1] + min(ys), region[0] + max(xs) + 1, region[1] + max(ys) + 1)


def make_transparent(im, tol=60):
    """把背景蓝变透明。"""
    rgba = im.convert("RGBA")
    w, h = rgba.size
    for y in range(h):
        for x in range(w):
            px = rgba.getpixel((x, y))
            if is_bg(px[:3], tol):
                rgba.putpixel((x, y), (px[0], px[1], px[2], 0))
    return rgba


im = Image.open(SRC)
W, H = im.size  # 1050×768

# ---- 布局假设（用户描述）：上=组合体（左校徽右校名）；中=大校徽；下=校名 ----
# 保守切块后各自找内容包围盒
top = crop_nonbg_bbox(im, (0, 0, W, H // 3))
mid = crop_nonbg_bbox(im, (0, H // 3, W, H * 2 // 3))
bottom = crop_nonbg_bbox(im, (0, H * 2 // 3, W, H))
print("bboxes:", top, mid, bottom)

# 大校徽（中部）
badge = make_transparent(im.crop(mid))
badge.save(f"{OUT}\\buaa-badge.png")
# 校名（下部）
name_img = make_transparent(im.crop(bottom))
name_img.save(f"{OUT}\\buaa-name.png")
# 组合体（上部）
combo = make_transparent(im.crop(top))
combo.save(f"{OUT}\\buaa-combo.png")
print("badge/name/combo saved:", badge.size, name_img.size, combo.size)

# ---- 背景图：提亮 + 提饱和 + 像素化 ----


def pixelate(src, dst, blocks=160, bright=1.25, sat=1.25):
    """像素化流程：缩小→提亮提饱→放大（最近邻）→ 存 PNG。

    blocks=160：横向 160 个色块（参考站像素颗粒度接近），
    提亮 25% + 提饱和 25%（用户要求"亮度和饱和度拉高一点"）。
    """
    img = Image.open(src).convert("RGB")
    w, h = img.size
    small = img.resize((blocks, max(1, round(blocks * h / w))), Image.LANCZOS)
    small = ImageEnhance.Brightness(small).enhance(bright)
    small = ImageEnhance.Color(small).enhance(sat)
    big = small.resize((1920, round(1920 * h / w)), Image.NEAREST)
    big.save(dst, optimize=True)
    print("bg saved:", dst, big.size)


pixelate(BG_DAY, f"{OUT}\\bg-day.png")
pixelate(BG_NIGHT, f"{OUT}\\bg-night.png")
