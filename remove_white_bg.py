# -*- coding: utf-8 -*-
"""
将桌宠图片的纯白背景去除，变为透明背景。
从备份目录读取原图，处理后保存到 assets 目录。
使用 flood fill 从图片边缘开始填充，只去除与背景连通的白色区域，
保护角色内部的白色部分（如眼白、白色衣服等）。
"""
import os
import glob
from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
SKIN_DIR = os.path.join(BASE, "assets", "skin", "girlfriend")
BACKUP_DIR = os.path.join(BASE, "assets", "skin", "girlfriend_backup")

# 颜色容差：与起点白色的最大通道差异
THRESH = 22
# 判定为"接近白色"的 RGB 最小值
WHITE_MIN = 235


def process_image(backup_path, out_path):
    img = Image.open(backup_path).convert("RGBA")
    w, h = img.size
    px = img.load()

    # 采样点：四角 + 四边中点 + 沿边均匀多点
    step = max(1, min(w, h) // 20)
    edge_points = set()
    for x in range(0, w, step):
        edge_points.add((x, 0))
        edge_points.add((x, h - 1))
    for y in range(0, h, step):
        edge_points.add((0, y))
        edge_points.add((w - 1, y))

    for pt in edge_points:
        x0, y0 = pt
        if 0 <= x0 < w and 0 <= y0 < h:
            r, g, b, a = px[x0, y0]
            # 只有起点接近白色时才 flood fill
            if r > WHITE_MIN and g > WHITE_MIN and b > WHITE_MIN:
                ImageDraw.floodfill(img, pt, (0, 0, 0, 0), thresh=THRESH)

    img.save(out_path)
    # 统计透明像素比例
    return w, h


def main():
    files = glob.glob(os.path.join(BACKUP_DIR, "**", "*.png"), recursive=True)
    print(f"找到 {len(files)} 张图片，从备份读取并处理...", flush=True)

    for i, backup_path in enumerate(files):
        rel = os.path.relpath(backup_path, BACKUP_DIR)
        out_path = os.path.join(SKIN_DIR, rel)
        try:
            w, h = process_image(backup_path, out_path)
            print(f"[{i + 1}/{len(files)}] 完成: {rel} ({w}x{h})", flush=True)
        except Exception as e:
            print(f"[{i + 1}/{len(files)}] 失败: {rel} -> {e}", flush=True)

    print("全部处理完成！", flush=True)


if __name__ == "__main__":
    main()
