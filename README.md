# Headphone Tester

A terminal tool to test USB and line-input headphones on Linux. Plays test tones, checks left/right channels, runs frequency sweeps, and tests microphone input -- all from the CLI.

Uses PortAudio under the hood, so it works with PipeWire, PulseAudio, and ALSA.

## Requirements

- Python 3.10+
- Linux with PortAudio installed (usually already present with PipeWire/PulseAudio)
- A venv is included in the project -- no system-wide installs needed

## Quick Start

```bash
~/headphone-tester/.venv/bin/python ~/headphone-tester/headphone-tester.py
```

Or add an alias to your shell rc:

```bash
alias hptest='~/headphone-tester/.venv/bin/python ~/headphone-tester/headphone-tester.py'
```

## How It Works

When you launch the tool, you get an interactive prompt. You type commands, it does audio things. Ctrl+C exits continuous commands (mic meter, loopback). Type `quit` to exit.

### Step 1: See Your Devices

```
> devices

  #  Type     Ch(I/O)  SampleRate  Name
  -----------------------------------------------------------------
  0   in/out   2/2      48000Hz  HDA Intel PCH: SN6140 Analog (hw:0,0)
  1   output   0/8      44100Hz  HDA Intel PCH: HDMI 0 (hw:0,3)
  14  in/out   64/64    44100Hz  pipewire
  15  in/out   32/32    44100Hz  pulse
  20  in/out   64/64    44100Hz  default [*IN, *OUT]
```

What the columns mean:

| Column | Meaning |
|--------|---------|
| `#` | Device index -- use this number with `output` and `input` commands |
| `Type` | `input` = mic only, `output` = speakers only, `in/out` = both |
| `Ch(I/O)` | Number of input/output channels (e.g. `2/2` = stereo in + stereo out) |
| `SampleRate` | Device's default sample rate |
| `Name` | Device name from the system |

Markers in brackets:
- `*IN` = system default input device
- `*OUT` = system default output device
- `USB` = detected as a USB audio device

### Step 2: Select Your Headphones

By default, audio goes to whatever your system default is. If you plugged in USB headphones, find their device number from `devices` and select them:

```
> output 3
  Output device set to: USB Audio Device (hw:2,0) (#3)

> input 3
  Input device set to: USB Audio Device (hw:2,0) (#3)
```

- `output <id>` sets where sound plays TO (your headphones)
- `input <id>` sets where sound records FROM (your headphone mic)

You can set them independently -- e.g. play through USB headphones but record from the laptop mic.

### Step 3: Test Playback

#### Basic tone

```
> tone
  Playing 440Hz tone for 2s...
  Done.
```

You should hear a clean A4 note (440Hz) in both ears. If you hear nothing, your output device is wrong -- try a different one with `output <id>`.

You can customize frequency and duration:

```
> tone 1000 3
  Playing 1000Hz tone for 3s...
```

#### Left/Right channel test

```
> left
  Playing 440Hz in LEFT channel for 2s...

> right
  Playing 440Hz in RIGHT channel for 2s...
```

You should hear the tone in only one ear each time. This verifies:
- Both drivers work
- Left and right aren't swapped
- Stereo separation is working (no bleed between channels)

#### Frequency sweep

```
> sweep
  Sweeping 20Hz → 20kHz over 5s...
```

Plays a tone that starts at 20Hz (deep bass) and smoothly rises to 20kHz (upper limit of human hearing). The sweep is logarithmic, meaning it spends equal time per octave -- the way human hearing perceives pitch.

Use this to check:
- Bass response (do you feel/hear the low rumble at the start?)
- Treble response (does the high end stay audible or cut out early?)
- Any rattling or distortion at specific frequencies

You can change the duration: `sweep 10` for a slower 10-second sweep.

### Step 4: Test Microphone

#### Level meter

```
> mic
  Mic level meter (Ctrl+C to stop)

  [██████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] -35.2 dB
```

Shows a real-time bar that bounces with your voice/sound. The dB value on the right is the signal level:

| dB range | What it means |
|----------|---------------|
| -60 to -40 | Silence / very quiet background |
| -40 to -20 | Normal speaking voice |
| -20 to -10 | Loud speech / close to mic |
| -10 to 0 | Very loud, may clip |

If the bar doesn't move at all, your input device is wrong or the mic is muted at the system level.

Press **Ctrl+C** to stop.

#### Loopback test

```
> loopback
  Loopback: mic → headphones (latency ~6ms, Ctrl+C to stop)
```

Routes your microphone directly to your headphones in real-time. You hear yourself as you speak. This tests:

- Mic is actually picking up audio
- Headphone output works simultaneously with mic input
- Approximate latency (the delay between speaking and hearing yourself)

The block size is 256 samples at 44100Hz, giving ~6ms of buffer latency. Actual end-to-end latency depends on your audio stack (PipeWire is typically the lowest).

Press **Ctrl+C** to stop.

## Command Reference

| Command | Args | Description |
|---------|------|-------------|
| `devices` | | List all audio devices |
| `tone` | `[freq] [seconds]` | Play sine wave (default: 440Hz, 2s) |
| `left` | | Tone in left channel only |
| `right` | | Tone in right channel only |
| `sweep` | `[seconds]` | Frequency sweep 20Hz to 20kHz (default: 5s) |
| `mic` | | Real-time mic level meter |
| `loopback` | | Mic-to-headphone passthrough |
| `output` | `<device_id>` | Set output device by index |
| `input` | `<device_id>` | Set input device by index |
| `help` | | Show command list |
| `quit` | | Exit (`q` and `exit` also work) |

## Troubleshooting

**No sound at all**
- Run `devices` and check which device has `[*OUT]` -- is it the right one?
- Try `output 15` (pulse) or `output 14` (pipewire) as these virtual devices follow your system settings
- Check system volume isn't muted: `pactl get-sink-mute @DEFAULT_SINK@`

**Mic not working**
- Run `devices` and set `input` to the correct device
- Check mic isn't muted: `pactl get-source-mute @DEFAULT_SOURCE@`
- Some USB headsets expose mic on a different device index than the speakers

**"PortAudio error"**
- Usually means the device is busy or doesn't support the requested format
- Try a different device, or try `output 20` (the `default` device)

**USB headphones not showing up**
- Unplug and replug, then run `devices` again
- Check `lsusb` to verify the OS sees the device
- Check `dmesg | tail` for USB audio errors
