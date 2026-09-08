import logging
import subprocess
import threading
import time

from apps.streaming.ffmpeg import (
    build_restream_cmd,
    camera_hls_dir,
    find_ffmpeg,
    hls_url as local_hls_url,
    playlist_path,
    popen_kwargs,
)
from apps.streaming import mediamtx as mtx

logger = logging.getLogger("streaming")


class StreamState:
    def __init__(self, camera_id):
        self.camera_id = int(camera_id)
        self.status = "idle"  # idle | starting | running | error
        self.mode = None  # mediamtx | rtsp | file | demo
        self.pid = None
        self.error = ""
        self.started_at = None
        self.process = None
        self.source_key = None
        self.alias_of = None
        self.mtx_path = None
        self.hls_url = None
        self.lock = threading.RLock()


class StreamManager:
    def __init__(self):
        self._states = {}
        self._lock = threading.Lock()
        self._start_sem = threading.Semaphore(2)
        self._publishers = {}  # mtx_path -> Popen (restream camera RTSP to MTX)
        self._publisher_src = {}  # mtx_path -> source rtsp

    def _state(self, camera_id):
        cid = int(camera_id)
        with self._lock:
            if cid not in self._states:
                self._states[cid] = StreamState(cid)
            return self._states[cid]

    def _find_shared(self, source_key, exclude_id=None):
        if not source_key:
            return None
        with self._lock:
            items = list(self._states.items())
        for cid, state in items:
            if exclude_id is not None and cid == int(exclude_id):
                continue
            with state.lock:
                if (
                    state.status == "running"
                    and state.source_key == source_key
                    and state.alias_of is None
                    and state.hls_url
                ):
                    return cid
        return None

    def _apply_alias(self, state, shared_id, source_key):
        owner = self._state(shared_id)
        with owner.lock:
            hls = owner.hls_url
            mode = owner.mode
            path = owner.mtx_path
            ready = bool(hls)
        with state.lock:
            if state.process and state.process.poll() is None:
                self._kill_proc(state.process)
            state.process = None
            state.pid = None
            state.alias_of = shared_id
            state.source_key = source_key
            state.mode = mode
            state.mtx_path = path
            state.hls_url = hls
            state.status = "running" if ready else "starting"
            state.error = ""
            state.started_at = time.time()
        logger.info("stream camera=%s alias_of=%s key=%s", state.camera_id, shared_id, source_key)
        return self.status(state.camera_id)

    def status(self, camera_id):
        from apps.common import rdb
        from apps.common.process import is_runtime_process

        cid = int(camera_id)
        shared = rdb.get_stream_health(cid)
        if not is_runtime_process():
            return self._status_from_shared(cid, shared)

        state = self._state(cid)
        with state.lock:
            alias = state.alias_of
            mode = state.mode
            hls = state.hls_url
            path = state.mtx_path
            status = state.status
            error = state.error or ""
            pid = state.pid
            started = state.started_at

        if not path:
            try:
                from apps.cameras.models import Camera

                cam = Camera.objects.filter(pk=cid).only("id", "rtsp").first()
                if cam:
                    path = self._mtx_path_for(cam)
            except Exception:
                path = None
        ready = False
        if path and mtx.hls_port_open(timeout=0.2):
            ready = bool(mtx.hls_ready(path, timeout=0.45, check_port=False))
        if ready:
            hls = hls or mtx.mtx_hls_url(path)
            mode = mode or "mediamtx"
            status = "running"
            error = ""
        elif status == "running":
            status = "starting"
        extras = self._runtime_health_extras(cid)
        payload = {
            "cameraId": cid,
            "streamStatus": status,
            "streamMode": mode,
            "hlsUrl": hls or (mtx.mtx_hls_url(path) if path else None),
            "playlistReady": ready,
            "hlsReady": ready,
            "pid": pid,
            "error": error,
            "startedAt": started,
            "ffmpeg": bool(find_ffmpeg()),
            "aliasOf": alias,
            "mtxPath": path,
            "status": status,
            "mode": mode,
            **extras,
        }
        rdb.put_stream_health(cid, payload)
        return payload

    def _runtime_health_extras(self, camera_id: int) -> dict:
        cid = int(camera_id)
        extras = {"armed": False, "inferActive": False, "hasLastFrame": False, "lastFrameAt": None}
        try:
            from apps.cameras.models import Camera
            from apps.common import rdb
            from apps.inference.runtime import get_latest_frame
            from apps.inference.strategy import should_infer

            cam = Camera.objects.filter(pk=cid).first()
            if cam is not None:
                extras["armed"] = bool(should_infer(cam))
            frame = get_latest_frame(cid) or {}
            extras["inferActive"] = bool(frame.get("inferActive"))
            extras["lastFrameAt"] = frame.get("timestamp")
            extras["hasLastFrame"] = bool(extras["lastFrameAt"] or rdb.has_last_frame_jpeg(cid))
        except Exception:
            logger.debug("runtime health extras skipped camera=%s", cid)
        return extras

    @staticmethod
    def _status_from_shared(camera_id: int, shared: dict | None) -> dict:
        data = dict(shared or {})
        path = data.get("mtxPath")
        ready = bool(data.get("hlsReady"))
        hls = data.get("hlsUrl")
        status = data.get("streamStatus") or ("running" if ready else "idle")
        return {
            "cameraId": int(camera_id),
            "streamStatus": status,
            "streamMode": data.get("streamMode") or ("mediamtx" if path else None),
            "hlsUrl": hls,
            "playlistReady": ready,
            "hlsReady": ready,
            "pid": data.get("pid"),
            "error": data.get("error") or "",
            "startedAt": data.get("startedAt") or data.get("ts"),
            "ffmpeg": bool(find_ffmpeg()),
            "aliasOf": data.get("aliasOf"),
            "mtxPath": path,
            "status": status,
            "mode": data.get("streamMode"),
            "armed": bool(data.get("armed")),
            "inferActive": bool(data.get("inferActive")),
            "hasLastFrame": bool(data.get("hasLastFrame")),
            "lastFrameAt": data.get("lastFrameAt"),
        }

    def _probe_mtx(self, camera_id: int, path: str | None = None) -> dict | None:
        del camera_id, path
        return None

    def _mtx_path_for(self, camera) -> str:
        rtsp = (getattr(camera, "rtsp", None) or "").strip()
        cid = getattr(camera, "id", None)
        return mtx.path_from_rtsp(rtsp, cid)

    def start(self, camera, prefer_rtsp=True):
        from apps.common.process import is_runtime_process

        path = self._mtx_path_for(camera)
        if not path:
            raise RuntimeError("未配置 RTSP，无法启动预览流")

        if not is_runtime_process():
            from apps.common import rdb

            rdb.put_stream_cmd(int(camera.id), "start")
            rdb.put_stream_health(
                int(camera.id),
                {
                    "hlsReady": False,
                    "hlsUrl": mtx.mtx_hls_url(path),
                    "mtxPath": path,
                    "streamStatus": "starting",
                    "streamMode": "mediamtx",
                    "error": "",
                },
            )
            return self.status(camera.id)

        state = self._state(camera.id)
        if prefer_rtsp and mtx.hls_port_open() and mtx.rtsp_port_open():
            source_key = f"mtx:{path}"
            shared_id = self._find_shared(source_key, exclude_id=camera.id)
            if shared_id is not None:
                return self._apply_alias(state, shared_id, source_key)

            with state.lock:
                if (
                    state.status == "running"
                    and state.mode == "mediamtx"
                    and state.mtx_path == path
                    and state.hls_url
                    and not state.alias_of
                ):
                    if mtx.hls_ready(path, timeout=0.8):
                        self._after_ready(camera, path)
                        return self.status(camera.id)
                state.status = "starting"
                state.error = ""
                state.started_at = time.time()
                state.alias_of = None
                state.source_key = source_key
                state.mtx_path = path
                state.mode = "mediamtx"
                state.hls_url = mtx.mtx_hls_url(path)

            ok = self._ensure_camera_stream(camera, wait=12.0)
            if ok:
                with state.lock:
                    state.status = "running"
                    state.mode = "mediamtx"
                    state.mtx_path = path
                    state.hls_url = mtx.mtx_hls_url(path)
                    state.error = ""
                    state.process = None
                    state.pid = None
                self._after_ready(camera, path)
                logger.info("stream camera=%s mode=mediamtx path=%s", camera.id, path)
                return self.status(camera.id)

            with state.lock:
                state.status = "error"
                state.error = state.error or "预览流尚未就绪（等待摄像头 RTSP / MediaMTX HLS）"
            logger.warning("MediaMTX HLS not ready for path=%s camera=%s", path, camera.id)
            return self.status(camera.id)

        return self._start_local_hls(camera, prefer_rtsp=prefer_rtsp)

    def _after_ready(self, camera, path: str) -> None:
        from apps.streaming import preroll
        from apps.streaming.grab import publisher_rtsp

        src = publisher_rtsp(camera.id, getattr(camera, "rtsp", "") or "")
        try:
            preroll.ensure(path, src)
        except Exception:
            logger.exception("preroll ensure failed camera=%s", camera.id)
        self._sync_camera_status(camera, True)

    def _ensure_camera_stream(self, camera, wait: float = 3.0) -> bool:
        """Make this camera's own RTSP appear on its MTX path. Never fill with demo MP4."""
        path = self._mtx_path_for(camera)
        if not path:
            return False
        if mtx.hls_ready(path, timeout=0.6):
            return True

        from apps.common.process import is_runtime_process

        if not is_runtime_process():
            return mtx.hls_ready(path, timeout=0.4)

        rtsp = (getattr(camera, "rtsp", None) or "").strip()
        if mtx.is_local_mediamtx_rtsp(rtsp):
            return mtx.wait_hls_ready(path, timeout=min(2.0, max(0.4, wait)))
        return self._restream_rtsp(path, rtsp, wait=wait)

    def _restream_rtsp(self, path: str, src_rtsp: str, wait: float = 8.0) -> bool:
        ffmpeg_bin = find_ffmpeg()
        src = (src_rtsp or "").strip()
        dst = mtx.mtx_rtsp_url(path)
        if not ffmpeg_bin or not src or not dst:
            return False
        if src.rstrip("/") == dst.rstrip("/"):
            return mtx.wait_hls_ready(path, timeout=min(2.0, max(0.4, wait)))

        with self._lock:
            proc = self._publishers.get(path)
            same_src = self._publisher_src.get(path) == src
            if proc is None or proc.poll() is not None or not same_src:
                if proc is not None and proc.poll() is None:
                    self._kill_proc(proc)
                cmd = build_restream_cmd(ffmpeg_bin, src, dst)
                try:
                    proc = subprocess.Popen(cmd, **popen_kwargs())
                    self._publishers[path] = proc
                    self._publisher_src[path] = src
                    logger.info("mtx restream started path=%s src=%s pid=%s", path, src, proc.pid)
                except Exception:
                    logger.exception("mtx restream failed path=%s src=%s", path, src)
                    return False

        if proc is not None and proc.poll() is not None:
            logger.warning("mtx restream exited immediately path=%s code=%s", path, proc.returncode)
            return False

        return mtx.wait_hls_ready(path, timeout=max(1.0, wait))

    def ensure_online_cameras(self) -> int:
        """Runtime: restream each enabled camera with RTSP onto its MTX path."""
        from apps.cameras.models import Camera

        n = 0
        qs = Camera.objects.filter(enabled=True).only("id", "rtsp", "status")
        for cam in qs.only("id", "rtsp", "status"):
            if not (cam.rtsp or "").strip():
                continue
            ready = self._ensure_camera_stream(cam, wait=2.0)
            if ready:
                self._after_ready(cam, self._mtx_path_for(cam))
                n += 1
            else:
                self._sync_camera_status(cam, False)
            self.status(cam.id)
        return n

    def process_stream_cmds(self) -> None:
        from apps.cameras.models import Camera
        from apps.common import rdb

        for cid, action in rdb.pop_stream_cmds():
            cam = Camera.objects.filter(pk=cid).first()
            if not cam:
                continue
            try:
                if action == "start":
                    self.start(cam, prefer_rtsp=True)
                else:
                    path = self._mtx_path_for(cam)
                    self.stop(cid)
                    from apps.streaming import preroll

                    preroll.stop(path)
                    self._sync_camera_status(cam, False)
                    self.status(cid)
            except Exception:
                logger.exception("stream cmd %s failed camera=%s", action, cid)

    def _sync_camera_status(self, camera, live: bool) -> None:
        desired = "online" if live else "offline"
        if getattr(camera, "status", "") == desired:
            return
        try:
            type(camera).objects.filter(pk=camera.id).update(status=desired)
            camera.status = desired
        except Exception:
            logger.debug("camera status sync skipped id=%s", getattr(camera, "id", None))

    def _start_local_hls(self, camera, prefer_rtsp=True):
        ffmpeg_bin = find_ffmpeg()
        if not ffmpeg_bin:
            raise RuntimeError("未找到 ffmpeg，请安装后设置 PATH 或 FFMPEG_PATH")

        state = self._state(camera.id)
        rtsp = (camera.rtsp or "").strip()
        if not (prefer_rtsp and rtsp.lower().startswith("rtsp://")):
            raise RuntimeError("未配置 RTSP，无法启动预览流")
        source_key = f"rtsp:{rtsp}"

        shared_id = self._find_shared(source_key, exclude_id=camera.id)
        if shared_id is not None:
            return self._apply_alias(state, shared_id, source_key)

        with state.lock:
            if state.process and state.process.poll() is None and not state.alias_of:
                already_running = True
                cmds = []
            else:
                already_running = False
                out_dir = camera_hls_dir(camera.id)
                for item in out_dir.iterdir():
                    try:
                        if item.is_file():
                            item.unlink()
                    except OSError:
                        pass
                state.status = "starting"
                state.error = ""
                state.started_at = time.time()
                state.alias_of = None
                state.source_key = source_key
                state.mtx_path = None
                from apps.streaming.ffmpeg import build_rtsp_cmd

                cmds = [("rtsp", build_rtsp_cmd(ffmpeg_bin, camera, playlist_path(camera.id)))]

        if already_running:
            return self.status(camera.id)

        last_err = ""
        out_dir = camera_hls_dir(camera.id)
        for mode, cmd in cmds:
            try:
                proc = subprocess.Popen(cmd, cwd=str(out_dir), **popen_kwargs())
                deadline = time.time() + (8 if mode == "rtsp" else 4)
                ready = False
                while time.time() < deadline:
                    if proc.poll() is not None:
                        last_err = f"FFmpeg 退出码 {proc.returncode} ({mode})"
                        break
                    if playlist_path(camera.id).exists():
                        ready = True
                        break
                    time.sleep(0.2)
                if ready and proc.poll() is None:
                    with state.lock:
                        state.process = proc
                        state.pid = proc.pid
                        state.mode = mode
                        state.status = "running"
                        state.error = ""
                        state.hls_url = local_hls_url(camera.id)
                        state.alias_of = None
                    logger.info("stream camera=%s mode=%s pid=%s (local fallback)", camera.id, mode, proc.pid)
                    threading.Thread(
                        target=self._watch, args=(camera.id, proc), daemon=True, name=f"hls-watch-{camera.id}"
                    ).start()
                    return self.status(camera.id)
                self._kill_proc(proc)
            except Exception as exc:
                last_err = str(exc)
                logger.exception("start local stream failed camera=%s mode=%s", camera.id, mode)

        with state.lock:
            state.status = "error"
            state.error = last_err or "启动 HLS 失败"
            state.process = None
            state.pid = None
            state.mode = None
            state.hls_url = None
        raise RuntimeError(state.error)

    def start_async(self, camera, prefer_rtsp=True):
        return self.start(camera, prefer_rtsp=prefer_rtsp)

    def _start_safe(self, camera_id, prefer_rtsp):
        from apps.cameras.models import Camera

        acquired = self._start_sem.acquire(timeout=20)
        if not acquired:
            state = self._state(camera_id)
            with state.lock:
                if state.status == "starting":
                    state.status = "error"
                    state.error = "启动队列繁忙，请稍后重试"
            return
        try:
            camera = Camera.objects.get(pk=camera_id)
            self.start(camera, prefer_rtsp=prefer_rtsp)
        except Exception as exc:
            state = self._state(camera_id)
            with state.lock:
                if state.status == "starting":
                    state.status = "error"
                    state.error = str(exc)
            logger.exception("async start failed camera=%s", camera_id)
        finally:
            self._start_sem.release()

    def _watch(self, camera_id, proc):
        code = proc.wait()
        state = self._state(camera_id)
        with state.lock:
            if state.process is proc:
                state.process = None
                state.pid = None
                if state.status == "running":
                    state.status = "error" if code not in (0, None, -9, -15) else "idle"
                    if code not in (0, None, -9, -15):
                        state.error = f"FFmpeg 退出码 {code}"
                logger.info("stream ended camera=%s code=%s", camera_id, code)

    def stop(self, camera_id):
        from apps.common.process import is_runtime_process
        from apps.common import rdb

        cid = int(camera_id)
        if not is_runtime_process():
            rdb.put_stream_cmd(cid, "stop")
            current = rdb.get_stream_health(cid) or {}
            current["hlsReady"] = False
            current["streamStatus"] = "idle"
            current["playlistReady"] = False
            rdb.put_stream_health(cid, current)
            return self.status(cid)

        state = self._state(cid)
        with state.lock:
            proc = state.process
            path = state.mtx_path
            state.process = None
            state.pid = None
            state.status = "idle"
            state.error = ""
            state.mode = None
            state.alias_of = None
            state.source_key = None
            state.hls_url = None
            state.mtx_path = None
        if proc:
            self._kill_proc(proc)
        if path:
            try:
                from apps.streaming import preroll

                preroll.stop(path)
            except Exception:
                pass
        rdb.put_stream_health(
            cid,
            {"hlsReady": False, "streamStatus": "idle", "mtxPath": path, "hlsUrl": None},
        )
        return self.status(cid)

    def stop_all(self):
        with self._lock:
            ids = list(self._states.keys())
            pubs = list(self._publishers.items())
            self._publishers.clear()
            self._publisher_src.clear()
        for cid in ids:
            try:
                self.stop(cid)
            except Exception:
                logger.exception("stop_all camera=%s", cid)
        for path, proc in pubs:
            self._kill_proc(proc)
            logger.info("stopped mtx publisher path=%s", path)
        try:
            from apps.streaming import preroll

            preroll.stop_all()
        except Exception:
            pass

    @staticmethod
    def _kill_proc(proc):
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


stream_manager = StreamManager()
