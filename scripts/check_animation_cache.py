"""GUI allocation stability during repeated resize/flip; not an FPS benchmark."""
import gc
import json
from pathlib import Path
import sys
import tempfile
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psutil
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from app.main import CompanionController
from app.core.config import SettingsStore


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    process = psutil.Process()
    samples = []
    tracemalloc.start()
    with tempfile.TemporaryDirectory() as directory:
        controller = CompanionController(app, SettingsStore(Path(directory)))
        controller.start()
        try:
            count = 0
            for iterations in (24, *([96] * 10)):
                for i in range(iterations):
                    controller.overlay.set_character_scale((.5, 2, 1, 1.5, .75, 1.25)[i % 6])
                    controller.overlay.set_flipped(bool(i % 2))
                    app.processEvents()
                    count += 1
                controller.overlay.set_character_scale(1)
                controller.overlay.set_flipped(False)
                QTest.qWait(100)
                gc.collect()
                memory = process.memory_info()
                samples.append({'resize_flip_pairs': count, 'gui_private_mib': memory.private / 2**20,
                                'gui_resident_mib': memory.rss / 2**20, 'gui_handles': process.num_handles(),
                                'python_traced_mib': tracemalloc.get_traced_memory()[0] / 2**20,
                                'individual_layer_bytes': sum(c[2].sizeInBytes() for c in controller.renderer._cache),
                                'cached_layers': len(controller.renderer._cache),
                                'cached_groups': len(controller.renderer._draw_groups)})
        finally:
            controller.close()
        assert not controller.overlay.animation.timer.isActive()
    report = {'scenario': '984 resize/flip pairs with tracemalloc; return to 100% at each checkpoint',
              'scope': 'GUI process only; relative allocation check, not total application memory',
              'animation_timer_stopped': True, 'samples': samples}
    output = Path('.runtime/phase3-interactions.json')
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
