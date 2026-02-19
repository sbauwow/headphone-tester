#!/usr/bin/env python3
"""Headphone Tester - CLI tool to test USB and line-input headphones on Linux."""

import argparse
import sys
import time
import threading

import numpy as np
import sounddevice as sd


output_device = None
input_device = None


def list_devices():
    """List all audio input/output devices."""
    devices = sd.query_devices()
    defaults = sd.default.device  # (input_idx, output_idx)

    print("\n  #  Type     Ch(I/O)  SampleRate  Name")
    print("  " + "-" * 65)

    for i, dev in enumerate(devices):
        in_ch = dev["max_input_channels"]
        out_ch = dev["max_output_channels"]
        rate = int(dev["default_samplerate"])
        name = dev["name"]

        # Determine device type
        if in_ch > 0 and out_ch > 0:
            dtype = "in/out"
        elif in_ch > 0:
            dtype = "input "
        elif out_ch > 0:
            dtype = "output"
        else:
            dtype = "      "

        # Mark defaults and USB
        markers = []
        if i == defaults[0]:
            markers.append("*IN")
        if i == defaults[1]:
            markers.append("*OUT")
        name_lower = name.lower()
        if "usb" in name_lower or "USB" in name:
            markers.append("USB")

        marker_str = f" [{', '.join(markers)}]" if markers else ""

        print(f"  {i:<3} {dtype}   {in_ch}/{out_ch}      {rate:>5}Hz  {name}{marker_str}")

    print()
    if output_device is not None:
        print(f"  Selected output: {output_device}")
    if input_device is not None:
        print(f"  Selected input:  {input_device}")
    print()


def get_samplerate(device=None, kind="output"):
    """Get the default sample rate for a device."""
    dev = device if device is not None else sd.default.device[0 if kind == "input" else 1]
    info = sd.query_devices(dev)
    return int(info["default_samplerate"])


def play_tone(freq=440, duration=2.0):
    """Play a sine wave tone."""
    samplerate = get_samplerate(output_device)
    t = np.linspace(0, duration, int(samplerate * duration), endpoint=False)

    # Apply fade in/out to avoid clicks (10ms)
    fade_samples = int(samplerate * 0.01)
    fade_in = np.linspace(0, 1, fade_samples)
    fade_out = np.linspace(1, 0, fade_samples)

    tone = np.sin(2 * np.pi * freq * t).astype(np.float32)
    tone[:fade_samples] *= fade_in
    tone[-fade_samples:] *= fade_out

    # Stereo: same signal in both channels
    stereo = np.column_stack([tone, tone])

    print(f"  Playing {freq}Hz tone for {duration}s...")
    sd.play(stereo, samplerate=samplerate, device=output_device)
    sd.wait()
    print("  Done.")


def play_channel_test(channel):
    """Play tone in left (0) or right (1) channel only."""
    freq = 440
    duration = 2.0
    samplerate = get_samplerate(output_device)
    t = np.linspace(0, duration, int(samplerate * duration), endpoint=False)

    fade_samples = int(samplerate * 0.01)
    fade_in = np.linspace(0, 1, fade_samples)
    fade_out = np.linspace(1, 0, fade_samples)

    tone = np.sin(2 * np.pi * freq * t).astype(np.float32)
    tone[:fade_samples] *= fade_in
    tone[-fade_samples:] *= fade_out

    stereo = np.zeros((len(t), 2), dtype=np.float32)
    stereo[:, channel] = tone

    label = "LEFT" if channel == 0 else "RIGHT"
    print(f"  Playing {freq}Hz in {label} channel for {duration}s...")
    sd.play(stereo, samplerate=samplerate, device=output_device)
    sd.wait()
    print("  Done.")


def play_sweep(duration=5.0):
    """Logarithmic frequency sweep from 20Hz to 20kHz."""
    samplerate = get_samplerate(output_device)
    n_samples = int(samplerate * duration)
    t = np.linspace(0, duration, n_samples, endpoint=False)

    # Logarithmic sweep: frequency increases exponentially
    f0, f1 = 20.0, 20000.0
    phase = 2 * np.pi * f0 * duration / np.log(f1 / f0) * (np.exp(t / duration * np.log(f1 / f0)) - 1)
    sweep = (0.8 * np.sin(phase)).astype(np.float32)

    # Fade in/out
    fade_samples = int(samplerate * 0.01)
    sweep[:fade_samples] *= np.linspace(0, 1, fade_samples)
    sweep[-fade_samples:] *= np.linspace(1, 0, fade_samples)

    stereo = np.column_stack([sweep, sweep])

    print(f"  Sweeping 20Hz → 20kHz over {duration}s...")
    sd.play(stereo, samplerate=samplerate, device=output_device)
    sd.wait()
    print("  Done.")


def mic_level_meter():
    """Show real-time ASCII VU meter of mic input."""
    samplerate = get_samplerate(input_device, kind="input")
    block_size = 1024
    bar_width = 50

    print("  Mic level meter (Ctrl+C to stop)\n")

    def callback(indata, frames, time_info, status):
        if status:
            print(f"  {status}", file=sys.stderr)
        rms = np.sqrt(np.mean(indata ** 2))
        # Map to dB, clamp to -60..0 range
        db = 20 * np.log10(max(rms, 1e-10))
        db_clamped = max(-60, min(0, db))
        level = int((db_clamped + 60) / 60 * bar_width)

        bar = "█" * level + "░" * (bar_width - level)
        sys.stdout.write(f"\r  [{bar}] {db:+6.1f} dB")
        sys.stdout.flush()

    try:
        with sd.InputStream(device=input_device, channels=1,
                            samplerate=samplerate, blocksize=block_size,
                            callback=callback):
            while True:
                time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n  Stopped.")


