import os
import sys
from playwright.sync_api import sync_playwright

SLIDES_DIR = "/home/ubuntu/iem/dac-peq-manager/media/slides"
os.makedirs(SLIDES_DIR, exist_ok=True)

SLIDES_HTML = [
    # Slide 1: Hero & Overview
    """
    <div class="slide slide-hero">
      <div class="badge-row">
        <span class="pill pill-cyan">⚡ 100% WebHID Client-Side</span>
        <span class="pill pill-purple">🦀 Rust WebAssembly Core</span>
        <span class="pill pill-green">🛡️ Hardware Safety Shield</span>
        <span class="pill pill-gold">🔓 MIT Open Source</span>
      </div>
      <h1 class="hero-title"><span class="gradient-text">dac-peq-manager</span></h1>
      <p class="hero-subtitle">Zero-Install Hardware Parametric EQ Flasher for Portable USB-C DACs & IEM Cables</p>
      
      <div class="card-grid-3">
        <div class="feature-card">
          <div class="card-icon">🚀</div>
          <h3>Zero Installation</h3>
          <p>Runs directly in Chrome, Edge, or Brave. No sketchy APKs, no drivers, and no background software needed.</p>
        </div>
        <div class="feature-card">
          <div class="card-icon">💾</div>
          <h3>Hardware NVRAM Burn</h3>
          <p>Permanently burns custom 5-band / 9-band PEQ curves into onboard DAC flash in under 50ms.</p>
        </div>
        <div class="feature-card">
          <div class="card-icon">📱</div>
          <h3>True Portability</h3>
          <p>Flash once from your PC or laptop. Settings persist natively on iPhone, iPad, Android, Mac, Windows & Steam Deck.</p>
        </div>
      </div>

      <div class="footer-bar">
        <span>🌐 Live Web Flasher: <strong>johnnyguerra.github.io/dac-peq-manager/</strong></span>
        <span>⭐ GitHub: <strong>JohnnyGuerra/dac-peq-manager</strong></span>
      </div>
    </div>
    """,

    # Slide 2: Status Quo vs dac-peq-manager
    """
    <div class="slide">
      <div class="slide-header">
        <span class="pill pill-cyan">THE PROBLEM & THE SOLUTION</span>
        <h2>Why Audiophiles Need an Open-Source PEQ Tool</h2>
      </div>

      <div class="comparison-grid">
        <div class="comp-card card-bad">
          <div class="comp-badge bad-badge">❌ THE STATUS QUO (OEM APPS)</div>
          <ul class="comp-list">
            <li><strong>Sideloaded APKs:</strong> Requires downloading unsigned Chinese APKs with intrusive permissions (Location, Storage).</li>
            <li><strong>Zero iOS Support:</strong> iPhone & iPad users cannot tune or reflash their USB-C DACs or DSP cables.</li>
            <li><strong>Volume Lockout Bugs:</strong> Writing wrong registers locks out physical hardware volume buttons on phones.</li>
            <li><strong>Bricking Hazards:</strong> Fixed-mask ROM chips (Conexant CX31993) get corrupted by improper OTP register writes.</li>
            <li><strong>Abandoned Software:</strong> Companion apps break after OS updates and lack modern IEM presets.</li>
          </ul>
        </div>

        <div class="comp-card card-good">
          <div class="comp-badge good-badge">✅ DAC-PEQ-MANAGER (OPEN SOURCE)</div>
          <ul class="comp-list">
            <li><strong>Zero Install (WebHID):</strong> 100% browser-based. Runs instantly on any desktop, laptop, or Chromebook.</li>
            <li><strong>Universal Persistence:</strong> Burn your profile once; sound tuning stays on the hardware wherever you plug it.</li>
            <li><strong>Hardware Safety Guardrails:</strong> Automatic Conexant OTP write-block & Allegro Mini volume lock prevention.</li>
            <li><strong>AutoEq Integration:</strong> Instantly target 5,000+ measured IEMs and headphones (Crinacle, Oratory1990).</li>
            <li><strong>Rust + WASM Math:</strong> High-precision coordinate-descent biquad refitting compiled to WebAssembly.</li>
          </ul>
        </div>
      </div>

      <div class="footer-bar">
        <span>🔒 100% Private — Zero data or audio leaves your local machine.</span>
        <span>⭐ GitHub: <strong>JohnnyGuerra/dac-peq-manager</strong></span>
      </div>
    </div>
    """,

    # Slide 3: Web Flasher UI & Features
    """
    <div class="slide">
      <div class="slide-header">
        <span class="pill pill-purple">INTUITIVE CONTROL</span>
        <h2>Interactive Web Flasher Interface</h2>
      </div>

      <div class="feature-layout">
        <div class="feature-mockup">
          <div class="mockup-header">
            <span class="mock-dot red"></span>
            <span class="mock-dot yellow"></span>
            <span class="mock-dot green"></span>
            <span class="mock-title">⚡ dac-peq-manager WebHID Flasher</span>
            <span class="badge connected">🟢 Kiwi Ears Allegro Mini Connected</span>
          </div>
          <div class="mockup-curve">
            <svg viewBox="0 0 700 240" class="curve-svg">
              <defs>
                <linearGradient id="curveGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stop-color="#00f2fe" stop-opacity="0.35"/>
                  <stop offset="100%" stop-color="#4facfe" stop-opacity="0.0"/>
                </linearGradient>
              </defs>
              <!-- Grid lines -->
              <line x1="50" y1="30" x2="680" y2="30" stroke="#1f293d" stroke-dasharray="3,3"/>
              <line x1="50" y1="90" x2="680" y2="90" stroke="#1f293d" stroke-dasharray="3,3"/>
              <line x1="50" y1="150" x2="680" y2="150" stroke="#2a3854" stroke-width="1.5"/>
              <line x1="50" y1="210" x2="680" y2="210" stroke="#1f293d" stroke-dasharray="3,3"/>
              <text x="15" y="154" fill="#64748b" font-size="11">0 dB</text>
              <text x="10" y="94" fill="#64748b" font-size="11">+6 dB</text>
              <text x="10" y="214" fill="#64748b" font-size="11">-6 dB</text>
              <!-- Curve Fill & Line -->
              <path d="M 50 150 C 110 100, 160 85, 220 120 C 270 145, 340 155, 420 148 C 490 140, 560 90, 620 135 L 680 150 L 680 150 L 50 150 Z" fill="url(#curveGrad)"/>
              <path d="M 50 150 C 110 100, 160 85, 220 120 C 270 145, 340 155, 420 148 C 490 140, 560 90, 620 135 L 680 150" fill="none" stroke="#00f2fe" stroke-width="3"/>
              <!-- Draggable Points -->
              <circle cx="150" cy="90" r="7" fill="#00f2fe" stroke="#ffffff" stroke-width="2"/>
              <text x="140" y="75" fill="#00f2fe" font-size="12" font-weight="bold">B1: 65Hz (+5dB)</text>
              <circle cx="280" cy="142" r="6" fill="#a855f7" stroke="#ffffff" stroke-width="2"/>
              <text x="270" y="130" fill="#a855f7" font-size="11">B2: 450Hz</text>
              <circle cx="430" cy="148" r="6" fill="#a855f7" stroke="#ffffff" stroke-width="2"/>
              <text x="420" y="135" fill="#a855f7" font-size="11">B3: 2.1kHz</text>
              <circle cx="580" cy="105" r="7" fill="#00f2fe" stroke="#ffffff" stroke-width="2"/>
              <text x="560" y="90" fill="#00f2fe" font-size="12" font-weight="bold">B4: 6.8kHz (+4dB)</text>
            </svg>
          </div>
          <div class="mockup-actions">
            <span class="btn btn-secondary">🎧 Live Audition in RAM</span>
            <span class="btn btn-primary">🔥 Burn to Hardware NVRAM (&lt;50ms)</span>
          </div>
        </div>

        <div class="feature-bullets">
          <div class="f-item">
            <h4>🎯 Draggable Log-Frequency SVG Handles</h4>
            <p>Drag frequency and gain handles directly on the graph. Sliders update simultaneously with real-time biquad response.</p>
          </div>
          <div class="f-item">
            <h4>⚡ Live RAM Audition vs NVRAM Burn</h4>
            <p>Test changes instantly in volatile RAM with zero flash wear. When satisfied, click Burn to write to non-volatile flash memory.</p>
          </div>
          <div class="f-item">
            <h4>📦 5,000+ AutoEq Measurement Profiles</h4>
            <p>Direct integration with AutoEq targets from Crinacle, Bad Guy Good Audio Reviews, Oratory1990, and Super*Review.</p>
          </div>
        </div>
      </div>

      <div class="footer-bar">
        <span>🌐 Try it right now: <strong>johnnyguerra.github.io/dac-peq-manager/</strong></span>
        <span>⭐ GitHub: <strong>JohnnyGuerra/dac-peq-manager</strong></span>
      </div>
    </div>
    """,

    # Slide 4: Engineering Safety Guardrails
    """
    <div class="slide">
      <div class="slide-header">
        <span class="pill pill-green">HARDWARE SAFETY</span>
        <h2>Built with Multi-Tier Hardware Protections</h2>
      </div>

      <div class="safety-grid">
        <div class="safety-card">
          <div class="s-icon">🛡️</div>
          <h3>Conexant CX31993 OTP Shield</h3>
          <p>Conexant DACs use fixed mask ROM with One-Time Programmable (OTP) registers. The app automatically detects CX31993 devices and <strong>hard-blocks register flashing</strong>, routing them safely to PipeWire, EqualizerAPO, or Wavelet.</p>
        </div>

        <div class="safety-card">
          <div class="s-icon">🔊</div>
          <h3>Allegro Mini Volume Lockout Guard</h3>
          <p>Writing to registers 0x11 or 0x66 on Kiwi Ears Allegro Mini (KTMicro KT02H20) overwrites internal attenuation, breaking iOS/Android physical volume buttons. Our encoder strictly protects volume registers.</p>
        </div>

        <div class="safety-card">
          <div class="s-icon">⏳</div>
          <h3>Flash Wear-Out Health Tracker</h3>
          <p>DAC EEPROMs have finite write cycles (~10,000 commits). The flasher tracks cumulative burns per device VID:PID in local storage and alerts users if writes exceed safe daily thresholds.</p>
        </div>

        <div class="safety-card">
          <div class="s-icon">🔄</div>
          <h3>Automatic Stock Factory Backup</h3>
          <p>Before your very first burn, the flasher takes a silent snapshot of the manufacturer's original hardware tuning registers, allowing 1-click factory restore anytime.</p>
        </div>
      </div>

      <div class="footer-bar">
        <span>💡 Includes official <strong>0x43 CLEAR</strong> recovery command to restore volume control anytime.</span>
        <span>⭐ GitHub: <strong>JohnnyGuerra/dac-peq-manager</strong></span>
      </div>
    </div>
    """,

    # Slide 5: Compatibility Matrix & Call to Action
    """
    <div class="slide slide-cta">
      <div class="slide-header">
        <span class="pill pill-gold">ECOSYSTEM & COMPATIBILITY</span>
        <h2>Supported Devices & How to Get Started</h2>
      </div>

      <div class="matrix-grid">
        <div class="matrix-card">
          <div class="m-status">🟢 HARDWARE VERIFIED & TESTED</div>
          <ul class="m-items">
            <li><strong>Kiwi Ears Allegro Mini</strong> (Dual 3.5mm / 4.4mm KT02H20)</li>
            <li><strong>Moondrop FreeDSP / May Cable</strong> (9-Band DSP Cable)</li>
            <li><strong>BASN BmasterX 6 Plug</strong> (Type-C MMCX Mic Cable)</li>
            <li><strong>Rythflo WD01 / JCALLY JM12</strong> (Ultra-compact Type-C)</li>
            <li><strong>TTGK CX31993</strong> (Host-DSP Safe Verified)</li>
          </ul>
        </div>

        <div class="matrix-card">
          <div class="m-status">🟡 PROTOCOL READY (TESTERS WELCOME)</div>
          <ul class="m-items">
            <li><strong>Tangzu Wan'er SG 2 Type-C</strong> (Active DSP Cable)</li>
            <li><strong>FiiO / JadeAudio JA11</strong> (USB-C PEQ Dongle)</li>
            <li><strong>Moondrop Chu II DSP</strong> (Integrated Type-C IEM)</li>
            <li><strong>Tanchjim ONE DSP / SPACE Lite</strong> (DSP Cable / DAC)</li>
            <li><strong>Simgot EW300 DSP</strong> (Modular USB-C DSP)</li>
          </ul>
        </div>
      </div>

      <div class="cta-box">
        <div class="cta-text">
          <h3>Try the Web Flasher & Support the Project</h3>
          <p>Open source under MIT. No sign-up, no analytics tracking, no ads.</p>
        </div>
        <div class="cta-links">
          <div class="cta-btn primary">👉 johnnyguerra.github.io/dac-peq-manager/</div>
          <div class="cta-btn secondary">⭐ Star on GitHub: JohnnyGuerra/dac-peq-manager</div>
        </div>
      </div>
    </div>
    """
]

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
body { background: #070a12; color: #f1f5f9; width: 1920px; height: 1080px; overflow: hidden; display: flex; align-items: center; justify-content: center; }

.slide {
  width: 1920px;
  height: 1080px;
  background: radial-gradient(circle at 15% 15%, #151d30 0%, #080c16 65%, #05070d 100%);
  padding: 65px 85px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  position: relative;
  box-shadow: inset 0 0 120px rgba(0, 0, 0, 0.8);
}

.slide::after {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0; height: 4px;
  background: linear-gradient(90deg, #00f2fe 0%, #4facfe 35%, #7928ca 70%, #ff0080 100%);
}

.badge-row { display: flex; gap: 14px; margin-bottom: 24px; }
.pill {
  font-size: 15px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;
  padding: 8px 18px; border-radius: 9999px; display: inline-flex; align-items: center; gap: 8px;
}
.pill-cyan { background: rgba(0, 242, 254, 0.12); color: #00f2fe; border: 1px solid rgba(0, 242, 254, 0.35); }
.pill-purple { background: rgba(168, 85, 247, 0.12); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.35); }
.pill-green { background: rgba(34, 197, 94, 0.12); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.35); }
.pill-gold { background: rgba(234, 179, 8, 0.12); color: #fde047; border: 1px solid rgba(234, 179, 8, 0.35); }

.hero-title { font-size: 84px; font-weight: 900; letter-spacing: -2px; line-height: 1.05; margin-bottom: 16px; }
.gradient-text {
  background: linear-gradient(135deg, #ffffff 30%, #00f2fe 75%, #4facfe 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.hero-subtitle { font-size: 28px; color: #94a3b8; max-width: 1400px; line-height: 1.4; margin-bottom: 30px; }

.card-grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 28px; margin-bottom: 20px; }
.feature-card {
  background: rgba(18, 26, 43, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  padding: 36px 32px;
  backdrop-filter: blur(12px);
  transition: all 0.2s ease;
}
.card-icon { font-size: 44px; margin-bottom: 18px; }
.feature-card h3 { font-size: 26px; color: #ffffff; margin-bottom: 12px; font-weight: 700; }
.feature-card p { font-size: 18px; color: #94a3b8; line-height: 1.5; }

.footer-bar {
  display: flex; justify-content: space-between; align-items: center;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  padding-top: 22px; font-size: 19px; color: #64748b;
}
.footer-bar strong { color: #e2e8f0; font-weight: 600; }

.slide-header { margin-bottom: 28px; }
.slide-header h2 { font-size: 50px; font-weight: 800; color: #ffffff; margin-top: 10px; letter-spacing: -1px; }

/* Slide 2 Comparison */
.comparison-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 36px; margin-bottom: 20px; }
.comp-card {
  border-radius: 20px; padding: 40px; display: flex; flex-direction: column; gap: 20px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
}
.card-bad { background: rgba(30, 15, 20, 0.6); border: 1px solid rgba(239, 68, 68, 0.25); }
.card-good { background: rgba(12, 32, 35, 0.6); border: 1px solid rgba(0, 242, 254, 0.35); }
.comp-badge { font-size: 16px; font-weight: 800; letter-spacing: 1px; padding: 8px 18px; border-radius: 8px; width: fit-content; }
.bad-badge { background: rgba(239, 68, 68, 0.18); color: #f87171; }
.good-badge { background: rgba(0, 242, 254, 0.18); color: #00f2fe; }
.comp-list { list-style: none; display: flex; flex-direction: column; gap: 16px; }
.comp-list li { font-size: 19px; color: #cbd5e1; line-height: 1.5; padding-left: 28px; position: relative; }
.card-bad .comp-list li::before { content: "✕"; position: absolute; left: 0; color: #ef4444; font-weight: bold; }
.card-good .comp-list li::before { content: "✓"; position: absolute; left: 0; color: #00f2fe; font-weight: bold; }
.comp-list strong { color: #ffffff; }

/* Slide 3 Layout */
.feature-layout { display: grid; grid-template-columns: 1.15fr 0.85fr; gap: 40px; align-items: center; margin-bottom: 20px; }
.feature-mockup {
  background: #0d1322; border: 1px solid rgba(0, 242, 254, 0.25); border-radius: 18px;
  padding: 24px; box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
}
.mockup-header { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; font-size: 15px; color: #94a3b8; }
.mock-dot { width: 12px; height: 12px; border-radius: 50%; }
.mock-dot.red { background: #ef4444; }
.mock-dot.yellow { background: #f59e0b; }
.mock-dot.green { background: #10b981; }
.mock-title { font-weight: 600; color: #cbd5e1; margin-left: 6px; }
.mockup-header .badge { margin-left: auto; font-size: 13px; font-weight: bold; color: #4ade80; background: rgba(74, 222, 128, 0.15); padding: 4px 12px; border-radius: 9999px; }
.mockup-curve { background: #070c17; border-radius: 12px; padding: 16px; margin-bottom: 18px; border: 1px solid rgba(255, 255, 255, 0.05); }
.curve-svg { width: 100%; height: 230px; }
.mockup-actions { display: flex; gap: 14px; justify-content: flex-end; }
.btn { padding: 12px 22px; border-radius: 10px; font-weight: 700; font-size: 16px; }
.btn-secondary { background: #1e293b; color: #cbd5e1; border: 1px solid rgba(255, 255, 255, 0.1); }
.btn-primary { background: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%); color: #04101e; border: none; }
.feature-bullets { display: flex; flex-direction: column; gap: 24px; }
.f-item { background: rgba(18, 26, 43, 0.6); padding: 22px 26px; border-radius: 14px; border-left: 4px solid #00f2fe; }
.f-item h4 { font-size: 21px; color: #ffffff; margin-bottom: 8px; }
.f-item p { font-size: 16px; color: #94a3b8; line-height: 1.4; }

/* Slide 4 Safety */
.safety-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 26px; margin-bottom: 20px; }
.safety-card {
  background: rgba(16, 24, 39, 0.75); border: 1px solid rgba(34, 197, 94, 0.2);
  border-radius: 18px; padding: 32px 30px; display: flex; flex-direction: column; gap: 12px;
}
.s-icon { font-size: 38px; }
.safety-card h3 { font-size: 24px; color: #4ade80; font-weight: 700; }
.safety-card p { font-size: 17px; color: #94a3b8; line-height: 1.5; }
.safety-card strong { color: #f1f5f9; }

/* Slide 5 Matrix & CTA */
.matrix-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 32px; margin-bottom: 26px; }
.matrix-card {
  background: rgba(16, 24, 40, 0.7); border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px; padding: 28px 32px;
}
.m-status { font-size: 16px; font-weight: 800; letter-spacing: 1px; margin-bottom: 16px; color: #4ade80; }
.matrix-card:last-child .m-status { color: #fde047; }
.m-items { list-style: none; display: flex; flex-direction: column; gap: 12px; font-size: 18px; color: #cbd5e1; }
.m-items strong { color: #ffffff; }
.cta-box {
  background: linear-gradient(135deg, rgba(0, 242, 254, 0.12) 0%, rgba(121, 40, 202, 0.15) 100%);
  border: 1px solid rgba(0, 242, 254, 0.35); border-radius: 18px;
  padding: 28px 40px; display: flex; justify-content: space-between; align-items: center;
}
.cta-text h3 { font-size: 28px; color: #ffffff; margin-bottom: 6px; }
.cta-text p { font-size: 18px; color: #94a3b8; }
.cta-links { display: flex; gap: 16px; }
.cta-btn { padding: 14px 26px; border-radius: 12px; font-weight: 700; font-size: 18px; }
.cta-btn.primary { background: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%); color: #04101e; }
.cta-btn.secondary { background: rgba(255, 255, 255, 0.08); color: #ffffff; border: 1px solid rgba(255, 255, 255, 0.15); }
"""

def generate_slides():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        
        for idx, slide_html in enumerate(SLIDES_HTML, start=1):
            full_html = f"<!DOCTYPE html><html><head><style>{CSS}</style></head><body>{slide_html}</body></html>"
            page.set_content(full_html)
            output_path = os.path.join(SLIDES_DIR, f"slide_{idx}.png")
            page.screenshot(path=output_path, full_page=True)
            print(f"Generated Slide {idx}: {output_path}")
            
        browser.close()

if __name__ == "__main__":
    generate_slides()
