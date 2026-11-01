from __future__ import annotations

import sys
from pathlib import Path

pytest_plugins = ["pytest_homeassistant_custom_component"]

sys.path.insert(0, str(Path(__file__).parents[1] / "custom_components"))
