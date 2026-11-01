# What the hardware does with an out-of-range Q2.30 write

Findings for wayfinder ticket [What does the hardware do with an out-of-range Q2.30 write?](https://github.com/JohnnyGuerra/openpeq/issues/6). Throwaway branch — never merged.

## Answer: it is undocumented, so the software cannot rely on it

- No public datasheet for the Conexant/Synaptics CX31993 exists. The Framework Community thread "Audio Expansion Card - CX31993 Datasheet" (https://community.frame.work/t/audio-expansion-card-cx31993-datasheet/78809) is a request for one; the poster states they could not find it. Secondary summaries (WarmSea) give SNR/THD/power but nothing about coefficient formats or overflow behaviour.
- Nothing in the public protocol notes for WalkPlay/Savitech, KTMicro or Moondrop states what happens when a Q2.30 value is outside [-2, 2). The repo's own claim that writes "will corrupt OTP descriptors" (`dac-peq-manager/src/dac_peq/ktmicro_hid.py:16`, `:463-464`) is the project's own assertion, not a sourced fact. It is plausible — a fixed-mask-ROM part has no flash to write — but it is not verifiable from primary sources.
- General fixed-point guidance (https://dsp-workshop.nl/topics/finite-wordlength/index.html, https://dsp-workshop.nl/basics/09-biquad/embedded.html): overflow in a fixed-point biquad is a decision the implementer must make explicitly (wrap vs saturate); hardware accumulators typically saturate, and undefined overflow is the standard hazard. There is no basis for assuming the DAC clamps for us.

**Consequence for the map:** because the hardware behaviour is unknowable, the only defensible canonical behaviour is to validate coefficients before the write, not to rely on what the device does with a bad value. That is decision #5's job; this ticket supplies the constraint.

## Reachability — the divergence is latent, not live

Overflow needs |coef| >= 2. With the RBJ peak formula in `compute_walkplay_biquad` (`walkplay_hid.py:99-123`), `b1/a0 = -2cos(w0)/a0` is strictly inside [-2, 2) for normal inputs, so ordinary presets never overflow. It becomes reachable when Q is small:

- `f=1000, q=0.01, gain=40` -> `struct.error: 'i' format requires -2147483648 <= number <= 2147483647`
- `f=1000, q=0.05, gain=20` -> same error
- `f=20000, q=0.01, gain=12` -> same error
- `f=20, q=0.01, gain=12` -> packs fine

So the trigger is roughly `q < 0.1` combined with gain >= 12 dB. The three surfaces (Python raises, Rust saturates, JS wraps) disagree only on inputs the current UI cannot produce — which is why it looks harmless until a caller uses the API directly or the gain/Q limits change.
