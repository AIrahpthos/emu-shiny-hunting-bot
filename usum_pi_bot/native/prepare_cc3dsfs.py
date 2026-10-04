"""Add a fail-closed, direct-frame mode to pinned cc3dsfs source."""
from pathlib import Path
import shutil
import sys

def replace_once(path, old, new):
    source=path.read_text()
    if source.count(old)!=1: raise RuntimeError(f'Unexpected upstream source: {path}')
    path.write_text(source.replace(old,new))

root=Path(sys.argv[1])
shutil.copy2(Path(__file__).with_name('shiny_headless.hpp'),root/'source/shiny_headless.hpp')
p=root/'source/cc3dsfs.cpp'
replace_once(p,'static int mainVideoOutputCall(', '#include "shiny_headless.hpp"\n\nstatic int mainVideoOutputCall(')
replace_once(p,'\tint ret_val = mainVideoOutputCall(&audio_data, capture_data, override_data, &can_do_output);',
             '\tint ret_val = std::getenv("SHINY_FRAME_FD") ? shiny_headless(capture_data) : mainVideoOutputCall(&audio_data, capture_data, override_data, &can_do_output);')
replace_once(root/'source/devicecapture.cpp','\tupdate_connected_3ds_ds(frontend_data, capture_data->status.device, devices_list[chosen_device]);',
             '\tif(frontend_data) update_connected_3ds_ds(frontend_data, capture_data->status.device, devices_list[chosen_device]);')
# Pin the SFML snapshot used by this bridge, rather than upstream's moving master.
replace_once(root/'CMakeLists.txt','https://github.com/SFML/SFML/archive/refs/heads/master.zip',
             'https://github.com/SFML/SFML/archive/2124d5fe87412ac1cf8e20de282502a75039efcf.zip')

replace_once(root/'CMakeLists.txt','GIT_TAG main','GIT_TAG bea6567b63796ab27c1c33257d230284fb2d8316')
