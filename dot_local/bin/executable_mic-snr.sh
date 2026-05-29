#!/usr/bin/env bash
# Mic SNR & quality test:
#   - record noise floor + signal
#   - time-domain metrics via ffmpeg astats
#   - frequency-domain metrics via Welch PSD (pure-Python FFT)
#   - output: broadband SNR, band SNR, ENOB, resolution, hum detection, grade
#
# Usage:
#   /tmp/mic-snr.sh                 # interactive, default device, 16kHz mono
#   /tmp/mic-snr.sh -d <source>     # specify pulse/pipewire source name
#   /tmp/mic-snr.sh -n 3 -s 5       # noise 3s, signal 5s
#   /tmp/mic-snr.sh -r 48000        # sample rate (default 16000)
#   /tmp/mic-snr.sh -o <dir>        # output directory (default: /tmp/mic-snr)
#   /tmp/mic-snr.sh -t <tag>        # filename tag (default: timestamp)
#   /tmp/mic-snr.sh -A <noise.wav> <signal.wav>   # analyze existing files, skip recording
#   /tmp/mic-snr.sh -l              # list input sources and exit
set -euo pipefail

NOISE_SEC=3
SIGNAL_SEC=5
RATE=16000
DEVICE=""
WORK="/tmp/mic-snr"
TAG=""
ANALYZE_ONLY=0

SAMPLE_TEXT_JA="あらゆる現実を、すべて自分のほうへねじ曲げたのだ。"
SAMPLE_TEXT_JA_KANA="(あらゆるげんじつを、すべてじぶんのほうへねじまげたのだ。)"

usage() { sed -n '2,17p' "$0"; exit 1; }

while getopts ":d:n:s:r:o:t:Alh" opt; do
  case "$opt" in
    d) DEVICE="$OPTARG" ;;
    n) NOISE_SEC="$OPTARG" ;;
    s) SIGNAL_SEC="$OPTARG" ;;
    r) RATE="$OPTARG" ;;
    o) WORK="$OPTARG" ;;
    t) TAG="$OPTARG" ;;
    A) ANALYZE_ONLY=1 ;;
    l) pactl list short sources; exit 0 ;;
    h|*) usage ;;
  esac
done
shift $((OPTIND-1))

