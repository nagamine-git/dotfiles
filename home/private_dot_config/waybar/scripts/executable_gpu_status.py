#!/usr/bin/env python3
"""Waybar GPU status. stdlib handles JSON/CSV; Waybar draws the meter."""
import csv
from html import escape
import json
from pathlib import Path
import subprocess


def read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def number(value):
    try:
        return float(value)
    except ValueError:
        return None


def sample(card):
    device = card / "device"
    vendor = read(device / "vendor")
    pci = dict(line.split("=", 1) for line in read(device / "uevent").splitlines() if "=" in line).get("PCI_SLOT_NAME", "")
    name, temperature, power = f"AMD {card.name} ({pci})", None, None
    if vendor == "0x1002":
        utilization = number(read(device / "gpu_busy_percent"))
        sensors = sorted((device / "hwmon").glob("hwmon*"))
        sensor = next((s for s in sensors if read(s / "name") == "amdgpu"), next(iter(sensors), None))
        if sensor is not None:
            temperature = number(read(sensor / "temp1_input"))
            power = number(read(sensor / "power1_average"))
            if power is None:
                power = number(read(sensor / "power1_input"))
            temperature = temperature / 1000 if temperature is not None else None
            power = power / 1000000 if power is not None else None
    elif vendor == "0x10de" and pci:
        output = subprocess.check_output(
            ["nvidia-smi", f"--id={pci}", "--query-gpu=name,utilization.gpu,temperature.gpu,power.draw",
             "--format=csv,noheader,nounits"], text=True, stderr=subprocess.DEVNULL, timeout=2,
        )
        name, utilization, temperature, power = next(csv.reader(output.splitlines(), skipinitialspace=True))
        utilization, temperature, power = map(number, (utilization, temperature, power))
    else:
        return None
    if utilization is None or not 0 <= utilization <= 100:
        return None
    tooltip = [escape(name), f"GPU: {utilization:g}%"]
    if temperature is not None:
        tooltip.append(f"Temp: {temperature:g}°C")
    if power is not None:
        tooltip.append(f"Power: {power:g}W")
    return {"text": "GPU", "percentage": int(utilization), "tooltip": "\n".join(tooltip),
            "class": "critical" if utilization >= 95 else "warning" if utilization >= 80 else "normal"}


def status(drm=Path("/sys/class/drm")):
    cards = [card for card in drm.glob("card*") if card.name[4:].isdigit()
             and read(card / "device/vendor") in ("0x1002", "0x10de")]
    # A connected display takes precedence over card numbers, including while DPMS is off.
    def priority(card):
        connected = any(read(connector / "status") == "connected" for connector in card.glob(f"{card.name}-*"))
        return (not connected, read(card / "device/boot_vga") != "1", int(card.name[4:]))

    if not cards:
        return None
    try:
        return sample(min(cards, key=priority))
    except (OSError, ValueError, StopIteration, subprocess.SubprocessError):
        return None  # Do not disguise a failed display GPU as an idle iGPU.


if __name__ == "__main__":
    result = status()
    if result is not None:
        print(json.dumps(result, ensure_ascii=False))
