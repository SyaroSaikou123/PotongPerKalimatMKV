
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pysubs2


# FILE PATH
BASE_DIR = Path(__file__).resolve().parent

SOURCE_DIR = BASE_DIR 
VIDEO_DIR = SOURCE_DIR / "Video"
AUDIO_DIR = SOURCE_DIR / "Audio_NBGM"
EXPORT_DIR = BASE_DIR / "Ekspor"

# ------------------------------------------------------------
# VIDEO
# ------------------------------------------------------------

# False:
#   MP4 hasil potongan tetap membawa audio asli dari MKV.
#
# True:
#   MP4 hasil potongan hanya berisi video.
#   Audio NBGM akan menjadi file MP3 terpisah.
#
# Untuk workflow otoMAD, biasanya True lebih praktis.
MUTE_EXPORTED_VIDEO = True


# ------------------------------------------------------------
# SUBTITLE
# ------------------------------------------------------------

# Jika True, subtitle event dengan style yang tidak dikenal
# akan tetap diproses.
#
# Jika False, hanya style yang terdapat dalam DIALOG_STYLES
# yang diproses.
#
# Disarankan True untuk awal.

# USE_DIALOG_STYLE_WHITELIST = False

DIALOG_STYLES = {
    "default",
    "dialogue",
    "dialog",
    "main",
    "normal",
    "spoken",
    "speech",
    "Dialog",
    "Dialog Miring",
    "Dialog Atas",
    "Dialog Atas Miring",
}


# Style yang hampir pasti bukan dialog.
NON_DIALOG_STYLE_KEYWORDS = {
    "karaoke",
    "kara",
    "lyric",
    "lyrics",
    "song",
    "opening",
    "ending",
    "op",
    "ed",
    "effect",
    "effects",
    "fx",
    "sign",
    "signs",
    "title",
    "typeset",
    "typ",
    "logo",
    "credits",
    "credit",
    "preview",
}


# ------------------------------------------------------------
# NAMA FILE
# ------------------------------------------------------------

MAX_FILENAME_TEXT_LENGTH = 120

# Jika subtitle sama persis muncul beberapa kali,
# nomor dialog tetap mengikuti urutan subtitle.
#
# Contoh:
# 001_Hello.mp4
# 002_Hello.mp4
#
# bukan:
# 001_Hello.mp4
# 001_Hello_2.mp4


# ============================================================
# PEMERIKSAAN PROGRAM
# ============================================================

def check_program(program: str):
    """
    Memastikan executable tersedia di PATH.
    """

    if shutil.which(program) is None:
        raise RuntimeError(
            f"Program '{program}' tidak ditemukan.\n\n"
            f"Pastikan FFmpeg sudah terinstall dan dapat "
            f"dipanggil dari CMD/PowerShell.\n\n"
            f"Coba:\n"
            f"    {program} -version"
        )


# RUN COMMAND
def run_command(command: list[str]):
    """
    Menjalankan command eksternal.
    """

    print("\n> " + " ".join(map(str, command)))

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:

        print("\n--- FFmpeg/FFprobe ERROR ---")
        print(result.stderr)

        raise RuntimeError(
            f"Command gagal dengan exit code "
            f"{result.returncode}"
        )

    return result


# FFPROBE
def ffprobe_subtitle_streams(video_file: Path):
    """
    Mendapatkan semua subtitle stream dari MKV.
    """

    command = [
        "ffprobe",
        "-v", "error",

        "-select_streams", "s",

        "-show_entries",
        "stream=index,codec_name:stream_tags=language,title",

        "-of", "json",

        str(video_file),
    ]

    result = run_command(command)

    data = json.loads(result.stdout)

    return data.get("streams", [])


def find_text_subtitle_stream(video_file: Path):
    """
    Mencari subtitle berbasis teks.

    Jika terdapat beberapa subtitle text stream,
    untuk sekarang digunakan stream pertama.
    """

    streams = ffprobe_subtitle_streams(video_file)

    if not streams:
        return None

    text_codecs = {
        "subrip",
        "ass",
        "ssa",
        "webvtt",
        "mov_text",
        "text",
    }

    for stream in streams:

        codec = (
            stream.get("codec_name") or ""
        ).lower()

        if codec in text_codecs:
            return stream

    return None


