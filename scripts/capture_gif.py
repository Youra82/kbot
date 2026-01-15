import asyncio
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
HTML_PATH = ROOT / "kbot_illustration.html"
PNG_PATH = ROOT / "artifacts" / "kbot_illustration_preview.png"
GIF_PATH = ROOT / "artifacts" / "kbot_illustration_preview.gif"


async def capture_png() -> None:
    PNG_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1500, "height": 2000})
        await page.goto(HTML_PATH.as_uri())
        await page.wait_for_timeout(1500)  # allow Chart.js render
        await page.screenshot(path=str(PNG_PATH), full_page=True)
        await browser.close()


def convert_to_gif() -> None:
    image = Image.open(PNG_PATH)
    # Single-frame GIF keeps file size low while working on GitHub
    image.save(GIF_PATH, format="GIF", save_all=True, loop=0, duration=500)


def main() -> None:
    if not HTML_PATH.exists():
        raise FileNotFoundError(f"HTML file not found: {HTML_PATH}")
    asyncio.run(capture_png())
    convert_to_gif()
    print(f"Saved PNG to {PNG_PATH}")
    print(f"Saved GIF to {GIF_PATH}")


if __name__ == "__main__":
    main()
