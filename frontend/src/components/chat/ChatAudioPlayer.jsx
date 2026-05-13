import { useCallback, useEffect, useRef, useState } from "react";
import { FiPause, FiPlay } from "react-icons/fi";
import "./chat-audio-player.css";

const WAVE_HEIGHTS = [
  4, 7, 5, 9, 6, 8, 4, 7, 5, 8, 6, 9, 5, 7, 4, 8, 6, 5, 9, 7, 6, 4, 8, 5,
];

function formatAudioTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const s = Math.floor(seconds);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

function mediaErrorMessage(code) {
  const E =
    typeof MediaError !== "undefined"
      ? MediaError
      : { MEDIA_ERR_ABORTED: 1, MEDIA_ERR_NETWORK: 2, MEDIA_ERR_DECODE: 3, MEDIA_ERR_SRC_NOT_SUPPORTED: 4 };
  switch (code) {
    case E.MEDIA_ERR_ABORTED:
      return "Lecture interrompue.";
    case E.MEDIA_ERR_NETWORK:
      return "Erreur réseau pendant la lecture.";
    case E.MEDIA_ERR_DECODE:
      return "Fichier audio illisible.";
    case E.MEDIA_ERR_SRC_NOT_SUPPORTED:
      return "Format non pris en charge par ce navigateur (ex. Opus/OGG sous Safari). Essayez Chrome ou Edge.";
    default:
      return "Impossible de lire l’audio.";
  }
}

export default function ChatAudioPlayer({ src, mimeType }) {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [current, setCurrent] = useState(0);
  const [decodeError, setDecodeError] = useState(null);

  const playPause = useCallback(() => {
    const el = audioRef.current;
    if (!el) return;
    el.muted = false;
    el.volume = 1;
    if (el.paused) {
      void el.play().catch((err) => {
        console.warn("[ChatAudioPlayer] play()", err);
        setDecodeError(
          "Lecture bloquée (navigateur ou interaction). Vérifiez aussi le volume système."
        );
      });
    } else {
      el.pause();
    }
  }, []);

  const seekFromClientX = useCallback(
    (clientX, trackEl) => {
      const el = audioRef.current;
      if (!el || !trackEl || !Number.isFinite(duration) || duration <= 0) return;
      const rect = trackEl.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      el.currentTime = ratio * duration;
      setCurrent(el.currentTime);
    },
    [duration]
  );

  const onTrackClick = useCallback(
    (e) => {
      seekFromClientX(e.clientX, e.currentTarget);
    },
    [seekFromClientX]
  );

  const onTrackKeyDown = useCallback(
    (e) => {
      const el = audioRef.current;
      if (!el || !Number.isFinite(duration)) return;
      const step = Math.min(5, duration * 0.05 || 5);
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        el.currentTime = Math.max(0, el.currentTime - step);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        el.currentTime = Math.min(duration, el.currentTime + step);
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        playPause();
      }
    },
    [duration, playPause]
  );

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    el.defaultMuted = false;
    el.muted = false;
    el.volume = 1;
    setDecodeError(null);

    const onMeta = () => setDuration(el.duration || 0);
    const onTime = () => setCurrent(el.currentTime);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onEnded = () => setPlaying(false);
    const onErr = () => {
      const code = el.error?.code;
      console.warn("[ChatAudioPlayer] error", code, el.error?.message, { mimeType, src: src?.slice(0, 80) });
      if (code != null) {
        setDecodeError(mediaErrorMessage(code));
      } else {
        setDecodeError(mediaErrorMessage(3));
      }
    };

    el.addEventListener("loadedmetadata", onMeta);
    el.addEventListener("durationchange", onMeta);
    el.addEventListener("timeupdate", onTime);
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("ended", onEnded);
    el.addEventListener("error", onErr);

    return () => {
      el.removeEventListener("loadedmetadata", onMeta);
      el.removeEventListener("durationchange", onMeta);
      el.removeEventListener("timeupdate", onTime);
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("ended", onEnded);
      el.removeEventListener("error", onErr);
      try {
        el.pause();
      } catch {
        /* ignore */
      }
    };
  }, [src, mimeType]);

  const pct = duration > 0 ? Math.min(100, (current / duration) * 100) : 0;

  return (
    <div
      className={`chat-audio-player${playing ? " chat-audio-player--playing" : ""}`}
      onClick={(e) => e.stopPropagation()}
    >
      <audio
        key={src || "no-src"}
        ref={audioRef}
        src={src || undefined}
        preload="auto"
        className="chat-audio-player__native"
      />
      <button
        type="button"
        className="chat-audio-player__play"
        onClick={(e) => {
          e.stopPropagation();
          playPause();
        }}
        aria-label={playing ? "Pause" : "Lecture"}
      >
        {playing ? <FiPause /> : <FiPlay className="chat-audio-player__icon-play" />}
      </button>
      <div className="chat-audio-player__main">
        <div className="chat-audio-player__wave" aria-hidden>
          {WAVE_HEIGHTS.map((h, i) => (
            <span
              key={i}
              className="chat-audio-player__wave-bar"
              style={{ height: `${6 + (h % 7) * 2}px` }}
            />
          ))}
        </div>
        <div
          className="chat-audio-player__track"
          role="slider"
          tabIndex={0}
          aria-valuemin={0}
          aria-valuemax={Math.round(duration * 1000) || 0}
          aria-valuenow={Math.round(current * 1000)}
          aria-label="Position dans l’audio"
          onClick={onTrackClick}
          onKeyDown={onTrackKeyDown}
        >
          <div className="chat-audio-player__track-fill" style={{ width: `${pct}%` }} />
        </div>
        <div className="chat-audio-player__times">
          <span>{formatAudioTime(current)}</span>
          <span>{formatAudioTime(duration)}</span>
        </div>
        {decodeError ? (
          <div className="chat-audio-player__error" role="alert">
            {decodeError}
          </div>
        ) : null}
      </div>
    </div>
  );
}
