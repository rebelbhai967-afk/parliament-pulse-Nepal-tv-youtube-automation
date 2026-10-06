import json
import os
import subprocess
import sys
from pathlib import Path

from faster_whisper import WhisperModel


def run_ffmpeg(video_path, audio_path):
    command = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(audio_path)
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        print(result.stdout)
        raise RuntimeError(f"FFmpeg failed for {video_path}")


def transcribe_video(model, video_path, output_path):
    video = Path(video_path)
    output = Path(output_path)
    if not video.exists():
        raise FileNotFoundError(f"Video not found: {video}")

    output.parent.mkdir(parents=True, exist_ok=True)
    audio_path = output.parent / f"{video.stem}.wav"
    run_ffmpeg(video, audio_path)

    beam_size = int(os.getenv("WHISPER_BEAM_SIZE", "5"))
    temperature = os.getenv("WHISPER_TEMPERATURE", "0.0")
    temperature_value = float(temperature)
    temperatures = [temperature_value, 0.2, 0.4] if temperature_value == 0.0 else temperature_value
    print(f"Whisper: large-v3-turbo / int8 / beam={beam_size} / temperature={temperatures}")

    segments, info = model.transcribe(
        str(audio_path),
        language="ne",
        task="transcribe",
        beam_size=beam_size,
        temperature=temperatures,
        condition_on_previous_text=False,
        compression_ratio_threshold=2.0,
        log_prob_threshold=-1.0,
        no_speech_threshold=0.6,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        word_timestamps=True,
        initial_prompt=(
            "यो नेपालको संघीय संसदको औपचारिक बैठक हो। "
            "नेपाली भाषामा सभामुख, अध्यक्ष, सांसद, मन्त्री "
            "तथा सरकारी अधिकारीहरूले सम्बोधन गरिरहेका छन्।"
        )
    )

    transcript = {
        "video": str(video),
        "language": info.language,
        "language_probability": info.language_probability,
        "model": "large-v3-turbo",
        "transcription_mode": f"beam-{beam_size}",
        "segments": []
    }

    for segment in segments:
        text = str(segment.text).strip()
        if text:
            transcript["segments"].append({
                "start": float(segment.start),
                "end": float(segment.end),
                "nepali": text,
                "avg_logprob": float(getattr(segment, "avg_logprob", 0.0)),
                "compression_ratio": float(getattr(segment, "compression_ratio", 0.0)),
                "no_speech_prob": float(getattr(segment, "no_speech_prob", 0.0)),
            })

    with open(output, "w", encoding="utf-8") as file:
        json.dump(transcript, file, ensure_ascii=False, indent=2)

    if audio_path.exists():
        audio_path.unlink()

    print(f"TRANSCRIPTION COMPLETE: {output}")
    print(f"Segments: {len(transcript['segments'])}")
    return transcript


def transcribe_directory(input_dir, output_dir):
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    videos = sorted(input_path.glob("video_*.mp4"))
    if not videos:
        raise RuntimeError(f"No video_*.mp4 files found in {input_path}")

    print(f"BATCH TRANSCRIPTION: {len(videos)} videos")

    model = WhisperModel(
        "large-v3-turbo",
        device="cpu",
        compute_type="int8",
        cpu_threads=int(os.getenv("WHISPER_CPU_THREADS", "2")),
        num_workers=1
    )

    results = []
    successful = 0
    skipped = 0

    for index, video in enumerate(videos, start=1):
        output_file = output_path / f"{video.stem}.json"
        print(f"VIDEO {index}/{len(videos)}: {video.name}")

        if output_file.exists() and output_file.stat().st_size > 100:
            print(f"Skipping existing transcript: {output_file}")
            results.append({
                "video": str(video),
                "transcript": str(output_file),
                "status": "skipped_existing"
            })
            successful += 1
            skipped += 1
            continue

        try:
            transcript = transcribe_video(model, video, output_file)
            results.append({
                "video": str(video),
                "transcript": str(output_file),
                "segments": len(transcript["segments"]),
                "status": "success"
            })
            successful += 1
        except Exception as error:
            print(f"Transcription failed: {error}")
            results.append({
                "video": str(video),
                "transcript": str(output_file),
                "segments": 0,
                "status": "failed",
                "error": str(error)
            })

    summary = {
        "input_directory": str(input_path),
        "output_directory": str(output_path),
        "total_videos": len(videos),
        "successful": successful,
        "skipped_existing": skipped,
        "failed": len(videos) - successful,
        "results": results
    }

    summary_file = output_path / "transcription_summary.json"
    with open(summary_file, "w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)

    print(f"Total: {len(videos)} | Successful: {successful} | Skipped: {skipped} | Failed: {len(videos)-successful}")

    if successful == 0:
        raise RuntimeError("All Parliament video transcriptions failed.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python src/batch_transcribe.py <input_video_directory> <output_directory>")
    transcribe_directory(sys.argv[1], sys.argv[2])