# ============================================================
# EKSTRAK SUBTITLE
# ============================================================

def extract_subtitle(
    video_file: Path,
    subtitle_file: Path,
):
    """
    Mengekstrak subtitle text stream dari MKV
    dan mengubahnya menjadi ASS.
    """

    stream = find_text_subtitle_stream(video_file)

    if stream is None:
        raise RuntimeError(
            f"Tidak ditemukan subtitle berbasis teks "
            f"pada:\n{video_file}"
        )

    stream_index = stream["index"]
    codec = stream.get("codec_name", "unknown")

    tags = stream.get("tags", {})

    language = tags.get("language", "")
    title = tags.get("title", "")

    print(
        "\nSubtitle stream:"
        f"\n  index    : {stream_index}"
        f"\n  codec    : {codec}"
        f"\n  language : {language}"
        f"\n  title    : {title}"
    )

    command = [
        "ffmpeg",
        "-y",

        "-v", "error",

        "-i", str(video_file),

        "-map", f"0:{stream_index}",

        "-c:s", "ass",

        str(subtitle_file),
    ]

    run_command(command)


# ============================================================
# PEMBERSIHAN TEKS ASS
# ============================================================

def remove_ass_override_tags(text: str) -> str:
    """
    Menghapus:
        {\\i1}
        {\\an8}
        {\\pos(...)}
        {\\k20}
        dll.
    """

    return re.sub(
        r"\{[^}]*\}",
        "",
        text,
    )


def clean_subtitle_text(text: str) -> str:
    """
    Mengubah teks subtitle ASS menjadi teks biasa.
    """

    if text is None:
        return ""

    text = remove_ass_override_tags(text)

    # ASS line break
    text = text.replace("\\N", " ")
    text = text.replace("\\n", " ")

    # ASS hard space
    text = text.replace("\\h", " ")

    text = text.replace("\n", " ")
    text = text.replace("\r", " ")

    # Whitespace
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# ASS DRAWING
# ============================================================

def has_ass_drawing_tag(raw_text: str) -> bool:
    """
    Mendeteksi ASS drawing mode.

    Contoh:

        {\\p1}m 5 -13 l 5 -11 ...
        {\\p2}...
        {\\p4}...

    \p0 = kembali ke text mode,
    sehingga \p0 sendiri tidak dianggap drawing.
    """

    if not raw_text:
        return False

    drawing_tags = re.findall(
        r"\\p(-?\d+)",
        raw_text,
        re.IGNORECASE,
    )

    for value in drawing_tags:

        try:
            mode = int(value)
        except ValueError:
            continue

        if mode > 0:
            return True

    return False


