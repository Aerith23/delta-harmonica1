"""Application-owned UI smoke test; no recording or playback is performed."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from app import App
from recorder import OutputDevice
from transcription import ConversionCancelled

with patch('app.list_outputs', return_value=[OutputDevice(0, 'Test Output', 2, 48000, True)]):
    ui = App()
    try:
        ui.update()
        ui.update_idletasks()
        for widget in [ui.table, ui.convert_btn, ui.cancel_btn, ui.progress]:
            assert widget.winfo_height() > 1, (widget, widget.winfo_geometry())
            assert widget.winfo_rooty() + widget.winfo_height() <= ui.winfo_rooty() + ui.winfo_height()
        # Real rows must be loaded, and their pixels must belong to the table,
        # not an overlapping sibling frame. Dimensions alone missed this bug.
        expected = [p for p in ui.folder.glob('*.wav') if not p.name.endswith('.partial.wav')]
        assert len(ui.table.get_children()) == min(len(expected), 100)
        assert ui.table.master is ui.nametowidget(ui.table.winfo_parent())
        assert ui.table.master == ui.table.pack_info()['in']
        if expected:
            first = ui.table.get_children()[0]
            box = ui.table.bbox(first)
            assert box, 'First recording is not visible'
            point_x = ui.table.winfo_rootx() + 10
            point_y = ui.table.winfo_rooty() + box[1] + box[3] // 2
            assert ui.winfo_containing(point_x, point_y) is ui.table, 'Recording list is covered'
            assert ui.table.item(first, 'values')[0] == ui.files[0].name
        assert str(len(ui.files)) in ui.file_status.get()
        print('RECORDING_LIST_VISIBLE:', len(ui.files))
        ui.withdraw()
        end = time.monotonic() + 2
        while ui.loading and time.monotonic() < end:
            ui.update(); time.sleep(0.02)
        assert not ui.loading
        ui.table.delete(*ui.table.get_children())
        ui.files = [Path('test.wav')]
        ui.table.insert('', 'end', iid='0', values=('test.wav', '00:03', '0.1 MB'))
        ui.table.selection_set('0')
        with patch('app.convert_recording', return_value=dict(path='test.json', notes=3, seconds=3, raw_notes=3)):
            ui.convert_selected()
            assert ui.converting and str(ui.convert_btn.cget('state')) == 'disabled'
            end = time.monotonic() + 3
            while ui.converting and time.monotonic() < end:
                ui.update(); time.sleep(0.02)
            assert not ui.converting
            assert ui.progress['value'] == 100
            assert str(ui.convert_btn.cget('state')) == 'normal'
            assert '3' in ui.conversion_text.get()
        def wait_for_cancel(source, destination, monophonic, cancel, progress):
            cancel.wait(2)
            raise ConversionCancelled()
        with patch('app.convert_recording', side_effect=wait_for_cancel):
            ui.convert_selected()
            ui.cancel_conversion()
            end = time.monotonic() + 3
            while ui.converting and time.monotonic() < end:
                ui.update(); time.sleep(0.02)
            assert not ui.converting and '取消' in ui.conversion_text.get()
        print('UI_LAYOUT_AND_CONVERSION_STATES_OK')
    finally:
        ui.destroy()
