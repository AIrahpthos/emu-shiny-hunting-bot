import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from capture_linux import Desktop, overlaps, require_x11
from install_capture import safe_extract

class PiAdapterTests(unittest.TestCase):
    def test_overlap_checks(self):
        self.assertTrue(overlaps((10,10,320,240),(100,100,20,20)))
        self.assertFalse(overlaps((10,10,320,240),(330,10,20,20)))
        self.assertFalse(overlaps((10,10,320,240),(0,300,100,100)))
    def test_wayland_rejected_with_instructions(self):
        with patch.dict(os.environ,{'XDG_SESSION_TYPE':'wayland','DISPLAY':':0'},clear=True):
            with self.assertRaisesRegex(RuntimeError,'X11'): require_x11()
    def test_desktop_display_required(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(RuntimeError,'Pi desktop'): require_x11()
        with patch.dict(os.environ,{'XDG_SESSION_TYPE':'x11','DISPLAY':':0'},clear=True): require_x11()
    def test_client_to_root_coordinates_and_frame_bounds(self):
        desktop=Desktop.__new__(Desktop)
        window=Mock(); window.get_geometry.return_value=SimpleNamespace(width=320,height=240)
        window.get_full_property.return_value=SimpleNamespace(value=[2,2,24,2])
        desktop.window=Mock(return_value=window)
        desktop.root=Mock(); desktop.root.translate_coords.return_value=SimpleNamespace(x=120,y=80)
        desktop.X=SimpleNamespace(AnyPropertyType=0)
        desktop.atoms={'_NET_FRAME_EXTENTS':1}
        self.assertEqual(desktop.bounds(42),(120,80,320,240))
        desktop.root.translate_coords.assert_called_with(window,0,0)
        self.assertEqual(desktop.bounds(42,frame=True),(118,56,324,266))
    def test_verified_archive_extracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); archive=root/'a.zip'
            with zipfile.ZipFile(archive,'w') as z: z.writestr('viewer/cc3dsfs',b'placeholder')
            safe_extract(archive,root/'destination')
            self.assertEqual((root/'destination/viewer/cc3dsfs').read_bytes(),b'placeholder')
    def test_archive_paths_cannot_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); archive=root/'a.zip'
            with zipfile.ZipFile(archive,'w') as z: z.writestr('../escaped',b'bad')
            with self.assertRaises(ValueError): safe_extract(archive,root/'destination')
            self.assertFalse((root/'escaped').exists())

if __name__=='__main__': unittest.main()
