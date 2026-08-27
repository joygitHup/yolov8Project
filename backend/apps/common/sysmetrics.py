import shutil
import subprocess

try:
    import psutil
except ImportError:
    psutil = None

_cpu_primed = False


def collect_system_metrics():
    global _cpu_primed
    cpu = 0.0
    memory = 0.0
    if psutil:
        if not _cpu_primed:
            psutil.cpu_percent(interval=None)
            _cpu_primed = True
        cpu = float(psutil.cpu_percent(interval=0.2))
        memory = float(psutil.virtual_memory().percent)
    return {
        "cpu": f"{cpu:.1f}",
        "memory": f"{memory:.1f}",
        "gpu": f"{_gpu_percent():.1f}",
    }


def _gpu_percent():
    smi = shutil.which("nvidia-smi")
    if not smi:
        return 0.0
    try:
        out = subprocess.check_output(
            [smi, "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            timeout=1.5,
            stderr=subprocess.DEVNULL,
        )
        values = [float(line.strip()) for line in out.decode("utf-8", "ignore").splitlines() if line.strip()]
        return sum(values) / len(values) if values else 0.0
    except Exception:
        return 0.0
