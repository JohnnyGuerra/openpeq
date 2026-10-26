import os
import time
import subprocess
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from playwright.sync_api import sync_playwright

WEB_DIR = "/home/ubuntu/iem/dac-peq-manager/web"
OUTPUT_DIR = "/home/ubuntu/iem/dac-peq-manager/media"
RECORD_DIR = os.path.join(OUTPUT_DIR, "recordings")
os.makedirs(RECORD_DIR, exist_ok=True)

class WasmHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def guess_type(self, path):
        if path.endswith(".wasm"):
            return "application/wasm"
        return super().guess_type(path)

def run_server():
    httpd = HTTPServer(("127.0.0.1", 8765), WasmHandler)
    httpd.serve_forever()

def record_demo():
    for f in os.listdir(RECORD_DIR):
        if f.endswith(".webm") or f.endswith(".png"):
            try:
                os.remove(os.path.join(RECORD_DIR, f))
            except Exception:
                pass

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-web-security", "--no-sandbox"]
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 920},
            record_video_dir=RECORD_DIR,
            record_video_size={"width": 1440, "height": 920}
        )
        page = context.new_page()

        print("Navigating to local Web Flasher...")
        page.goto("http://127.0.0.1:8765/index.html")
        page.wait_for_load_state("networkidle")
        time.sleep(1.5)

        # 1. Enable Demo Mode
        print("Enabling Virtual DAC Demo Mode...")
        page.click("#chkDemoMode")
        time.sleep(2)

        # 2. Click through preset cards
        print("Selecting Simgot EW300 Silver preset...")
        page.click('.preset-card[data-preset="ew300-silver"]')
        time.sleep(2)

        print("Selecting Harman 2019v2 Target preset...")
        page.click('.preset-card[data-preset="harman-2019v2"]')
        time.sleep(2)

        # 3. Interactively tweak band 1 (bass boost) and band 4 (treble)
        print("Tweaking PEQ bands with real-time biquad response...")
        page.evaluate("""() => {
            const b1Gain = document.querySelector('input[data-band="0"][data-param="gain"]');
            if (b1Gain) {
                b1Gain.value = "5.5";
                b1Gain.dispatchEvent(new Event('input', { bubbles: true }));
                b1Gain.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }""")
        time.sleep(1.5)

        page.evaluate("""() => {
            const b4Gain = document.querySelector('input[data-band="3"][data-param="gain"]');
            if (b4Gain) {
                b4Gain.value = "3.5";
                b4Gain.dispatchEvent(new Event('input', { bubbles: true }));
                b4Gain.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }""")
        time.sleep(1.5)

        # 4. Click Audition in RAM
        print("Auditioning in volatile DSP RAM...")
        page.click("#btnApply")
        time.sleep(2.5)

        # 5. Burn to Hardware NVRAM
        print("Burning to hardware NVRAM flash...")
        page.evaluate("""() => {
            window.confirm = () => true;
        }""")
        page.click("#btnFlash")
        time.sleep(3.5)

        context.close()
        browser.close()

    files = [os.path.join(RECORD_DIR, f) for f in os.listdir(RECORD_DIR) if f.endswith(".webm")]
    if not files:
        print("Error: No recorded video found!")
        return

    latest_video = max(files, key=os.path.getmtime)
    print(f"Recorded video saved to: {latest_video}")

    # Convert to MP4 (h264, web-optimized)
    mp4_output = os.path.join(OUTPUT_DIR, "dac-peq-web-flasher-demo.mp4")
    print(f"Converting to MP4: {mp4_output}...")
    subprocess.run([
        "ffmpeg", "-y", "-i", latest_video,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "slow",
        "-movflags", "+faststart",
        mp4_output
    ], check=True)

    # Convert to High-Quality GIF (15 fps, 960px width, palettegen)
    gif_output = os.path.join(OUTPUT_DIR, "dac-peq-web-flasher-demo.gif")
    palette_path = os.path.join(RECORD_DIR, "palette.png")
    print(f"Generating palette for GIF: {palette_path}...")
    subprocess.run([
        "ffmpeg", "-y", "-i", mp4_output,
        "-vf", "fps=15,scale=960:-1:flags=lanczos,palettegen=stats_mode=diff",
        palette_path
    ], check=True)

    print(f"Converting to optimized GIF: {gif_output}...")
    subprocess.run([
        "ffmpeg", "-y", "-i", mp4_output, "-i", palette_path,
        "-filter_complex", "fps=15,scale=960:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
        gif_output
    ], check=True)

    print("SUCCESS: Both MP4 and GIF generated!")

if __name__ == "__main__":
    record_demo()
