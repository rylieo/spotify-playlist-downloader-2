import subprocess
import os
import time


def encode_audio(
    input_wav, output_file, fmt="aac", bitrate_k=192, timeout_sec=None, stop_event=None
):
    outdir = os.path.dirname(output_file)
    if outdir:
        os.makedirs(outdir, exist_ok=True)

    codec_args = []
    if fmt == "aac":
        # Use native AAC encoder, container .m4a
        codec_args = ["-c:a", "aac", "-b:a", f"{bitrate_k}k"]
    elif fmt == "ogg":
        codec_args = ["-c:a", "libvorbis", "-b:a", f"{bitrate_k}k"]
    else:
        codec_args = ["-c:a", "libmp3lame", "-b:a", f"{bitrate_k}k"]

    cmd = (
        [
            "ffmpeg",
            "-y",
            "-i",
            input_wav,
            "-map_metadata",
            "-1",
            "-vn",
        ]
        + codec_args
        + [output_file]
    )

    stdout_pipe = subprocess.PIPE
    stderr_pipe = subprocess.PIPE
    proc = subprocess.Popen(cmd, stdout=stdout_pipe, stderr=stderr_pipe)

    try:
        start_time = time.time()
        while True:
            try:
                # Gunakan timeout yang lebih besar (misalnya 5 detik) untuk menghindari
                # pemanggilan wait() yang terlalu sering
                ret = proc.wait(timeout=5)
                break
            except subprocess.TimeoutExpired:
                # check cancellation
                if stop_event is not None and stop_event.is_set():
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    proc.wait()
                    raise RuntimeError("Encoding cancelled by user")

                # enforce timeout if set
                if timeout_sec is not None and (time.time() - start_time) > timeout_sec:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        pass
                    raise RuntimeError(f"Encoding timed out after {timeout_sec}s")
                continue

        if ret != 0:
            stderr = ""
            try:
                stderr = proc.stderr.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise RuntimeError(f"ffmpeg failed for {output_file}: {stderr}")
    finally:
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass


# Backwards compatible wrapper
def encode_mp3(input_wav, output_mp3, stop_event=None):
    encode_audio(input_wav, output_mp3, fmt="mp3", bitrate_k=192, stop_event=stop_event)
