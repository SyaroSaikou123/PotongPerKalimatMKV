# PotongPerKalimatMKV

Alat buat motong klip anime BD berdasarkan kalimat untuk membuat sentencing/dialog otoMAD.

<img width="616" height="612" alt="image" src="https://github.com/user-attachments/assets/ef0d6134-38a5-4623-95f8-b36ca0943016" />

## Yang diperlukan:
- Anime BD (format .MKV dengan subtitle di dalamnya (kecuali format .sub))
- Audio yang telah dihapus BGMnya (rekomendasi)
- FFmpeg

## Persiapan:
- Folder "Video" .mkv ke dalam folder "Video" dengan nama file berdasarkan urutan episode (mis. 1.mkv; 2.mkv; 3.mkv).
- Folder "Audio_NBGM" berisi audio yang telah dihapus BGM-nya.
- Folder "Ekspor" adalah folder keluaran.

## Cara pemakaian
Pasang library pysubs2 (kalau belum)
`` python -m pip install pysubs2 ``

Kalo udah tinggal run aja
`` python Split_Subtitle.py ``
