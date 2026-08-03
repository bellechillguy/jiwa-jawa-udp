# Jiwa Jawa

Jiwa Jawa adalah permainan dam-daman 16 batu untuk dua pemain. Setiap pemain menjalankan program terpisah, lalu kedua program bertukar pesan melalui UDP.

Protokolnya menangani kehilangan dan duplikasi paket dengan nomor urut, ACK, CRC32, retransmisi, dan penyaringan paket duplikat.

Program hanya menggunakan pustaka standar Python 3.10. GUI dibuat dengan Tkinter, yang umumnya sudah tersedia pada instalasi Python desktop.

## Fitur yang tersedia

- Papan dam-daman dengan 37 titik dan 16 pion untuk setiap pemain.
- Gerakan satu ruas ke depan, ke samping, atau secara diagonal. Pion raja juga dapat bergerak mundur.
- Lompatan untuk memakan pion, promosi raja, kondisi menang, dan hukuman DAM sebanyak tiga pion.
- Dua program terpisah dengan peran host dan join.
- Protokol andal di atas UDP yang telah diuji dengan kehilangan paket 50%.
- GUI Tkinter dan mode terminal untuk server tanpa desktop.
- Pencatatan event melalui klaster Raft yang terdiri atas tiga proses dan menggunakan penyimpanan persisten.
- Perhitungan rating Elo dengan fungsi ekspektasi logistik.

## Mulai cepat

Buka folder repositori ini pada tiga terminal. Permainan tidak memerlukan paket Python tambahan.

Pada terminal pertama, jalankan klaster logger:

```bash
./scripts/start-logger-cluster.sh
```

Pada terminal kedua, jalankan pemain A sebagai host:

```bash
./scripts/run-game.sh \
  --host 0.0.0.0:9000 \
  --name "Pemain A"
```

Pada terminal ketiga, jalankan pemain B:

```bash
./scripts/run-game.sh \
  --join 127.0.0.1:9000 \
  --name "Pemain B"
```

Launcher akan mencari instalasi Python yang menyediakan Tkinter. Perilaku ini membantu pada macOS yang memiliki lebih dari satu instalasi Python.

Untuk bermain melalui dua komputer, ganti `127.0.0.1` dengan alamat IP komputer host. Pastikan firewall mengizinkan trafik UDP pada port `9000`. Tambahkan opsi `--cli` untuk menjalankan permainan tanpa GUI.

Setelah permainan selesai, hentikan klaster logger:

```bash
./scripts/stop-logger-cluster.sh
```

Script tersebut hanya menghentikan proses dan tidak menghapus data. Event tersimpan di `data/logger-N/events.jsonl`, sedangkan rating tersimpan di `data/logger-N/ratings.json`.

## Cara bermain melalui GUI

Pemain A menggunakan pion biru, sedangkan pemain B menggunakan pion merah.

Klik salah satu pion milik sendiri, lalu klik titik tujuan yang menyala. Titik hijau menandai langkah biasa. Titik emas menandai lompatan untuk memakan pion lawan.

Jika pemain memiliki kesempatan makan tetapi memilih langkah biasa, lawan memperoleh hak DAM. Pilih tiga pion lawan, kemudian tekan tombol `Ambil DAM`.

Pion yang mencapai garis terluar pada segitiga lawan berubah menjadi raja. GUI menandai pion tersebut dengan huruf `R`.

## Bermain melalui dua komputer

Secara default, host mengirim event ke logger pada port `9101`, `9102`, dan `9103` di komputer host.

Untuk memakai klaster logger pada alamat lain, berikan opsi `--logger` untuk setiap node:

```bash
./scripts/run-game.sh \
  --host 0.0.0.0:9000 \
  --name "Pemain A" \
  --logger 10.10.0.11:9101 \
  --logger 10.10.0.12:9102 \
  --logger 10.10.0.13:9103
```

Permainan tetap berjalan saat logger tidak dapat dihubungi. Event yang belum terkirim disimpan di `.jiwa-jawa/outbox-<match-id>.jsonl`.

Program akan mengirim ulang event tersebut sampai leader Raft mengonfirmasi bahwa event sudah di-commit.

## Melihat rating

Jalankan perintah berikut:

```bash
PYTHONPATH=. python3 -m jiwa_jawa.rating_cli
```

Setiap pemain memulai dengan rating `1200`. Perubahan rating menggunakan rumus Elo berikut:

```text
E_A = 1 / (1 + 10 ^ ((R_B - R_A) / 400))
R_A_baru = R_A_lama + 32 * (skor_A - E_A)
```

Nilai ekspektasi menggunakan fungsi pangkat, sehingga perubahan rating bersifat nonlinier.

## Menguji kehilangan paket 50%

Pada macOS dan Windows, pengujian dilakukan melalui container agar aturan jaringan tidak mengubah konfigurasi host. Pastikan Docker sedang aktif, lalu jalankan:

```bash
./scripts/test-netem.sh
```

Container memperoleh kapabilitas `NET_ADMIN`. Script kemudian menjalankan rangkaian berikut:

```bash
tc qdisc add dev lo root netem loss 50%
python -m unittest tests.test_protocol_netem -v
tc qdisc del dev lo root
```

Perintah untuk menghapus aturan netem ditempatkan di dalam `trap`. Aturan tersebut tetap dibersihkan jika pengujian gagal atau dihentikan.

Pada pengujian terakhir, status awal menunjukkan `qdisc netem ... loss 50%`. Seluruh 20 pesan tetap tiba, lalu status antarmuka kembali menjadi `qdisc noqueue` setelah pengujian selesai.

Pada Linux, aturan yang sama dapat dijalankan langsung pada host:

```bash
./scripts/netem-local.sh add lo
./scripts/netem-local.sh status lo
./scripts/netem-local.sh del lo
```

Hapus aturan netem setelah demo selesai, terutama jika aturan dipasang pada antarmuka jaringan yang masih digunakan.

## Menjalankan seluruh pengujian

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

Test suite mencakup:

- aturan papan;
- hukuman DAM;
- promosi raja;
- perhitungan rating;
- sinkronisasi dua program;
- kehilangan paket;
- commit mayoritas Raft; dan
- pemilihan leader baru setelah leader sebelumnya dihentikan.

## Berkas utama

```text
jiwa_jawa/board.py          engine dan aturan dam-daman
jiwa_jawa/protocol.py       ACK dan retransmisi di atas UDP
jiwa_jawa/controller.py     host otoritatif dan klien pemain B
jiwa_jawa/ui.py             GUI Tkinter
jiwa_jawa/cli.py            mode terminal tanpa Tkinter
jiwa_jawa/raft_logger.py    node logger Raft
jiwa_jawa/rating.py         perhitungan Elo
scripts/test-netem.sh       pengujian loss 50% dan pembersihan otomatis
```

Penjelasan format paket, state, dan alur Raft tersedia di [docs/PROTOCOL.md](docs/PROTOCOL.md).

Hasil pengujian dicatat di [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md).

Panduan penggunaan tersedia di [docs/panduan_jiwa_jawa.pdf](docs/panduan_jiwa_jawa.pdf).

## Referensi aturan

- [Dam-daman Jawa](https://id.wikibooks.org/wiki/Permainan_Tradisional_%22Catur%22_di_Indonesia/Dam-daman_(Jawa))
- [Netem](https://wiki.linuxfoundation.org/networking/netem)
- [Sistem rating Elo](https://en.wikipedia.org/wiki/Elo_rating_system)

## Video demo

[Video demo Jiwa Jawa](https://youtu.be/lS-BwKrTOSo)
