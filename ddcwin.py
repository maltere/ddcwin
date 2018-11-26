from ctypes import windll, byref, Structure, WinError, POINTER, WINFUNCTYPE
from ctypes.wintypes import BOOL, HMONITOR, HDC, RECT, LPARAM, DWORD, BYTE, WCHAR, HANDLE

from time import sleep
from datetime import datetime, timedelta
from enum import IntEnum


_MONITORENUMPROC = WINFUNCTYPE(BOOL, HMONITOR, HDC, POINTER(RECT), LPARAM)

VCP_BRIGHTNESS_BYTE_CODE = 0x10
VCP_INPUT_BYTE_CODE = 0x60


class DELL_DISPLAY(IntEnum):
    DP = 15
    mDP = 16
    HDMI1 = 17
    HDMI2 = 18


class _PHYSICAL_MONITOR(Structure):
    _fields_ = [('handle', HANDLE),
                ('description', WCHAR * 128)]


def get_displays():
    def callback(hmonitor, hdc, lprect, lparam):
        monitors.append(HMONITOR(hmonitor))
        return True

    monitors = []
    if not windll.user32.EnumDisplayMonitors(None, None, _MONITORENUMPROC(callback), None):
        raise WinError('EnumDisplayMonitors failed')
    return monitors


def open_handle(monitor):
    count = DWORD()
    if not windll.dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(monitor, byref(count)):
        raise WinError()
    # Get physical monitor handles
    physical_array = (_PHYSICAL_MONITOR * count.value)()
    if not windll.dxva2.GetPhysicalMonitorsFromHMONITOR(monitor, count.value, physical_array):
        raise WinError()
    for physical in physical_array:
        return physical.handle


def close_handle(handle):
    if not windll.dxva2.DestroyPhysicalMonitor(handle):
        raise WinError()


def _iter_physical_monitors(close_handles=True):
    """Iterates physical monitors.

    The handles are closed automatically whenever the iterator is advanced.
    This means that the iterator should always be fully exhausted!

    If you want to keep handles e.g. because you need to store all of them and
    use them later, set `close_handles` to False and close them manually."""

    def callback(hmonitor, hdc, lprect, lparam):
        monitors.append(HMONITOR(hmonitor))
        return True

    monitors = []
    if not windll.user32.EnumDisplayMonitors(None, None, _MONITORENUMPROC(callback), None):
        raise WinError('EnumDisplayMonitors failed')

    for monitor in monitors:
        # Get physical monitor count
        count = DWORD()
        if not windll.dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(monitor, byref(count)):
            raise WinError()
        # Get physical monitor handles
        physical_array = (_PHYSICAL_MONITOR * count.value)()
        if not windll.dxva2.GetPhysicalMonitorsFromHMONITOR(monitor, count.value, physical_array):
            raise WinError()
        for physical in physical_array:
            yield physical.handle
            if close_handles:
                if not windll.dxva2.DestroyPhysicalMonitor(physical.handle):
                    raise WinError()


vcp_timeout_dict = {}
VCP_TIMEOUT = 5


def set_vcp_feature(monitor, code, value):
    """Sends a DDC command to the specified monitor.

    See this link for a list of commands:
    ftp://ftp.cis.nctu.edu.tw/pub/csie/Software/X11/private/VeSaSpEcS/VESA_Document_Center_Monitor_Interface/mccsV3.pdf
    """
    timeout = vcp_timeout_dict.get(monitor, None)

    if timeout and datetime.now() - timeout < timedelta(seconds=0):
        sleep(VCP_TIMEOUT)

    vcp_timeout_dict[monitor] = datetime.now() + timedelta(seconds=VCP_TIMEOUT)

    if not windll.dxva2.SetVCPFeature(HANDLE(monitor), BYTE(code), DWORD(value)):
        raise WinError()


def get_vcp_feature(monitor, code):
    resp1 = DWORD()
    resp2 = DWORD()
    if not windll.dxva2.GetVCPFeatureAndVCPFeatureReply(HANDLE(monitor), BYTE(code), None, byref(resp1), byref(resp2)):
        raise WinError()
    else:
        return resp1, resp2


def set_brightness(handle, val):
    if val == get_brightness(handle):
        return
    elif val > get_max_brightness(handle):
        raise ValueError('Value is over max.')
    set_vcp_feature(handle, VCP_BRIGHTNESS_BYTE_CODE, val)


max_value_brightness = {}


def get_brightness(handle):
    resp = get_vcp_feature(handle, VCP_BRIGHTNESS_BYTE_CODE)
    max_value_brightness[handle] = resp[1].value
    return resp[0].value


def get_max_brightness(handle):
    maximum = max_value_brightness.get(handle, None)
    if maximum is None:
        get_brightness(handle)
        maximum = max_value_brightness.get(handle, None)
    if maximum is None:
        raise ValueError('This should be set right now.')
    return maximum


def set_input_source(handle, source):
    if source != get_input_source(handle):
        return set_vcp_feature(handle, VCP_INPUT_BYTE_CODE, source)


def get_input_source(handle):
    return DELL_DISPLAY(get_vcp_feature(handle, VCP_INPUT_BYTE_CODE)[0].value)


if __name__ == "__main__":
    # Switch to SOFT-OFF, wait for the user to press return and then back to ON
    # for handle in _iter_physical_monitors():
    #     # set_vcp_feature(handle, 0x10, 50)
    #     # set_vcp_feature(handle, 0xd6, 0x01)
    #     print(get_vcp_feature(handle, 0x10))
    handles = []
    for display in get_displays():
        handles.append(open_handle(display))

    for handle in handles:
        set_input_source(handle, DELL_DISPLAY.HDMI1)

    sleep(10)

    for handle in handles:
        set_input_source(handle, DELL_DISPLAY.mDP)

    for handle in handles:
        close_handle(handle)

