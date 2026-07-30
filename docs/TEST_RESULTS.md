# Hasil pengujian

Pengujian ini dijalankan pada 22 Juli 2026.

## Unit dan integration test

Perintah:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

Hasil: 11 tes lulus. Suite mencakup aturan papan, promosi, DAM, rating, sinkronisasi dua controller, pengiriman dengan loss sintetis 50%, serta klaster Raft. Tes Raft mematikan leader setelah commit pertama, menunggu pemilihan leader baru, lalu melakukan commit kedua pada dua node yang tersisa.

```text
Ran 11 tests in 3.686s
OK
```

## tc-netem loss 50%

Perintah:

```bash
./scripts/test-netem.sh
```

Rule di dalam container sebelum tes:

```text
qdisc netem 8001: root refcnt 2 limit 1000 loss 50%
```

ReliableUDP mengirim 20 pesan melalui loopback yang terkena rule tersebut. Semua pesan tiba sekali dan tes lulus.

```text
test_messages_survive_kernel_packet_loss ... ok
Ran 1 test in 2.157s
OK
```

Rule dihapus oleh trap. Pemeriksaan terakhir menunjukkan loopback kembali normal:

```text
qdisc noqueue 0: root refcnt 2
```