if [[ "$ANALYZE_ONLY" -eq 1 ]]; then
  [[ $# -eq 2 ]] || { echo "-A requires two file args: <noise.wav> <signal.wav>" >&2; exit 2; }
  NOISE_WAV="$1"
  SIGNAL_WAV="$2"
else
  slugify() { printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_' | sed -E 's/_+/_/g; s/^_+|_+$//g'; }
  : "${TAG:=$(date +%Y%m%d-%H%M%S)}"
  DEV_SLUG=""
  [[ -n "$DEVICE" ]] && DEV_SLUG="_$(slugify "$DEVICE")"
  BASE="snr_${TAG}${DEV_SLUG}_${RATE}Hz"
  mkdir -p "$WORK"
  NOISE_WAV="$WORK/${BASE}_noise.wav"
  SIGNAL_WAV="$WORK/${BASE}_signal.wav"

  REC_ARGS=(--rate="$RATE" --channels=1 --format=s16le --file-format=wav)
  [[ -n "$DEVICE" ]] && REC_ARGS+=(--device="$DEVICE")

  echo ">> Default source: $(pactl get-default-source 2>/dev/null || echo unknown)"
  [[ -n "$DEVICE" ]] && echo ">> Using device: $DEVICE"

  read -r -p ">> [1/2] Stay SILENT. Press Enter to record ${NOISE_SEC}s of noise floor..." _
  parecord "${REC_ARGS[@]}" "$NOISE_WAV" &
  REC_PID=$!
  sleep "$NOISE_SEC"
  kill "$REC_PID" 2>/dev/null || true
  wait "$REC_PID" 2>/dev/null || true
  echo "   saved: $NOISE_WAV"

  cat <<EOF

>> [2/2] 以下の文章を自然な速さで読み上げてください (${SIGNAL_SEC}秒録音):
   ┌──────────────────────────────────────────────────────────┐
   │  ${SAMPLE_TEXT_JA}
   │  ${SAMPLE_TEXT_JA_KANA}
   └──────────────────────────────────────────────────────────┘
EOF
  read -r -p ">> 準備ができたら Enter..." _
  parecord "${REC_ARGS[@]}" "$SIGNAL_WAV" &
  REC_PID=$!
  sleep "$SIGNAL_SEC"
  kill "$REC_PID" 2>/dev/null || true
  wait "$REC_PID" 2>/dev/null || true
  echo "   saved: $SIGNAL_WAV"
fi

python3 - "$NOISE_WAV" "$SIGNAL_WAV" <<'PY'
import sys, math, cmath, wave, array, subprocess, re

NPERSEG = 1024  # FFT window (freq resolution = sr/NPERSEG Hz)

# ---------------------------------------------------------------- WAV loader
def load_wav(path):
    with wave.open(path, "rb") as w:
        sw, ch, sr, n = w.getsampwidth(), w.getnchannels(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw != 2:
        raise SystemExit(f"unsupported sample width {sw} in {path}")
    a = array.array("h"); a.frombytes(raw)
    if ch > 1:
        mono = array.array("h", [0]*(len(a)//ch))
        for i in range(len(mono)):
            s = 0
            for c in range(ch): s += a[i*ch+c]
            mono[i] = s // ch
        a = mono
    return [s/32768.0 for s in a], sr, ch, sw, len(a)

# ------------------------------------------------------------- ffmpeg astats
ASTATS_KEY_RE = re.compile(r"\]\s+([A-Za-z][\w\s\(\)/+\-\.]*?):\s*(\S.*)$")
def astats(path):
    """Parse ffmpeg astats stderr. Take last occurrence per key so that
    'Overall' values override per-channel values when both exist."""
    cmd = ["ffmpeg", "-nostats", "-hide_banner", "-i", path,
           "-af", "astats=metadata=1:reset=0", "-f", "null", "-"]
    out = subprocess.run(cmd, capture_output=True, text=True).stderr
    metrics = {}
    for line in out.splitlines():
        m = ASTATS_KEY_RE.search(line)
        if not m: continue
        key, val = m.group(1).strip(), m.group(2).strip()
        try: metrics[key] = float(val)
        except ValueError: metrics[key] = val
    return metrics

# ------------------------------------------------------ pure-Python radix-2 FFT
def fft_inplace(x):
    n = len(x)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit; bit >>= 1
        j ^= bit
        if i < j: x[i], x[j] = x[j], x[i]
    length = 2
    while length <= n:
        half = length >> 1
        wstep = cmath.exp(-2j * math.pi / length)
        for start in range(0, n, length):
            w = 1+0j
            for k in range(half):
                t = w * x[start + k + half]
                x[start + k + half] = x[start + k] - t
                x[start + k] = x[start + k] + t
                w *= wstep
        length <<= 1
    return x

def welch_psd(samples, sr, nperseg=NPERSEG):
    noverlap = nperseg // 2
    step = nperseg - noverlap
    win = [0.5 - 0.5*math.cos(2*math.pi*i/(nperseg-1)) for i in range(nperseg)]
    win_pow = sum(w*w for w in win)
    nbins = nperseg // 2 + 1
    psd = [0.0] * nbins
    nseg = 0
    pos = 0
    while pos + nperseg <= len(samples):
        seg = [complex(samples[pos+i]*win[i], 0.0) for i in range(nperseg)]
        fft_inplace(seg)
        for k in range(nbins):
            re_, im_ = seg[k].real, seg[k].imag
            psd[k] += re_*re_ + im_*im_
        nseg += 1
        pos += step
    if nseg == 0:
        return [0.0]*nbins, [i*sr/nperseg for i in range(nbins)]
    scale = 1.0 / (sr * win_pow * nseg)
    out = []
    for k in range(nbins):
        v = psd[k] * scale
        if 0 < k < nbins-1: v *= 2
        out.append(v)
    freqs = [k*sr/nperseg for k in range(nbins)]
    return out, freqs

# --------------------------------------------------------- spectral metrics
def band_power(psd, freqs, f_lo, f_hi):
    p = 0.0
    df = freqs[1] - freqs[0]
    for k, f in enumerate(freqs):
        if f < f_lo or f > f_hi: continue
        p += psd[k] * df
    return p

def spectral_centroid(psd, freqs):
    num = sum(f*p for f, p in zip(freqs, psd))
    den = sum(psd)
    return num/den if den > 0 else 0.0

def spectral_rolloff(psd, freqs, frac):
    total = sum(psd)
    if total <= 0: return 0.0
    threshold = frac * total
    cumsum = 0.0
    for f, p in zip(freqs, psd):
        cumsum += p
        if cumsum >= threshold: return f
    return freqs[-1]

def spectral_flatness(psd):
    vals = [p for p in psd if p > 0]
    if len(vals) < 2: return 0.0
    log_sum = sum(math.log(v) for v in vals)
    gmean = math.exp(log_sum / len(vals))
    amean = sum(vals) / len(vals)
    return gmean / amean if amean > 0 else 0.0

def top_peaks(psd, freqs, n=5, min_freq=20):
    # local maxima first, then take top-n by magnitude
    locals_ = []
    for k in range(1, len(psd)-1):
        if freqs[k] < min_freq: continue
        if psd[k] > psd[k-1] and psd[k] > psd[k+1]:
            locals_.append((psd[k], freqs[k]))
    locals_.sort(reverse=True)
    return locals_[:n]

def db10(x): return 10*math.log10(x) if x > 0 else float("-inf")
def db20(x): return 20*math.log10(x) if x > 0 else float("-inf")

# --------------------------------------------------------- bit depth parse
def parse_bd(s):
    if isinstance(s, str) and "/" in s:
        parts = s.split("/")
        try: return int(parts[0]), int(parts[1])
        except: pass
    return None, None

# =========================================================================
noise_path, signal_path = sys.argv[1], sys.argv[2]
ns, sr_n, ch_n, sw_n, nn = load_wav(noise_path)
ss, sr_s, ch_s, sw_s, nns = load_wav(signal_path)
if sr_n != sr_s:
    raise SystemExit(f"sample rate mismatch: noise={sr_n} signal={sr_s}")
sr = sr_n
nyq = sr / 2

print()
print("="*70)
print("  Mic Quality Report")
print(f"  Noise : {noise_path}")
print(f"  Signal: {signal_path}")
print(f"  Format: {sr} Hz, {sw_n*8}-bit container, mono after downmix")
print(f"  Length: noise={nn/sr:.2f}s ({nn} samp), signal={nns/sr:.2f}s ({nns} samp)")
print("="*70)

# ---------------------------------------------------- time-domain (astats)
an, asig = astats(noise_path), astats(signal_path)

def num(d, k, default=None):
    v = d.get(k, default)
    return v if isinstance(v, (int, float)) else default

print("\n[Time-domain — ffmpeg astats: Overall]")
rows = [
    ("DC offset",          "DC offset",            "{:>+10.6f}"),
    ("Peak level (dBFS)",  "Peak level dB",        "{:>+10.2f}"),
    ("RMS level (dBFS)",   "RMS level dB",         "{:>+10.2f}"),
    ("RMS peak (dBFS)",    "RMS peak dB",          "{:>+10.2f}"),
    ("Crest factor",       "Crest factor",         "{:>10.2f}"),
    ("Flat factor",        "Flat factor",          "{:>10.3f}"),
    ("Peak count",         "Peak count",           "{:>10.0f}"),
    ("Noise floor (dBFS)", "Noise floor dB",       "{:>+10.2f}"),
    ("Entropy",            "Entropy",              "{:>10.3f}"),
    ("Dynamic range (dB)", "Dynamic range",        "{:>10.2f}"),
    ("Zero-crossings",     "Zero crossings",       "{:>10.0f}"),
    ("ZCR",                "Zero crossings rate",  "{:>10.4f}"),
    ("Bit depth (used)",   "Bit depth",            "{:>10s}"),
]
print(f"  {'Metric':<22}{'Noise':>16}{'Signal':>16}")
print(f"  {'-'*22}{'-'*16:>16}{'-'*16:>16}")
def fmt(v, f):
    if v is None: return "—"
    try:
        if isinstance(v, str) and "{:" in f and "s}" in f: return f.format(v)
        return f.format(v).strip().rjust(16)
    except: return str(v).rjust(16)
for label, k, f in rows:
    nv = an.get(k); sv = asig.get(k)
    nstr = fmt(nv, f).strip().rjust(16) if nv is not None else "—".rjust(16)
    sstr = fmt(sv, f).strip().rjust(16) if sv is not None else "—".rjust(16)
    print(f"  {label:<22}{nstr}{sstr}")

# ------------------------------------------------------ frequency-domain
print(f"\n[Frequency-domain — Welch PSD N={NPERSEG} ({sr/NPERSEG:.1f} Hz/bin), Hann window]")
psd_n, freqs = welch_psd(ns, sr)
psd_s, _     = welch_psd(ss, sr)

cent_n = spectral_centroid(psd_n, freqs)
cent_s = spectral_centroid(psd_s, freqs)
flat_n = spectral_flatness(psd_n)
flat_s = spectral_flatness(psd_s)
roll85 = spectral_rolloff(psd_s, freqs, 0.85)
roll95 = spectral_rolloff(psd_s, freqs, 0.95)

print(f"  noise   centroid: {cent_n:>7.1f} Hz   flatness: {flat_n:>5.3f}   "
      f"(1=white noise, 0=tonal)")
print(f"  signal  centroid: {cent_s:>7.1f} Hz   flatness: {flat_s:>5.3f}   "
      f"rolloff 85%/95%: {roll85:>5.0f}/{roll95:.0f} Hz")

print("\n  Noise spectrum — top peaks (local maxima):")
hum_warn = None
for p, f in top_peaks(psd_n, freqs, 6):
    tag = ""
    for hum in (50, 60, 100, 120, 150, 180, 200, 240):
        if abs(f - hum) < sr/NPERSEG:
            tag = f"  ← {hum} Hz {'mains' if hum in (50,60) else 'harmonic'}"
            if hum_warn is None and db10(p) > -65: hum_warn = (f, db10(p))
            break
    print(f"    {f:>7.1f} Hz   PSD {db10(p):>+7.2f} dB/Hz{tag}")

print("\n  Signal spectrum — top peaks (likely fundamentals/formants):")
for p, f in top_peaks(psd_s, freqs, 6):
    print(f"    {f:>7.1f} Hz   PSD {db10(p):>+7.2f} dB/Hz")

# ---------------------------------------------------------------- band SNR
print("\n[Octave-band SNR (signal vs noise, dB)]")
centers = [31.25, 62.5, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
bands = []
for fc in centers:
    lo, hi = fc/math.sqrt(2), fc*math.sqrt(2)
    if lo >= nyq: break
    hi = min(hi, nyq - sr/NPERSEG)
    bands.append((lo, hi, fc))

header = "  " + " ".join(f"{(f'{int(b[2])}Hz' if b[2]<1000 else f'{b[2]/1000:g}kHz'):>9}" for b in bands)
print(header)
row = "  "
for lo, hi, fc in bands:
    pn = band_power(psd_n, freqs, lo, hi)
    ps = band_power(psd_s, freqs, lo, hi)
    if pn > 0 and ps > 0:
        snr = 10*math.log10(ps/pn)
        row += f"{snr:>+9.1f}"
    else:
        row += f"{'—':>9}"
print(row)

# ------------------------------------------------------------- broadband
rms_n_db = num(an, "RMS level dB", -120)
rms_s_db = num(asig, "RMS level dB", -120)
rms_n = 10 ** (rms_n_db / 20)
rms_s = 10 ** (rms_s_db / 20)
snr_simple = 20*math.log10(rms_s/rms_n) if rms_n > 0 else float("inf")
if rms_s**2 > rms_n**2:
    snr_corr = 10*math.log10((rms_s**2 - rms_n**2)/rms_n**2)
else:
    snr_corr = float("-inf")

# ------------------------------------------------- resolution / ENOB
used_n, total_n = parse_bd(an.get("Bit depth", ""))
used_s, total_s = parse_bd(asig.get("Bit depth", ""))
dr_signal = num(asig, "Dynamic range", 0.0)
dr_noise  = num(an,   "Dynamic range", 0.0)
enob_dr = (dr_signal - 1.76) / 6.02 if dr_signal > 0 else 0.0
enob_snr = (snr_simple - 1.76) / 6.02 if snr_simple != float("inf") else 0.0
peak_s = num(asig, "Peak level dB", -100.0)
peak_n = num(an,   "Peak level dB", -100.0)
clipping = peak_s >= -0.1
nf_signal = num(asig, "Noise floor dB", -120.0)
nf_noise  = num(an,   "Noise floor dB", -120.0)

# bandwidth where signal power exceeds noise power + 6 dB
useful_lo, useful_hi = None, None
for k in range(1, len(freqs)):
    if psd_n[k] <= 0: continue
    snr_bin = 10*math.log10(psd_s[k]/psd_n[k]) if psd_s[k] > 0 else -999
    if snr_bin > 6:
        if useful_lo is None: useful_lo = freqs[k]
        useful_hi = freqs[k]

print("\n[Summary]")
print(f"  Broadband SNR (RMS ratio)       : {snr_simple:>+7.2f} dB")
print(f"  Noise-subtracted SNR            : {snr_corr:>+7.2f} dB")
print(f"  Signal dynamic range            : {dr_signal:>7.2f} dB")
print(f"  Noise floor dynamic range       : {dr_noise:>7.2f} dB")
print(f"  ENOB from DR  (≈ resolution)    : {enob_dr:>7.2f} bits"
      f"  (container: {used_s}/{total_s} bits)" if used_s else f"  ENOB from DR  : {enob_dr:>7.2f} bits")
print(f"  ENOB from SNR (alt. estimate)   : {enob_snr:>7.2f} bits")
print(f"  Signal peak                     : {peak_s:>+7.2f} dBFS"
      f"   {'⚠ CLIPPING' if clipping else ''}")
print(f"  Noise peak                      : {peak_n:>+7.2f} dBFS")
print(f"  Useful bandwidth (per-bin SNR>6): "
      f"{useful_lo or 0:>5.0f} – {useful_hi or 0:.0f} Hz")
print(f"  Spectral rolloff (85% energy)   : {roll85:>5.0f} Hz")
if hum_warn:
    print(f"  ⚠ Mains hum suspected at        : {hum_warn[0]:.1f} Hz ({hum_warn[1]:+.1f} dB/Hz)")

# ------------------------------------------------------------------- grade
def grade():
    score = 0; reasons = []
    if snr_simple >= 40: score += 3; reasons.append("SNR≥40dB")
    elif snr_simple >= 30: score += 2; reasons.append("SNR≥30dB")
    elif snr_simple >= 20: score += 1; reasons.append("SNR≥20dB")
    else: reasons.append(f"SNR={snr_simple:.1f}dB low")
    if not clipping: score += 1; reasons.append("no clip")
    else: reasons.append("CLIPPING!")
    if dr_signal > 0:
        if enob_dr >= 12: score += 2; reasons.append("ENOB≥12")
        elif enob_dr >= 9:  score += 1; reasons.append("ENOB≥9")
        else: reasons.append(f"ENOB={enob_dr:.1f} low")
    if useful_hi and useful_hi >= nyq * 0.7:
        score += 1; reasons.append("wide BW")
    if hum_warn:
        score -= 1; reasons.append("hum")
    if score >= 6: return "★★★★★ EXCELLENT", reasons
    if score >= 4: return "★★★★☆ GOOD", reasons
    if score >= 2: return "★★★☆☆ FAIR", reasons
    if score >= 1: return "★★☆☆☆ POOR", reasons
    return "★☆☆☆☆ VERY POOR", reasons

g, why = grade()
print(f"\n  Overall grade : {g}")
print(f"  Factors       : {', '.join(why)}")
print()
PY