def looks_like_vector_drawing(text: str) -> bool:
    """
    Mendeteksi vector drawing ASS yang mungkin sudah tidak
    mempunyai tag \\p1 setelah diproses.

    Contoh:

        m 5 -13 l 5 -11 6 -9
        b 8 -8 8 -7 7 -6
        l 7 -4 8 -3
    """

    if not text:
        return False

    # Command drawing ASS.
    commands = "mlbns p c"

    drawing_pattern = re.compile(
        r"""
        ^
        (?:
            [mlbnspc]
            \s+
            -?\d+(?:\.\d+)?
            \s+
            -?\d+(?:\.\d+)?
            (?:
                \s+
                -?\d+(?:\.\d+)?
                \s+
                -?\d+(?:\.\d+)?
            )*
        )
        (?:
            \s+
            [mlbnspc]
            \s+
            -?\d+(?:\.\d+)?
            \s+
            -?\d+(?:\.\d+)?
            (?:
                \s+
                -?\d+(?:\.\d+)?
                \s+
                -?\d+(?:\.\d+)?
            )*
        )*
        \s*
        $
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    return bool(
        drawing_pattern.match(text)
    )


# ============================================================
# KARAOKE TAG
# ============================================================

def has_karaoke_tags(raw_text: str) -> bool:
    """
    Mendeteksi tag karaoke ASS.

    Contoh:

        {\\k20}ra
        {\\K20}ra
        {\\kf20}ra
        {\\ko20}ra
        {\\Kf20}ra
    """

    if not raw_text:
        return False

    return bool(
        re.search(
            r"\\(?:k|K|kf|Kf|ko|Ko)\d+",
            raw_text,
        )
    )


# STYLE
# def is_non_dialog_style(style: str) -> bool:
#     """
#     Mengecek apakah style merupakan style non-dialog.
#     """

#     if not style:
#         return False

#     style_normalized = style.strip().lower()

#     if style_normalized in NON_DIALOG_STYLE_KEYWORDS:
#         return True

#     for keyword in NON_DIALOG_STYLE_KEYWORDS:

#         if keyword in style_normalized:
#             return True

#     return False

def is_dialog_style(style: str) -> bool:
    """
    Hanya style yang secara eksplisit diketahui sebagai dialog
    yang boleh diproses.

    Ini jauh lebih aman daripada mencoba mencari semua
    kemungkinan style non-dialog.
    """

    return style.strip().lower() in {
        "dialog",
        "dialog miring",
        "dialog atas",
        "dialog atas miring",
    }


# ============================================================
# KARAOKE BERDASARKAN ATURAN USER
# ============================================================

#ini buat fix bagian subtitle karaoke romaji

def is_lowercase_single_syllable_candidate(
    text: str,
) -> bool:
    """
    Aturan khusus karaoke:

    Teks karaoke adalah suku kata yang:
      1. hanya satu token
      2. diawali huruf kecil
      3. berbasis alfabet Latin
      4. pendek

    Contoh yang akan dianggap kandidat:

        ra
        re
        ri
        ru
        ro

        ka
        ki
        ku

    Sedangkan:

        Ya
        Eh

    TIDAK dibuang karena diawali huruf kapital.

    --------------------------------------------------------

    CATATAN:

    Fungsi ini sengaja hanya menjadi kandidat.
    Kita tidak langsung membuang SEMUA teks lowercase
    karena kata seperti:

        ok
        no
        yes

    bisa saja merupakan dialog sungguhan.

    Untuk mengurangi false positive, kandidat harus cocok
    dengan pola suku kata pendek.
    """

    if not text:
        return False

    text = text.strip()

    # Harus satu token
    if " " in text:
        return False

    # Harus dimulai huruf kecil
    if not text[0].islower():
        return False

    # Hanya alfabet
    if not re.fullmatch(
        r"[a-z]+",
        text,
    ):
        return False

    # Suku kata pendek.
    #
    # Pola sederhana:
    #   CV
    #   CVC
    #   CVV
    #   CCV
    #   CCVC
    #
    # Tidak dimaksudkan sebagai linguistic syllabifier sempurna.
    if len(text) > 4:
        return False

    return True


def is_karaoke_syllable(
    text: str,
    raw_text: str,
) -> bool:
    """
    Menentukan apakah sebuah subtitle event merupakan
    karaoke syllable.
    """

    # Karaoke ASS tag adalah indikator terkuat.
    if has_karaoke_tags(raw_text):
        return True

    # Aturan lowercase satu suku kata.
    if is_lowercase_single_syllable_candidate(text):
        return True

    return False


# ============================================================
# FILTER SUBTITLE
# ============================================================

def classify_subtitle_event(sub):
    """
    Menentukan apakah subtitle merupakan dialog.

    Prioritas:
    1. Style harus merupakan style dialog.
    2. Bukan ASS drawing.
    3. Bukan karaoke tag.
    4. Bukan vector drawing.
    5. Bukan kandidat karaoke lowercase.
    """

    raw_text = sub.text or ""
    text = clean_subtitle_text(raw_text)
    style = (sub.style or "").strip()

    # ========================================================
    # 1. STYLE
    # ========================================================
    #
    # Ini filter TERPENTING.
    #
    # Contoh yang akan dibuang:
    #
    #   Judul Episode
    #   Tata Rias
    #   TS Cuk
    #   Ano Hikari - Romaji
    #   Ano Hikari - Indonesia
    #   Kolab
    #   YES to NO no Aida ni - Romaji
    #   YES to NO no Aida ni - Indonesia
    #
    # Hanya style Dialog* yang lolos.
    #

    if not is_dialog_style(style):
        return True, f"non-dialog style: {style}"

    # ========================================================
    # 2. TEKS KOSONG
    # ========================================================

    if not text:
        return True, "teks kosong"

    # ========================================================
    # 3. ASS VECTOR DRAWING
    # ========================================================

    if has_ass_drawing_tag(raw_text):
        return True, "ASS vector drawing"

    # ========================================================
    # 4. KARAOKE TAG
    # ========================================================

    if has_karaoke_tags(raw_text):
        return True, "karaoke tag"

    # ========================================================
    # 5. VECTOR DRAWING
    # ========================================================

    if looks_like_vector_drawing(text):
        return True, "vector drawing"

    # ========================================================
    # 6. LOWERCASE SINGLE-SYLLABLE KARAOKE
    # ========================================================

    if is_lowercase_single_syllable_candidate(text):
        return True, (
            "lowercase single-syllable karaoke: "
            f"{text}"
        )

    return False, ""

# NAMA FILE

def sanitize_filename(
    text: str,
    max_length: int = MAX_FILENAME_TEXT_LENGTH,
) -> str:
    """
    Mengubah teks subtitle menjadi nama file aman Windows.
    """

    text = clean_subtitle_text(text)

    # Windows illegal characters
    text = re.sub(
        r'[<>:"/\\|?*]',
        "_",
        text,
    )

    # Control characters
    text = re.sub(
        r"[\x00-\x1f]",
        "",
        text,
    )

    # Whitespace berlebihan
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    # Jangan berakhir dengan titik/spasi
    text = text.rstrip(" .")

    if not text:
        text = "Tanpa_Teks"

    # Batasi panjang
    text = text[:max_length]

    text = text.rstrip(" .")

    return text


# TIMESTAMP
def format_time(seconds: float) -> str:
    """
    Contoh:

        12.345
        ->
        00:00:12.345
    """

    milliseconds = round(seconds * 1000)

    hours = milliseconds // 3_600_000
    milliseconds %= 3_600_000

    minutes = milliseconds // 60_000
    milliseconds %= 60_000

    seconds_int = milliseconds // 1000
    milliseconds %= 1000

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{seconds_int:02d}."
        f"{milliseconds:03d}"
    )