def mic_loopback():
    """Pass microphone input through to headphones in real-time."""
    samplerate = get_samplerate(output_device)
    block_size = 256  # Low block size for minimal latency

    print(f"  Loopback: mic → headphones (latency ~{block_size/samplerate*1000:.0f}ms, Ctrl+C to stop)")

    def callback(indata, outdata, frames, time_info, status):
        if status:
            print(f"  {status}", file=sys.stderr)
        # If input is mono and output is stereo, duplicate
        if indata.shape[1] < outdata.shape[1]:
            outdata[:] = np.column_stack([indata[:, 0]] * outdata.shape[1])
        elif indata.shape[1] > outdata.shape[1]:
            outdata[:] = indata[:, :outdata.shape[1]]
        else:
            outdata[:] = indata

    try:
        # Query channel counts
        in_info = sd.query_devices(input_device if input_device is not None else sd.default.device[0])
        out_info = sd.query_devices(output_device if output_device is not None else sd.default.device[1])
        in_ch = min(in_info["max_input_channels"], 2)
        out_ch = min(out_info["max_output_channels"], 2)

        with sd.Stream(device=(input_device, output_device),
                       channels=(in_ch, out_ch),
                       samplerate=samplerate, blocksize=block_size,
                       callback=callback):
            while True:
                time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n  Stopped.")


def select_by_type(device_type):
    """Auto-select input/output devices by type ('usb' or 'line')."""
    global input_device, output_device
    devices = sd.query_devices()
    found_out = None
    found_in = None

    for i, dev in enumerate(devices):
        name_lower = dev["name"].lower()
        is_usb = "usb" in name_lower
        if device_type == "usb" and not is_usb:
            continue
        if device_type == "line" and is_usb:
            continue
        if found_out is None and dev["max_output_channels"] > 0:
            found_out = i
        if found_in is None and dev["max_input_channels"] > 0:
            found_in = i

    if found_out is None and found_in is None:
        print(f"  No {device_type} devices found.")
        return

    if found_out is not None:
        output_device = found_out
        print(f"  Output device set to: {devices[found_out]['name']} (#{found_out})")
    else:
        print(f"  No {device_type} output device found.")

    if found_in is not None:
        input_device = found_in
        print(f"  Input device set to: {devices[found_in]['name']} (#{found_in})")
    else:
        print(f"  No {device_type} input device found.")


def set_device(kind, dev_id):
    """Set input or output device by index."""
    global input_device, output_device
    try:
        idx = int(dev_id)
        info = sd.query_devices(idx)
        if kind == "output" and info["max_output_channels"] == 0:
            print(f"  Error: device {idx} has no output channels.")
            return
        if kind == "input" and info["max_input_channels"] == 0:
            print(f"  Error: device {idx} has no input channels.")
            return
        if kind == "output":
            output_device = idx
        else:
            input_device = idx
        print(f"  {kind.capitalize()} device set to: {info['name']} (#{idx})")
    except (ValueError, sd.PortAudioError) as e:
        print(f"  Error: {e}")


def print_help():
    print("""
  Commands:
    devices          List audio devices
    tone [freq] [s]  Play test tone (default: 440Hz, 2s)
    left             Play tone in left channel only
    right            Play tone in right channel only
    sweep [s]        Frequency sweep 20Hz→20kHz (default: 5s)
    mic              Show mic level meter (Ctrl+C to stop)
    loopback         Mic→headphone passthrough (Ctrl+C to stop)
    output [id]      Set output device
    input [id]       Set input device
    use <line|usb>   Select devices by type
    help             Show this help
    quit             Exit
""")


def main():
    parser = argparse.ArgumentParser(description="Headphone Tester")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--usb", action="store_true", help="Start with USB devices selected")
    group.add_argument("--line", action="store_true", help="Start with line (non-USB) devices selected")
    cli_args = parser.parse_args()

    print("\n  === Headphone Tester ===")

    if cli_args.usb:
        select_by_type("usb")
    elif cli_args.line:
        select_by_type("line")

    print_help()

    while True:
        try:
            line = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        try:
            if cmd == "devices":
                list_devices()
            elif cmd == "tone":
                freq = float(args[0]) if len(args) > 0 else 440
                dur = float(args[1]) if len(args) > 1 else 2.0
                play_tone(freq, dur)
            elif cmd == "left":
                play_channel_test(0)
            elif cmd == "right":
                play_channel_test(1)
            elif cmd == "sweep":
                dur = float(args[0]) if len(args) > 0 else 5.0
                play_sweep(dur)
            elif cmd == "mic":
                mic_level_meter()
            elif cmd == "loopback":
                mic_loopback()
            elif cmd == "output":
                if not args:
                    print("  Usage: output <device_id>")
                else:
                    set_device("output", args[0])
            elif cmd == "input":
                if not args:
                    print("  Usage: input <device_id>")
                else:
                    set_device("input", args[0])
            elif cmd == "use":
                if not args or args[0].lower() not in ("usb", "line"):
                    print("  Usage: use <line|usb>")
                else:
                    select_by_type(args[0].lower())
            elif cmd in ("help", "?"):
                print_help()
            elif cmd in ("quit", "exit", "q"):
                break
            else:
                print(f"  Unknown command: {cmd}. Type 'help' for commands.")
        except sd.PortAudioError as e:
            print(f"  Audio error: {e}")
        except Exception as e:
            print(f"  Error: {e}")


if __name__ == "__main__":
    main()
