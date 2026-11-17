"""GPU メーター: 複数GPU・ホットプラグ・JSON・欠損値を実機なしで検査。"""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home/private_dot_config/waybar/scripts/executable_gpu_status.py"
CONFIG = ROOT / "home/private_dot_config/waybar/config.tmpl"


class GpuStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.drm = Path(self.tmp.name)
        spec = importlib.util.spec_from_file_location("gpu_status", SCRIPT)
        self.gpu = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.gpu)

    def card(self, number, *, busy=0, temperature=40000, watts=10, connected=False, vendor="0x1002"):
        card = self.drm / f"card{number}"
        device = card / "device"
        hwmon = device / "hwmon/hwmon0"
        hwmon.mkdir(parents=True)
        (device / "vendor").write_text(vendor)
        (device / "gpu_busy_percent").write_text(str(busy))
        (device / "uevent").write_text(f"PCI_SLOT_NAME=0000:0{number}:00.0\n")
        (hwmon / "temp1_input").write_text(str(temperature))
        (hwmon / "power1_average").write_text(str(watts * 1000000))
        connector = card / f"card{number}-HDMI-A-1"
        connector.mkdir()
        (connector / "status").write_text("connected" if connected else "disconnected")
        return card

    def status(self):
        return self.gpu.status(self.drm)

    def test_display_gpu_wins_over_first_igpu(self):
        self.card(0, busy=0, temperature=40000)
        self.card(1, busy=42, temperature=57000, watts=43, connected=True)
        result = self.status()
        self.assertEqual(result["percentage"], 42)
        self.assertIn("card1", result["tooltip"])
        self.assertIn("57", result["tooltip"])
        self.assertIn("43", result["tooltip"])
        self.assertNotIn("40°C", result["tooltip"])

    def test_single_igpu_fallback(self):
        self.card(0, busy=15)
        self.assertEqual(self.status()["percentage"], 15)

    def test_card_numbers_are_not_fixed(self):
        self.card(3, busy=21, connected=True)
        self.assertEqual(self.status()["percentage"], 21)

    def test_hotplug_is_reselected_on_each_poll(self):
        first = self.card(0, busy=3, connected=True)
        second = self.card(1, busy=65)
        self.assertEqual(self.status()["percentage"], 3)
        (first / "card0-HDMI-A-1/status").write_text("disconnected")
        (second / "card1-HDMI-A-1/status").write_text("connected")
        self.assertEqual(self.status()["percentage"], 65)

    def test_missing_optional_sensors_do_not_hide_load(self):
        card = self.card(0, busy=23)
        shutil.rmtree(card / "device/hwmon")
        result = self.status()
        self.assertEqual(result["percentage"], 23)
        self.assertNotIn("Temp:", result["tooltip"])
        self.assertNotIn("Power:", result["tooltip"])

    def test_temperature_and_power_are_from_selected_gpu_only(self):
        self.card(0, temperature=99000, watts=200)
        card = self.card(1, busy=7, connected=True)
        shutil.rmtree(card / "device/hwmon")
        self.assertNotIn("99", self.status()["tooltip"])
        self.assertNotIn("200", self.status()["tooltip"])

    def test_hwmon_reorder_uses_amdgpu_sensor(self):
        card = self.card(0)
        sensor = card / "device/hwmon/hwmon0"
        (sensor / "name").write_text("amdgpu")
        other = card / "device/hwmon/hwmon1"
        other.mkdir()
        (other / "name").write_text("other")
        (other / "temp1_input").write_text("99000")
        self.assertIn("40°C", self.status()["tooltip"])

    def test_missing_or_invalid_load_is_hidden_not_reported_as_zero(self):
        card = self.card(0)
        for value in ("", "bad", "-1", "101"):
            with self.subTest(value=value):
                (card / "device/gpu_busy_percent").write_text(value)
                self.assertIsNone(self.status())
        (card / "device/gpu_busy_percent").unlink()
        self.assertIsNone(self.status())

    def test_empty_drm_and_unsupported_gpu(self):
        self.assertIsNone(self.status())
        self.card(0, vendor="0x8086")
        self.assertIsNone(self.status())

    def test_existing_warning_thresholds(self):
        card = self.card(0)
        for percent, css in ((0, "normal"), (79, "normal"), (80, "warning"), (94, "warning"), (95, "critical"), (100, "critical")):
            with self.subTest(percent=percent):
                (card / "device/gpu_busy_percent").write_text(str(percent))
                self.assertEqual(self.status()["class"], css)

    def test_nvidia_query_is_scoped_to_selected_pci_device(self):
        self.card(0, vendor="0x10de", connected=True)
        with patch.object(self.gpu.subprocess, "check_output", return_value='NVIDIA Test, 35, 51, 25.50\n') as query:
            result = self.status()
        self.assertEqual(result["percentage"], 35)
        self.assertIn("NVIDIA Test", result["tooltip"])
        self.assertIn("--id=0000:00:00.0", query.call_args.args[0])
        self.assertLessEqual(query.call_args.kwargs["timeout"], 3)

    def test_unavailable_optional_nvidia_sensors_keep_load(self):
        self.card(0, vendor="0x10de")
        with patch.object(self.gpu.subprocess, "check_output", return_value='NVIDIA Test, 35, [Not Supported], N/A\n'):
            result = self.status()
        self.assertEqual(result["percentage"], 35)
        self.assertNotIn("Temp:", result["tooltip"])
        self.assertNotIn("Power:", result["tooltip"])

    def test_failed_display_gpu_does_not_silently_show_igpu(self):
        self.card(0, busy=0)
        card = self.card(1, connected=True)
        (card / "device/gpu_busy_percent").write_text("unavailable")
        self.assertIsNone(self.status())

    def test_nvidia_failure_does_not_crash_widget(self):
        self.card(0, vendor="0x10de")
        for error in (FileNotFoundError(), subprocess.CalledProcessError(1, "nvidia-smi"), subprocess.TimeoutExpired("nvidia-smi", 2)):
            with self.subTest(error=type(error).__name__):
                with patch.object(self.gpu.subprocess, "check_output", side_effect=error):
                    self.assertIsNone(self.status())

    def test_amd_display_does_not_query_unrelated_nvidia(self):
        self.card(0, vendor="0x10de")
        self.card(1, connected=True, busy=17)
        with patch.object(self.gpu.subprocess, "check_output") as query:
            self.assertEqual(self.status()["percentage"], 17)
        query.assert_not_called()

    def test_json_encoding_round_trip_for_special_characters(self):
        self.card(0, vendor="0x10de")
        with patch.object(self.gpu.subprocess, "check_output", return_value='"NVIDIA ""Test"" <GPU>", 2, 40, N/A\n'):
            result = self.status()
        encoded = json.dumps(result)
        self.assertEqual(json.loads(encoded), result)
        # Waybar の tooltip は Pango markup。GPU名の記号もエスケープする。
        self.assertIn("&lt;GPU&gt;", result["tooltip"])

    @unittest.skipUnless(shutil.which("chezmoi"), "chezmoi が必要")
    def test_waybar_owns_meter_icons_and_installed_path(self):
        for hostname in ("am5-itx", "fp7-e14"):
            rendered = subprocess.run(
                ["chezmoi", "--source", str(ROOT), "execute-template", "--override-data",
                 json.dumps({"chezmoi": {"hostname": hostname, "os": "linux"}})],
                input=CONFIG.read_text(), capture_output=True, text=True, check=True,
            ).stdout
            config = json.loads("\n".join(line for line in rendered.splitlines() if not line.lstrip().startswith("//")))
            gpu = config["custom/gpu"]
            self.assertEqual(gpu["exec"], "~/.config/waybar/scripts/gpu_status.py")
            self.assertEqual(gpu["return-type"], "json")
            self.assertEqual(gpu["format"], "󰢮 {icon}")
            self.assertEqual(len(gpu["format-icons"]), 8)
            self.assertEqual(gpu["interval"], 3)


if __name__ == "__main__":
    unittest.main()