# MEMBACA SUBTITLE
def get_subtitle_events(subtitle_file: Path):
    """
    Membaca subtitle dan hanya mengambil event dialog.
    """

    subs = pysubs2.load(
        str(subtitle_file)
    )

    events = []

    total = len(subs)
    filtered = 0

    print(
        f"\nTotal subtitle event: {total}"
    )

    print(
        "\nMemfilter subtitle..."
    )

    for original_index, sub in enumerate(
        subs,
        start=1,
    ):

        should_skip, reason = (
            classify_subtitle_event(sub)
        )

        text = clean_subtitle_text(
            sub.text
        )

        if should_skip:

            filtered += 1

            print(
                f"[BUANG] "
                f"#{original_index:04d} | "
                f"Style={sub.style} | "
                f"{reason} | "
                f"{text[:100]}"
            )

            continue

        start = sub.start / 1000.0
        end = sub.end / 1000.0

        if end <= start:

            filtered += 1

            print(
                f"[BUANG] "
                f"#{original_index:04d} | "
                f"timestamp tidak valid"
            )

            continue

        events.append({
            "index": len(events) + 1,
            "original_index": original_index,
            "start": start,
            "end": end,
            "text": text,
            "style": sub.style or "",
        })

    print(
        "\n" + "=" * 60
    )

    print(
        "HASIL FILTER"
    )

    print(
        f"Total subtitle : {total}"
    )

    print(
        f"Dialog         : {len(events)}"
    )

    print(
        f"Dibuang        : {filtered}"
    )

    print(
        "=" * 60
    )

    return events


