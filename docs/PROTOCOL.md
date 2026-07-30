# Protokol dan arsitektur

## Alur permainan

Host adalah sumber kebenaran state permainan. Pemain A menjalankan aksi langsung pada host. Pemain B mengirim pesan `action` yang memuat aksi dan nomor versi papan yang terakhir diterima. Host memvalidasi giliran, aturan langkah, dan versi tersebut. Setelah aksi sah dijalankan, host mengirim seluruh state terbaru ke pemain B.

Pengiriman seluruh state dipilih karena ukuran papan kecil. Cara ini juga memudahkan pemulihan jika client tertinggal beberapa aksi.

```text
Pemain A / Host                     Pemain B / Join
       |                                  |
       | <------ join + nama ------------ |
       | ------- welcome + state -------> |
       |                                  |
       | <------ action + version --------|
       | validasi dan ubah state           |
       | ------- state terbaru ---------->|
```

## Amplop ReliableUDP

Setiap pesan data memakai JSON berikut:

```json
{
  "version": 1,
  "kind": "data",
  "sequence": 17,
  "payload": {"type": "action"},
  "crc32": 123456789
}
```

Penerima menghitung ulang CRC32 sebelum membaca payload. Paket rusak dibuang. Paket yang sah segera dijawab dengan ACK berisi nomor urut yang sama. Jika ACK belum datang sebelum timeout, pengirim mengirim datagram yang sama. Penerima menyimpan nomor urut per alamat peer dan tidak memasukkan duplikat ke antrean aplikasi.

Sifat yang diperoleh:

- pesan yang belum mendapat ACK dikirim ulang;
- kerusakan payload terdeteksi oleh CRC32;
- retransmisi tidak menjalankan aksi dua kali;
- nomor urut terpisah untuk setiap peer;
- versi state mencegah aksi berbasis papan lama.

Ini adalah protokol buatan sendiri dengan semantik at-least-once pada jaringan dan exactly-once pada penyerahan ke aplikasi selama jendela deduplikasi aktif.

## Logging Raft

Proses game tidak membuka file log pertandingan. Ia mengirim event yang memiliki `event_id` unik ke tiga node logger. Jika logger belum menjawab, salinan event tetap berada di outbox host.

Node Raft menjalankan proses berikut:

1. Follower memulai pemilihan ketika heartbeat berhenti.
2. Candidate meminta suara dengan term dan posisi log terakhir.
3. Candidate yang mendapat suara mayoritas menjadi leader.
4. Leader menambahkan event client ke log lokal dan mengirim AppendEntries.
5. Event dianggap commit setelah tersimpan pada mayoritas node.
6. Setelah commit, setiap node menulis event ke `events.jsonl` dan memperbarui rating bila event adalah `game_ended`.

State yang dipersistenkan mencakup term, pilihan suara, isi log, commit index, dan last applied. Prefix log diperiksa dengan `prev_log_index` dan `prev_log_term`. Entri yang konflik dipotong sebelum entri leader disalin.

`event_id` dan `match_id` mencegah event serta hasil pertandingan diterapkan dua kali. Karena klaster berisi tiga node, satu node boleh mati tanpa menghentikan commit.

## Port bawaan

| Layanan | Transport | Port |
|---|---|---:|
| Permainan host | UDP | 9000 |
| Raft logger 1 | UDP | 9101 |
| Raft logger 2 | UDP | 9102 |
| Raft logger 3 | UDP | 9103 |

Port permainan dapat diubah lewat `--host`. Port logger dapat diubah lewat argumen script atau menjalankan `jiwa_jawa.raft_logger` secara langsung.

## Batas operasional

ReliableUDP dirancang untuk pesan state kecil dan tidak melakukan fragmentasi aplikasi. Payload dibatasi 60.000 byte. Nama pemain bukan identitas terautentikasi. Untuk jaringan publik, tambahkan autentikasi dan enkripsi sebelum pemakaian nyata.

