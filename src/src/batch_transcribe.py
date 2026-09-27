import json
import subprocess
import sys
from pathlib import Path

from faster_whisper import WhisperModel


def run_ffmpeg(
    video_path,
    audio_path
):
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(audio_path),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if result.returncode != 0:
        print(result.stdout)

        raise RuntimeError(
            f"FFmpeg failed for "
            f"{video_path}"
        )


def transcribe_video(
    model,
    video_path,
    output_path
):
    video = Path(
        video_path
    )

    output = Path(
        output_path
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    audio_path = (
        output.parent
        / f"{video.stem}.wav"
    )

    print("")
    print(
        "===================================="
    )

    print(
        f"Transcribing: {video.name}"
    )

    print(
        "===================================="
    )

    print(
        "Extracting audio..."
    )

    run_ffmpeg(
        video,
        audio_path
    )

    print(
        "Running Nepali transcription..."
    )

    segments, info = model.transcribe(
        str(audio_path),
        language="ne",
        task="transcribe",
        beam_size=5,
        temperature=[
            0.0,
            0.2,
            0.4,
            0.6,
            0.8,
            1.0,
        ],
        condition_on_previous_text=False,
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
        no_speech_threshold=0.6,
        repetition_penalty=1.1,
        no_repeat_ngram_size=3,
        vad_filter=True,
        vad_parameters={
            "min_silence_duration_ms": 500
        },
        word_timestamps=True,
        initial_prompt=(
            "यो नेपालको संघीय संसदको औपचारिक "
            "बैठक हो। नेपाली भाषामा सभामुख, "
            "अध्यक्ष, सांसद, मन्त्री तथा सरकारी "
            "अधिकारीहरूले सम्बोधन गरिरहेका छन्। "
            "सम्भव भएसम्म स्पष्ट नेपाली शब्द "
            "प्रयोग गर्नुहोस्।"
        ),
    )

    transcript = {
        "video": str(video),
        "language": info.language,
        "language_probability": (
            info.language_probability
        ),
        "model": "large-v3-turbo",
        "segments": [],
    }

    for segment in segments:

        text = segment.text.strip()

        if not text:
            continue

        transcript[
            "segments"
        ].append(
            {
                "start": round(
                    segment.start,
                    3
                ),
                "end": round(
                    segment.end,
                    3
                ),
                "nepali": text,
            }
        )

    with open(
        output,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            transcript,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"Transcript saved: {output}"
    )

    try:
        audio_path.unlink()
    except FileNotFoundError:
        pass

    return transcript


def transcribe_directory(
    input_dir,
    output_dir
):
    input_path = Path(
        input_dir
    )

    output_path = Path(
        output_dir
    )

    output_path.mkdir(
        parents=True,
        exist_ok=True
    )

    videos = sorted(
        input_path.glob(
            "video_*.mp4"
        )
    )

    if not videos:
        raise RuntimeError(
            f"No videos found in "
            f"{input_path}"
        )

    print("")
    print(
        "===================================="
    )

    print(
        "BATCH NEPALI TRANSCRIPTION"
    )

    print(
        "===================================="
    )

    print(
        f"Found {len(videos)} videos"
    )

    print("")
    print(
        "Loading Whisper model..."
    )

    model = WhisperModel(
        "large-v3-turbo",
        device="cpu",
        compute_type="int8",
    )

    results = []

    for index, video in enumerate(
        videos,
        start=1
    ):

        print("")
        print(
            f"VIDEO {index}/{len(videos)}"
        )

        output_file = (
            output_path
            / f"{video.stem}.json"
        )

        try:

            transcript = transcribe_video(
                model,
                video,
                output_file
            )

            results.append(
                {
                    "video": str(video),
                    "transcript": str(
                        output_file
                    ),
                    "segments": len(
                        transcript[
                            "segments"
                        ]
                    ),
                    "status": "success",
                }
            )

        except Exception as error:

            print(
                f"Transcription failed: "
                f"{error}"
            )

            results.append(
                {
                    "video": str(video),
                    "transcript": None,
                    "segments": 0,
                    "status": "failed",
                    "error": str(
                        error
                    ),
                }
            )

    summary_file = (
        output_path
        / "transcription_summary.json"
    )

    with open(
        summary_file,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            results,
            file,
            ensure_ascii=False,
            indent=2,
        )

    successful = sum(
        1
        for item in results
        if item["status"] == "success"
    )

    failed = len(results) - successful

    print("")
    print(
        "===================================="
    )

    print(
        "TRANSCRIPTION SUMMARY"
    )

    print(
        "===================================="
    )

    print(
        f"Total: {len(results)}"
    )

    print(
        f"Successful: {successful}"
    )

    print(
        f"Failed: {failed}"
    )

    print(
        f"Summary: {summary_file}"
    )

    if successful == 0:
        raise RuntimeError(
            "All video transcriptions failed."
        )


if __name__ == "__main__":

    if len(sys.argv) != 3:

        print("Usage:")

        print(
            "python batch_transcribe.py "
            "<input_video_directory> "
            "<output_directory>"
        )

        sys.exit(1)

    input_directory = sys.argv[1]

    output_directory = sys.argv[2]

    transcribe_directory(
        input_directory,
        output_directory
    )