# POTONG VIDEO

def cut_video(
    video_file: Path,
    output_file: Path,
    start: float,
    end: float,
):
    """
    Memotong video berdasarkan timestamp subtitle.
    """

    duration = end - start

    command = [
        "ffmpeg",
        "-y",

        "-v", "error",

        "-ss",
        format_time(start),

        "-i",
        str(video_file),

        "-t",
        format_time(duration),

        # Video
        "-map",
        "0:v:0",
    ]

    # Audio asli MKV
    if not MUTE_EXPORTED_VIDEO:

        command += [
            "-map",
            "0:a?",
        ]

    command += [
        # Video encoding
        "-c:v",
        "libx264",

        "-preset",
        "medium",

        "-crf",
        "18",

        "-pix_fmt",
        "yuv420p",
    ]

    if not MUTE_EXPORTED_VIDEO:

        command += [
            "-c:a",
            "aac",

            "-b:a",
            "192k",
        ]

    else:

        command += [
            "-an",
        ]

    command += [
        "-movflags",
        "+faststart",

        str(output_file),
    ]

    run_command(command)


# POTONG AUDIO

def cut_audio(
    audio_file: Path,
    output_file: Path,
    start: float,
    end: float,
):
    """
    Memotong Audio_NBGM berdasarkan timestamp subtitle.
    """

    duration = end - start

    command = [
        "ffmpeg",
        "-y",

        "-v", "error",

        "-ss",
        format_time(start),

        "-i",
        str(audio_file),

        "-t",
        format_time(duration),

        "-vn",

        "-c:a",
        "libmp3lame",

        "-q:a",
        "2",

        str(output_file),
    ]

    run_command(command)


# PROSES SATU VIDEO

