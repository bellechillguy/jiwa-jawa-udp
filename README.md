# Jiwa Jawa

Jiwa Jawa adalah permainan dam-daman 16 batu untuk dua pemain pada dua program berbeda. Kedua program bertukar pesan lewat UDP. Pengiriman dibuat andal dengan nomor urut, ACK, CRC32, retransmisi, dan pembuangan paket duplikat.

Program hanya memakai pustaka standar Python 3.10. Tkinter dipakai untuk GUI dan biasanya sudah ikut dalam instalasi Python desktop.

## Yang sudah dikerjakan

- Papan dam-daman 37 titik dengan 16 pion untuk setiap pemain.
- Gerak satu ruas ke depan, samping, atau diagonal. Raja boleh mundur.
- Lompatan makan, promosi raja, kondisi menang, dan hukuman DAM tiga pion.
- Dua program terpisah dalam peran host dan join.
- Protokol andal di atas UDP yang tetap lulus pada packet loss 50%.
- GUI Tkinter dan mode terminal untuk server tanpa desktop.
- Logging di klaster tiga proses terpisah dengan Raft dan penyimpanan persisten.
- Rating Elo dengan fungsi ekspektasi logistik.

## Mulai cepat

Masuk ke folder ini dari tiga terminal. Tidak ada paket yang perlu dipasang untuk menjalankan permainan.

Terminal pertama menjalankan klaster logger:

```bash
./scripts/start-logger-cluster.sh
```

Terminal kedua menjadi pemain A sekaligus host:

```bash
./scripts/run-game.sh \
  --host 0.0.0.0:9000 \
  --name "Pemain A"
```

Terminal ketiga menjadi pemain B:

```bash
./scripts/run-game.sh \
  --join 127.0.0.1:9000 \
  --name "Pemain B"
```

Launcher memilih instalasi Python yang mempunyai Tkinter. Ini berguna pada macOS yang memiliki beberapa Python sekaligus. Ganti `127.0.0.1` dengan alamat IP komputer host jika pemain berada pada dua komputer. Pastikan UDP port 9000 dapat dilewati firewall. Tambahkan `--cli` jika tidak ingin membuka GUI.

Setelah selesai:

```bash
./scripts/stop-logger-cluster.sh
```

Script penghenti tidak menghapus log. Event tersimpan di `data/logger-N/events.jsonl`, sedangkan rating ada di `data/logger-N/ratings.json`.

## Cara bermain di GUI

Warna biru adalah pemain A dan merah adalah pemain B. Klik pion sendiri, lalu klik titik tujuan yang menyala. Titik hijau berarti langkah biasa. Titik emas berarti lompatan makan.

Jika ada kesempatan makan tetapi pemain memilih langkah biasa, lawan mendapat hak DAM. Pilih tiga pion lawan dan tekan tombol `Ambil DAM`. Pion yang mencapai garis terluar segitiga lawan berubah menjadi raja, ditandai huruf `R`.

## Dua komputer dan logger jarak jauh

Secara bawaan, host mengirim log ke port 9101, 9102, dan 9103 pada komputer host. Untuk klaster yang berjalan pada alamat lain, ulangi opsi `--logger`:

```bash
./scripts/run-game.sh \
  --host 0.0.0.0:9000 \
  --name Pemain A \
  --logger 10.10.0.11:9101 \
  --logger 10.10.0.12:9102 \
  --logger 10.10.0.13:9103
```

Game tetap berjalan ketika logger sementara tidak dapat dihubungi. Event menunggu di `.jiwa-jawa/outbox-<match-id>.jsonl` dan dikirim ulang sampai leader Raft mengonfirmasi commit.

## Melihat rating

```bash
PYTHONPATH=. python3 -m jiwa_jawa.rating_cli
```

Rating awal adalah 1200. Perubahan rating memakai kurva ekspektasi Elo:

```text
E_A = 1 / (1 + 10 ^ ((R_B - R_A) / 400))
R_A_baru = R_A_lama + 32 * (skor_A - E_A)
```

Fungsi pangkat pada nilai ekspektasi membuat perhitungannya non-linear.

## Uji packet loss 50%

Cara yang paling aman di macOS atau Windows adalah container. Docker harus aktif.

```bash
./scripts/test-netem.sh
```

Container mendapat kapabilitas `NET_ADMIN`, lalu script menjalankan:

```bash
tc qdisc add dev lo root netem loss 50%
python -m unittest tests.test_protocol_netem -v
tc qdisc del dev lo root
```

Penghapusan rule berada di dalam `trap`, sehingga tetap dijalankan jika tes gagal atau dihentikan. Pengujian terakhir menghasilkan `qdisc netem ... loss 50%`, seluruh 20 pesan tiba, lalu status akhir kembali menjadi `qdisc noqueue`.

Pada Linux native, rule dapat diatur dengan:

```bash
./scripts/netem-local.sh add lo
./scripts/netem-local.sh status lo
./scripts/netem-local.sh del lo
```

Jangan meninggalkan rule netem pada interface yang dipakai setelah demo.

## Menjalankan seluruh tes

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

Suite menguji aturan papan, hukuman DAM, promosi, rating, sinkronisasi dua program, packet loss, commit mayoritas Raft, dan pemilihan leader baru setelah leader lama dimatikan.

## Isi penting repository

```text
jiwa_jawa/board.py          engine dan aturan dam-daman
jiwa_jawa/protocol.py       protokol ACK dan retransmisi di atas UDP
jiwa_jawa/controller.py     host otoritatif dan client pemain B
jiwa_jawa/ui.py             GUI Tkinter
jiwa_jawa/cli.py            mode terminal tanpa ketergantungan Tkinter
jiwa_jawa/raft_logger.py    node logger Raft
jiwa_jawa/rating.py         perhitungan Elo logistik
scripts/test-netem.sh       bukti loss 50% dan cleanup otomatis
```

Penjelasan packet, state, dan alur Raft ada di [docs/PROTOCOL.md](docs/PROTOCOL.md). Bukti pengujian dicatat di [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md). Dokumen penggunaan ada di [docs/panduan-jiwa-jawa.pdf](docs/panduan-jiwa-jawa.pdf).


## Referensi aturan

- Dam-daman Jawa: https://id.wikibooks.org/wiki/Permainan_Tradisional_%22Catur%22_di_Indonesia/Dam-daman_(Jawa)
- Netem: https://wiki.linuxfoundation.org/networking/netem
- Elo: https://en.wikipedia.org/wiki/Elo_rating_system
