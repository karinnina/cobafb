import sys
import subprocess
import threading
import os
import signal
import streamlit.components.v1 as components

# Install streamlit jika belum ada
try:
    import streamlit as st
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "streamlit"])
    import streamlit as st


# Simpan process FFmpeg agar bisa dihentikan dengan aman tanpa pkill semua ffmpeg
ffmpeg_process = None


def run_ffmpeg(video_path, stream_key, is_vertical, log_callback):
    global ffmpeg_process

    # ✅ Server Facebook Live
    output_url = f"rtmps://live-api-s.facebook.com:443/rtmp/{stream_key}"

    # Filter dibuat tetap ringan, fokus smooth loop/live tanpa jeda.
    # fps=30 + setpts/asetpts membantu timestamp stabil saat stream_loop.
    if is_vertical:
        vf_filter = "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,fps=30,setpts=N/(30*TB)"
    else:
        vf_filter = "fps=30,setpts=N/(30*TB)"

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "info",

        # Baca input sebagai live source dan loop tanpa batas
        "-re",
        "-stream_loop", "-1",

        # Buffer input diperbesar agar pembacaan file lebih stabil
        "-thread_queue_size", "4096",
        "-fflags", "+genpts+igndts",
        "-avoid_negative_ts", "make_zero",
        "-i", video_path,

        # Video: H264 stabil untuk Facebook Live
        "-vf", vf_filter,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "zerolatency",
        "-profile:v", "main",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-b:v", "2500k",
        "-maxrate", "2500k",
        "-bufsize", "5000k",
        "-g", "60",
        "-keyint_min", "60",
        "-sc_threshold", "0",

        # Audio: dibuat konstan agar tidak patah saat loop
        "-af", "aresample=async=1:first_pts=0",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-ac", "2",

        # Output FLV/RTMPS Facebook
        "-flvflags", "no_duration_filesize",
        "-f", "flv",
        output_url
    ]

    log_callback(f"Menjalankan: {' '.join(cmd)}")

    try:
        ffmpeg_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        for line in ffmpeg_process.stdout:
            log_callback(line.strip())

        ffmpeg_process.wait()

    except Exception as e:
        log_callback(f"Error: {e}")
    finally:
        ffmpeg_process = None
        log_callback("Streaming selesai atau dihentikan.")


def stop_ffmpeg(log_callback=None):
    global ffmpeg_process

    if ffmpeg_process and ffmpeg_process.poll() is None:
        try:
            if os.name == "nt":
                ffmpeg_process.terminate()
            else:
                os.kill(ffmpeg_process.pid, signal.SIGTERM)
            ffmpeg_process.wait(timeout=5)
        except Exception:
            try:
                ffmpeg_process.kill()
            except Exception:
                pass
        finally:
            ffmpeg_process = None
            if log_callback:
                log_callback("FFmpeg dihentikan.")
    else:
        if log_callback:
            log_callback("Tidak ada proses FFmpeg yang sedang berjalan.")


def main():
    st.set_page_config(
        page_title="Streaming Facebook Live",
        page_icon="📺",
        layout="wide"
    )

    st.config.set_option("server.maxUploadSize", 1000)

    st.title("Live Streaming ke Facebook")

    show_ads = st.checkbox("Tampilkan Iklan", value=False)
    if show_ads:
        st.subheader("Iklan Sponsor")
        components.html(
            """
            <div style="background:#f0f2f6;padding:20px;border-radius:10px;text-align:center">
                <p style="color:#888">Iklan akan muncul di sini</p>
            </div>
            """,
            height=200
        )

    video_files = [f for f in os.listdir('.') if f.endswith(('.mp4', '.flv'))]

    st.write("Video yang tersedia:")
    selected_video = st.selectbox("Pilih video", video_files) if video_files else None

    uploaded_file = st.file_uploader(
        "Atau upload video baru (mp4/flv - codec H264/AAC)",
        type=['mp4', 'flv']
    )

    if uploaded_file:
        with open(uploaded_file.name, "wb") as f:
            f.write(uploaded_file.read())
        st.success("Video berhasil diupload!")
        video_path = uploaded_file.name
    elif selected_video:
        video_path = selected_video
    else:
        video_path = None

    # ✅ Stream Key Facebook Live
    stream_key = st.text_input("Facebook Stream Key", type="password")
    is_vertical = st.checkbox("Mode Vertikal (720x1280)")

    if 'logs' not in st.session_state:
        st.session_state['logs'] = []

    if 'streaming' not in st.session_state:
        st.session_state['streaming'] = False

    if 'ffmpeg_thread' not in st.session_state:
        st.session_state['ffmpeg_thread'] = None

    log_placeholder = st.empty()

    def log_callback(msg):
        st.session_state['logs'].append(msg)
        try:
            log_placeholder.text("\n".join(st.session_state['logs'][-20:]))
        except Exception:
            print(msg)

    if st.button("Mulai Streaming"):
        if not video_path or not stream_key:
            st.error("Video dan stream key harus diisi!")
        else:
            if st.session_state['streaming']:
                st.warning("Streaming sudah berjalan.")
            else:
                st.session_state['streaming'] = True
                st.session_state['ffmpeg_thread'] = threading.Thread(
                    target=run_ffmpeg,
                    args=(video_path, stream_key, is_vertical, log_callback),
                    daemon=True
                )
                st.session_state['ffmpeg_thread'].start()
                st.success("Streaming dimulai ke Facebook!")

    if st.button("Hentikan Streaming"):
        st.session_state['streaming'] = False
        stop_ffmpeg(log_callback)
        st.warning("Streaming dihentikan!")

    log_placeholder.text("\n".join(st.session_state['logs'][-20:]))


if __name__ == '__main__':
    main()