def process_one_file(
    number: int,
    video_file: Path,
    audio_file: Path,
):
    """
    Memproses:

        Video/{number}.mkv
        Audio_NBGM/{number}.mp3

    menjadi:

        Ekspor/{number}/
    """

    print("\n")
    print("=" * 80)
    print(f"MEMPROSES FILE #{number}")
    print("=" * 80)

    print(
        f"Video : {video_file}"
    )

    print(
        f"Audio : {audio_file}"
    )

    # Folder output

    output_dir = (
        EXPORT_DIR /
        str(number)
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Subtitle sementara

    subtitle_file = (
        output_dir /
        "_subtitle_temp.ass"
    )

    # Extract subtitle

    print(
        "\n[1/4] Mengekstrak subtitle..."
    )

    extract_subtitle(
        video_file,
        subtitle_file,
    )

    # Parse + filter subtitle

    print(
        "\n[2/4] Membaca dan memfilter subtitle..."
    )

    events = get_subtitle_events(
        subtitle_file
    )

    if not events:

        subtitle_file.unlink(
            missing_ok=True
        )

        print(
            "\nTidak ada dialog yang lolos filter."
        )

        return

    # Export

    print(
        "\n[3/4] Memotong video..."
    )

    for event in events:

        index = event["index"]

        start = event["start"]
        end = event["end"]
        text = event["text"]

        safe_text = sanitize_filename(
            text
        )

        base_name = (
            f"{index:03d}_"
            f"{safe_text}"
        )

        video_output = (
            output_dir /
            f"{base_name}.mp4"
        )

        audio_output = (
            output_dir /
            f"{base_name}.mp3"
        )

        print("\n" + "-" * 80)

        print(
            f"Dialog #{index}"
        )

        print(
            f"Original subtitle event: "
            f"#{event['original_index']}"
        )

        print(
            f"Style: {event['style']}"
        )

        print(
            f"Text : {text}"
        )

        print(
            f"Time : "
            f"{format_time(start)}"
            f" --> "
            f"{format_time(end)}"
        )

        # VIDEO
        print(
            "  [VIDEO] "
            f"{video_output.name}"
        )

        if video_output.exists():
            video_output.unlink()

        cut_video(
            video_file,
            video_output,
            start,
            end,
        )

        # AUDIO
        print(
            "  [AUDIO] "
            f"{audio_output.name}"
        )

        if audio_output.exists():
            audio_output.unlink()

        cut_audio(
            audio_file,
            audio_output,
            start,
            end,
        )

    # Hapus subtitle sementara

    print(
        "\n[4/4] Membersihkan file sementara..."
    )

    subtitle_file.unlink(
        missing_ok=True
    )

    print(
        "\n" + "=" * 80
    )

    print(
        f"SELESAI: {video_file.name}"
    )

    print(
        f"Jumlah clip: {len(events)}"
    )

    print(
        f"Output: {output_dir}"
    )

    print(
        "=" * 80
    )


# CARI FILE VIDEO
def get_video_files():
    """
    Mendapatkan semua MKV dengan nama angka:

        1.mkv
        2.mkv
        3.mkv

    File lain akan diabaikan.
    """

    files = []

    for file in VIDEO_DIR.glob("*.mkv"):

        if not file.stem.isdigit():

            print(
                f"[SKIP] Nama file bukan angka: "
                f"{file.name}"
            )

            continue

        files.append(file)

    files.sort(
        key=lambda p: int(p.stem)
    )

    return files



def main():

    print("=" * 80)
    print(
        "VIDEO + AUDIO CUTTER "
        "BERDASARKAN SUBTITLE"
    )
    print("=" * 80)

    # cek dependency

    print(
        "\nMemeriksa FFmpeg..."
    )

    check_program("ffmpeg")

    print(
        "Memeriksa FFprobe..."
    )

    check_program("ffprobe")

    # cek folder

    if not VIDEO_DIR.exists():

        print(
            "\nERROR:"
        )

        print(
            f"Folder tidak ditemukan:\n"
            f"{VIDEO_DIR}"
        )

        return

    if not AUDIO_DIR.exists():

        print(
            "\nERROR:"
        )

        print(
            f"Folder tidak ditemukan:\n"
            f"{AUDIO_DIR}"
        )

        return

    EXPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Get video

    video_files = get_video_files()

    if not video_files:

        print(
            "\nTidak ada file MKV yang ditemukan."
        )

        return

    print(
        f"\nDitemukan "
        f"{len(video_files)} file MKV."
    )

    # Process

    success = 0
    failed = 0
    skipped = 0

    for video_file in video_files:

        number = int(
            video_file.stem
        )

        audio_file = (
            AUDIO_DIR /
            f"{number}.mp3"
        )

        # Audio g ada

        if not audio_file.exists():

            print(
                "\n" + "!" * 80
            )

            print(
                f"[SKIP] Audio NBGM tidak ditemukan "
                f"untuk {number}.mkv"
            )

            print(
                f"Diharapkan:"
                f"\n{audio_file}"
            )

            print(
                "!" * 80
            )

            skipped += 1

            continue

        # Process

        try:

            process_one_file(
                number,
                video_file,
                audio_file,
            )

            success += 1

        except Exception as error:

            failed += 1

            print(
                "\n" + "!" * 80
            )

            print(
                f"ERROR saat memproses "
                f"{video_file.name}"
            )

            print(
                str(error)
            )

            print(
                "File berikutnya akan diproses."
            )

            print(
                "!" * 80
            )
    # Summary

    print(
        "\n\n" + "=" * 80
    )

    print(
        "SEMUA PROSES SELESAI"
    )

    print(
        "=" * 80
    )

    print(
        f"Berhasil : {success}"
    )

    print(
        f"Skip     : {skipped}"
    )

    print(
        f"Gagal    : {failed}"
    )

    print(
        f"\nFolder output:"
        f"\n{EXPORT_DIR}"
    )

    print(
        "=" * 80
    )


# ENTRY POINT

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print(
            "\n\nProses dibatalkan oleh pengguna."
        )

        sys.exit(1)

    except Exception as error:

        print(
            "\n\nFATAL ERROR:"
        )

        print(
            str(error)
        )

        sys.exit(1)