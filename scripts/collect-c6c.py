"""Collect C6c snapshots for object-detection annotation without product tasks."""

from __future__ import annotations

import argparse
import asyncio
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.config import Settings  # noqa: E402
from app.devices.ezviz import EzvizClient, EzvizError  # noqa: E402

SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按间隔抓取萤石 C6c 图片，保存到本地并记录采集元数据。",
    )
    parser.add_argument("--count", type=int, default=1, help="抓图数量，默认 1")
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=30,
        help="两次抓图的间隔秒数，默认 30；批量采集时不得低于 5",
    )
    parser.add_argument("--camera-id", default="c6c01", help="脱敏后的相机编号")
    parser.add_argument("--lighting", default="unknown", help="光线，例如 day、light、night_ir")
    parser.add_argument("--scene", default="unknown", help="场景，例如 clear、box、mixed")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "evidence" / "c6c-collection",
        help="采集根目录",
    )
    args = parser.parse_args()
    if not SAFE_NAME.fullmatch(args.camera_id):
        parser.error("--camera-id 只能包含英文字母、数字、下划线和连字符")
    if not SAFE_NAME.fullmatch(args.lighting):
        parser.error("--lighting 只能包含英文字母、数字、下划线和连字符")
    if not SAFE_NAME.fullmatch(args.scene):
        parser.error("--scene 只能包含英文字母、数字、下划线和连字符")
    if args.count < 1:
        parser.error("--count 必须大于 0")
    if args.count > 1 and args.interval_seconds < 5:
        parser.error("批量采集时 --interval-seconds 不得低于 5")
    return args


def image_extension(content_type: str, content: bytes) -> str:
    normalized = content_type.partition(";")[0].strip().lower()
    if normalized in {"image/jpeg", "image/jpg"} or content.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if normalized == "image/png" or content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    raise ValueError(f"抓图结果不是支持的图片格式：{content_type or 'unknown'}")


def append_metadata(csv_path: Path, row: dict[str, str | int]) -> None:
    fieldnames = [
        "filename",
        "captured_at",
        "camera_id",
        "lighting",
        "scene",
        "bytes",
        "annotation",
    ]
    exists = csv_path.exists()
    with csv_path.open("a", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


async def collect(args: argparse.Namespace) -> int:
    settings = Settings(_env_file=REPO_ROOT / ".env")
    client = EzvizClient(settings)
    if not client.configured:
        print("请先在项目 .env 中配置 C6c 设备序列号和萤石开放平台凭据。", file=sys.stderr)
        await client.close()
        return 2

    camera_dir = args.output_root.resolve() / args.camera_id
    camera_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = camera_dir / "metadata.csv"
    succeeded = 0

    try:
        for index in range(args.count):
            if index:
                await asyncio.sleep(args.interval_seconds)
            captured_at = datetime.now().astimezone()
            try:
                picture_url = await client.capture()
                response = await client.client.get(picture_url, follow_redirects=True, timeout=45)
                response.raise_for_status()
                extension = image_extension(response.headers.get("content-type", ""), response.content)
                timestamp = captured_at.strftime("%Y%m%d_%H%M%S_%f")[:-3]
                filename = f"{args.camera_id}_{args.lighting}_{args.scene}_{timestamp}{extension}"
                image_path = camera_dir / filename
                temporary_path = image_path.with_suffix(image_path.suffix + ".part")
                temporary_path.write_bytes(response.content)
                temporary_path.replace(image_path)
                append_metadata(
                    metadata_path,
                    {
                        "filename": filename,
                        "captured_at": captured_at.isoformat(timespec="seconds"),
                        "camera_id": args.camera_id,
                        "lighting": args.lighting,
                        "scene": args.scene,
                        "bytes": len(response.content),
                        "annotation": "",
                    },
                )
                succeeded += 1
                print(f"[{succeeded}/{args.count}] 已保存 {image_path}")
            except (EzvizError, ValueError, OSError) as exc:
                print(f"第 {index + 1} 次抓图失败：{exc}", file=sys.stderr)
            except Exception as exc:  # HTTP errors include useful status text.
                print(f"第 {index + 1} 次下载失败：{exc}", file=sys.stderr)
    finally:
        await client.close()

    print(f"采集完成：成功 {succeeded} 张，计划 {args.count} 张；元数据：{metadata_path}")
    return 0 if succeeded == args.count else 1


def main() -> int:
    return asyncio.run(collect(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
