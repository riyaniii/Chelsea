import glob
import os

NVIDIA_EGL_VENDORS = (
    '/usr/lib/*/GL/nvidia-*/glvnd/egl_vendor.d/10_nvidia.json',
    '/usr/share/glvnd/egl_vendor.d/10_nvidia.json',
)
GPU_OVERRIDES = ('__NV_PRIME_RENDER_OFFLOAD', '__GLX_VENDOR_LIBRARY_NAME', 'DRI_PRIME')


def nvidia_available() -> bool:
    return os.path.exists('/dev/nvidia0') and any(glob.glob(pattern) for pattern in NVIDIA_EGL_VENDORS)


def prefer_nvidia_gpu(settings) -> None:
    if not settings.get_boolean('prefer-discrete-gpu'):
        return
    if any(name in os.environ for name in GPU_OVERRIDES) or not nvidia_available():
        return
    os.environ['__NV_PRIME_RENDER_OFFLOAD'] = '1'
    os.environ['__GLX_VENDOR_LIBRARY_NAME'] = 'nvidia'
    os.environ['__VK_LAYER_NV_optimus'] = 'NVIDIA_only'
