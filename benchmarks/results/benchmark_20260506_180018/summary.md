# Benchmark Session

Session: `benchmark_20260506_180018`

## Scope

- Generated: 2026-05-06 18:59:40 UTC
- Python versions: 3.13 and 3.14
- Interpreter builds: free-threaded executables with `PYTHON_GIL=1/0`
- GIL states: enabled and disabled
- Workloads: single-thread and multi-thread
- Scenarios: text and JSON
- Backends: D-SafeLogger, stdlib logging, loguru, structlog
- Modes: sync and async
- Messages per run: 100,000
- Measured runs per combination: 3
- Multi-thread worker count: 8
- Scratch output root: `C:\TempX\D-SafeLogger-bench\benchmark_20260506_180018`

## Recording Rules

- Throughput: multi-run average with min-max range
- `p50` / `p90` / `p99`: median of per-run percentile values
- Async / queue throughput is producer-side call-return throughput

## Runtime Matrix

| Python | GIL | Version | Runtime GIL | Build FT | Target Python | Raw Results |
|--------|-----|---------|-------------|----------|---------------|-------------|
| 3.13 | disabled | 3.13.12 | disabled | yes | `C:\Python\313\python3.13t.exe` | [`py313_gil_disabled.json`](benchmarks/results/benchmark_20260506_180018/raw/py313_gil_disabled.json) |
| 3.13 | enabled | 3.13.12 | enabled | yes | `C:\Python\313\python3.13t.exe` | [`py313_gil_enabled.json`](benchmarks/results/benchmark_20260506_180018/raw/py313_gil_enabled.json) |
| 3.14 | disabled | 3.14.3 | disabled | yes | `C:\Python\314\python3.14t.exe` | [`py314_gil_disabled.json`](benchmarks/results/benchmark_20260506_180018/raw/py314_gil_disabled.json) |
| 3.14 | enabled | 3.14.3 | enabled | yes | `C:\Python\314\python3.14t.exe` | [`py314_gil_enabled.json`](benchmarks/results/benchmark_20260506_180018/raw/py314_gil_enabled.json) |

## Python 3.13

### GIL enabled

#### single-thread

##### text

| Backend | Mode | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Notes |
|---------|------|--------|------|---------------------------|---------:|---------:|---------:|-------|
| D-SafeLogger | sync | ok | 3/3 | 23,674 (23,467-23,955) | 38.5 | 46.0 | 96.2 |  |
| D-SafeLogger | async | ok | 3/3 | 34,871 (34,700-35,015) | 20.7 | 23.9 | 50.3 |  |
| stdlib logging | sync | ok | 3/3 | 30,018 (29,716-30,499) | 30.9 | 34.1 | 71.4 |  |
| stdlib logging | async | ok | 3/3 | 34,817 (34,679-34,955) | 22.8 | 25.7 | 51.5 |  |
| loguru | sync | ok | 3/3 | 26,748 (26,461-27,180) | 34.7 | 39.3 | 79.1 |  |
| loguru | async | ok | 3/3 | 4,571 (4,546-4,613) | 206.9 | 258.4 | 339.0 |  |
| structlog | sync | ok | 3/3 | 32,352 (32,265-32,495) | 28.7 | 31.1 | 64.1 |  |
| structlog | async | ok | 3/3 | 3,648 (3,635-3,670) | 261.1 | 320.5 | 405.5 |  |

##### json

| Backend | Mode | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Notes |
|---------|------|--------|------|---------------------------|---------:|---------:|---------:|-------|
| D-SafeLogger | sync | ok | 3/3 | 20,242 (20,090-20,413) | 45.9 | 51.8 | 102.0 |  |
| D-SafeLogger | async | ok | 3/3 | 34,454 (32,917-35,525) | 20.8 | 23.8 | 49.0 |  |
| stdlib logging | sync | ok | 3/3 | 25,386 (25,335-25,479) | 36.8 | 40.1 | 83.5 |  |
| stdlib logging | async | ok | 3/3 | 34,572 (34,224-34,857) | 22.9 | 25.8 | 50.1 |  |
| loguru | sync | ok | 3/3 | 14,351 (13,636-14,729) | 63.2 | 76.4 | 144.3 |  |
| loguru | async | ok | 3/3 | 3,783 (3,736-3,821) | 248.5 | 307.3 | 400.7 |  |
| structlog | sync | ok | 3/3 | 26,765 (26,546-27,084) | 34.8 | 38.6 | 79.5 |  |
| structlog | async | ok | 3/3 | 3,439 (3,393-3,479) | 275.9 | 339.1 | 438.7 |  |

#### multi-thread

##### text

| Backend | Mode | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Notes |
|---------|------|--------|------|---------------------------|---------:|---------:|---------:|-------|
| D-SafeLogger | sync | ok | 3/3 | 6,747 (6,048-7,101) | 1104.0 | 1232.6 | 1516.6 |  |
| D-SafeLogger | async | ok | 3/3 | 8,709 (8,641-8,755) | 895.0 | 1077.5 | 1322.7 |  |
| stdlib logging | sync | ok | 3/3 | 7,837 (7,711-7,928) | 991.7 | 1123.1 | 1370.9 |  |
| stdlib logging | async | ok | 3/3 | 8,520 (8,445-8,597) | 909.7 | 1110.8 | 1405.8 |  |
| loguru | sync | ok | 3/3 | 11,448 (11,388-11,527) | 149.6 | 1409.5 | 1684.7 |  |
| loguru | async | ok | 3/3 | 3,585 (3,564-3,616) | 2190.7 | 2466.9 | 2910.0 |  |
| structlog | sync | ok | 3/3 | 12,022 (11,923-12,135) | 98.2 | 1426.1 | 1871.5 |  |
| structlog | async | ok | 3/3 | 3,229 (3,220-3,238) | 2444.2 | 2793.1 | 3319.0 |  |

##### json

| Backend | Mode | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Notes |
|---------|------|--------|------|---------------------------|---------:|---------:|---------:|-------|
| D-SafeLogger | sync | ok | 3/3 | 7,078 (6,416-8,300) | 1206.6 | 1328.2 | 1582.9 |  |
| D-SafeLogger | async | ok | 3/3 | 8,350 (7,843-9,306) | 981.8 | 1185.5 | 1451.6 |  |
| stdlib logging | sync | ok | 3/3 | 7,939 (7,085-9,545) | 1090.4 | 1228.7 | 1494.4 |  |
| stdlib logging | async | ok | 3/3 | 9,043 (8,465-9,403) | 806.3 | 967.6 | 1263.7 |  |
| loguru | sync | ok | 3/3 | 7,788 (7,753-7,812) | 1314.5 | 1952.5 | 2166.8 |  |
| loguru | async | ok | 3/3 | 3,165 (3,150-3,176) | 2483.4 | 2723.4 | 3135.4 |  |
| structlog | sync | ok | 3/3 | 10,851 (10,774-10,929) | 138.5 | 1459.1 | 1692.7 |  |
| structlog | async | ok | 3/3 | 3,102 (3,022-3,154) | 2517.6 | 2876.9 | 3495.3 |  |

### GIL disabled

#### single-thread

##### text

| Backend | Mode | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Notes |
|---------|------|--------|------|---------------------------|---------:|---------:|---------:|-------|
| D-SafeLogger | sync | ok | 3/3 | 24,301 (23,996-24,885) | 37.9 | 44.6 | 91.6 |  |
| D-SafeLogger | async | ok | 3/3 | 32,895 (32,516-33,634) | 24.7 | 46.2 | 84.7 |  |
| stdlib logging | sync | ok | 3/3 | 29,904 (29,450-30,284) | 30.9 | 34.0 | 72.1 |  |
| stdlib logging | async | ok | 3/3 | 29,623 (29,531-29,735) | 28.0 | 52.6 | 81.5 |  |
| loguru | sync | ok | 3/3 | 26,986 (26,753-27,278) | 34.5 | 38.5 | 77.5 |  |
| loguru | async | ok | 3/3 | 11,546 (11,341-11,774) | 77.2 | 104.2 | 186.5 |  |
| structlog | sync | ok | 3/3 | 32,560 (32,457-32,703) | 28.6 | 31.3 | 64.8 |  |
| structlog | async | ok | 3/3 | 4,480 (4,461-4,499) | 210.6 | 261.0 | 332.7 |  |

##### json

| Backend | Mode | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Notes |
|---------|------|--------|------|---------------------------|---------:|---------:|---------:|-------|
| D-SafeLogger | sync | ok | 3/3 | 20,433 (20,282-20,576) | 45.6 | 51.0 | 103.9 |  |
| D-SafeLogger | async | ok | 3/3 | 33,452 (33,093-33,797) | 23.4 | 45.3 | 72.0 |  |
| stdlib logging | sync | ok | 3/3 | 25,329 (25,163-25,550) | 36.7 | 40.5 | 86.3 |  |
| stdlib logging | async | ok | 3/3 | 30,477 (30,338-30,662) | 27.6 | 50.3 | 85.5 |  |
| loguru | sync | ok | 3/3 | 14,832 (14,666-14,929) | 62.7 | 74.1 | 140.5 |  |
| loguru | async | ok | 3/3 | 7,364 (7,238-7,466) | 124.9 | 153.6 | 244.8 |  |
| structlog | sync | ok | 3/3 | 26,679 (26,326-26,896) | 34.9 | 37.8 | 80.4 |  |
| structlog | async | ok | 3/3 | 4,240 (4,226-4,249) | 223.7 | 273.4 | 348.5 |  |

#### multi-thread

##### text

| Backend | Mode | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Notes |
|---------|------|--------|------|---------------------------|---------:|---------:|---------:|-------|
| D-SafeLogger | sync | ok | 3/3 | 17,508 (16,937-17,845) | 433.6 | 778.8 | 1349.0 |  |
| D-SafeLogger | async | ok | 3/3 | 34,280 (33,324-35,038) | 200.2 | 448.5 | 834.4 |  |
| stdlib logging | sync | ok | 3/3 | 23,986 (23,800-24,227) | 329.8 | 564.9 | 1013.3 |  |
| stdlib logging | async | ok | 3/3 | 28,610 (27,759-30,113) | 271.5 | 441.2 | 697.3 |  |
| loguru | sync | ok | 3/3 | 30,174 (29,721-30,427) | 261.6 | 408.3 | 783.0 |  |
| loguru | async | ok | 3/3 | 10,281 (10,166-10,372) | 754.5 | 961.0 | 1432.6 |  |
| structlog | sync | ok | 3/3 | 40,970 (40,528-41,281) | 187.3 | 369.5 | 672.9 |  |
| structlog | async | ok | 3/3 | 19,643 (17,801-21,186) | 371.8 | 513.9 | 777.0 |  |

##### json

| Backend | Mode | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Notes |
|---------|------|--------|------|---------------------------|---------:|---------:|---------:|-------|
| D-SafeLogger | sync | ok | 3/3 | 13,821 (13,715-13,973) | 557.9 | 654.2 | 849.1 |  |
| D-SafeLogger | async | ok | 3/3 | 34,078 (33,726-34,624) | 199.6 | 434.8 | 830.0 |  |
| stdlib logging | sync | ok | 3/3 | 17,916 (17,371-18,205) | 423.8 | 728.9 | 1152.1 |  |
| stdlib logging | async | ok | 3/3 | 32,359 (32,113-32,577) | 228.7 | 490.2 | 887.4 |  |
| loguru | sync | ok | 3/3 | 25,516 (25,248-25,731) | 307.2 | 509.2 | 825.2 |  |
| loguru | async | ok | 3/3 | 9,975 (9,799-10,223) | 795.5 | 1369.0 | 1668.9 |  |
| structlog | sync | ok | 3/3 | 38,981 (38,430-39,520) | 194.8 | 383.1 | 682.0 |  |
| structlog | async | ok | 3/3 | 18,290 (16,452-19,306) | 387.0 | 529.6 | 788.1 |  |

## Python 3.14

### GIL enabled

#### single-thread

##### text

| Backend | Mode | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Notes |
|---------|------|--------|------|---------------------------|---------:|---------:|---------:|-------|
| D-SafeLogger | sync | ok | 3/3 | 28,516 (27,996-28,778) | 32.4 | 36.0 | 72.6 |  |
| D-SafeLogger | async | ok | 3/3 | 51,554 (51,072-52,157) | 16.7 | 19.6 | 39.6 |  |
| stdlib logging | sync | ok | 3/3 | 37,228 (37,018-37,381) | 25.1 | 27.3 | 55.3 |  |
| stdlib logging | async | ok | 3/3 | 45,948 (45,274-46,545) | 18.6 | 21.5 | 41.5 |  |
| loguru | sync | ok | 3/3 | 29,640 (29,451-29,968) | 31.7 | 34.8 | 68.9 |  |
| loguru | async | ok | 3/3 | 4,637 (4,605-4,656) | 202.4 | 256.6 | 329.4 |  |
| structlog | sync | ok | 3/3 | 37,851 (37,484-38,455) | 24.6 | 27.1 | 55.9 |  |
| structlog | async | ok | 3/3 | 4,035 (4,022-4,046) | 235.8 | 293.1 | 367.2 |  |

##### json

| Backend | Mode | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Notes |
|---------|------|--------|------|---------------------------|---------:|---------:|---------:|-------|
| D-SafeLogger | sync | ok | 3/3 | 24,434 (24,297-24,512) | 38.1 | 42.4 | 87.1 |  |
| D-SafeLogger | async | ok | 3/3 | 52,081 (51,931-52,237) | 16.7 | 19.2 | 36.8 |  |
| stdlib logging | sync | ok | 3/3 | 30,553 (30,497-30,663) | 30.5 | 33.4 | 70.6 |  |
| stdlib logging | async | ok | 3/3 | 46,305 (46,095-46,499) | 18.5 | 21.2 | 41.5 |  |
| loguru | sync | ok | 3/3 | 15,732 (15,631-15,868) | 58.7 | 71.0 | 131.5 |  |
| loguru | async | ok | 3/3 | 3,879 (3,859-3,889) | 242.5 | 302.2 | 386.1 |  |
| structlog | sync | ok | 3/3 | 30,670 (30,642-30,695) | 30.5 | 33.4 | 69.2 |  |
| structlog | async | ok | 3/3 | 3,808 (3,722-3,855) | 248.7 | 305.2 | 384.4 |  |

#### multi-thread

##### text

| Backend | Mode | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Notes |
|---------|------|--------|------|---------------------------|---------:|---------:|---------:|-------|
| D-SafeLogger | sync | ok | 3/3 | 13,183 (13,139-13,233) | 74.0 | 1442.5 | 1620.9 |  |
| D-SafeLogger | async | ok | 3/3 | 29,231 (28,705-30,003) | 18.0 | 1209.1 | 1626.3 |  |
| stdlib logging | sync | ok | 3/3 | 16,849 (16,672-17,170) | 46.0 | 1558.0 | 2491.6 |  |
| stdlib logging | async | ok | 3/3 | 42,702 (42,258-43,001) | 19.6 | 23.3 | 59.0 |  |
| loguru | sync | ok | 3/3 | 13,801 (13,661-13,894) | 73.5 | 1464.0 | 1631.9 |  |
| loguru | async | ok | 3/3 | 3,633 (3,600-3,672) | 2149.5 | 2438.5 | 2911.8 |  |
| structlog | sync | ok | 3/3 | 17,146 (17,098-17,195) | 45.0 | 1551.1 | 2522.1 |  |
| structlog | async | ok | 3/3 | 3,477 (3,470-3,483) | 2270.2 | 2642.1 | 3296.4 |  |

##### json

| Backend | Mode | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Notes |
|---------|------|--------|------|---------------------------|---------:|---------:|---------:|-------|
| D-SafeLogger | sync | ok | 3/3 | 11,136 (11,123-11,150) | 1170.0 | 1434.3 | 1691.7 |  |
| D-SafeLogger | async | ok | 3/3 | 26,601 (24,718-28,043) | 18.1 | 1336.2 | 1788.1 |  |
| stdlib logging | sync | ok | 3/3 | 12,805 (12,568-13,021) | 78.2 | 1511.8 | 1827.8 |  |
| stdlib logging | async | ok | 3/3 | 42,658 (42,022-43,100) | 19.6 | 23.0 | 92.0 |  |
| loguru | sync | ok | 3/3 | 8,349 (8,320-8,389) | 1326.5 | 1862.8 | 2121.4 |  |
| loguru | async | ok | 3/3 | 3,107 (3,103-3,113) | 2532.7 | 2817.9 | 3215.3 |  |
| structlog | sync | ok | 3/3 | 12,653 (12,462-12,812) | 86.2 | 1527.7 | 1838.5 |  |
| structlog | async | ok | 3/3 | 3,277 (3,259-3,294) | 2404.5 | 2775.6 | 3356.3 |  |

### GIL disabled

#### single-thread

##### text

| Backend | Mode | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Notes |
|---------|------|--------|------|---------------------------|---------:|---------:|---------:|-------|
| D-SafeLogger | sync | ok | 3/3 | 28,599 (28,215-28,794) | 32.4 | 35.9 | 75.0 |  |
| D-SafeLogger | async | ok | 3/3 | 38,613 (38,381-38,935) | 20.7 | 42.2 | 75.2 |  |
| stdlib logging | sync | ok | 3/3 | 37,514 (37,015-38,130) | 24.8 | 27.3 | 56.6 |  |
| stdlib logging | async | ok | 3/3 | 37,403 (36,854-37,957) | 21.5 | 44.3 | 71.6 |  |
| loguru | sync | ok | 3/3 | 29,606 (29,092-30,023) | 31.5 | 34.6 | 68.3 |  |
| loguru | async | ok | 3/3 | 12,080 (11,965-12,138) | 73.0 | 105.3 | 183.5 |  |
| structlog | sync | ok | 3/3 | 37,213 (36,943-37,382) | 24.8 | 27.4 | 59.1 |  |
| structlog | async | ok | 3/3 | 4,777 (4,758-4,788) | 196.4 | 246.8 | 331.9 |  |

##### json

| Backend | Mode | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Notes |
|---------|------|--------|------|---------------------------|---------:|---------:|---------:|-------|
| D-SafeLogger | sync | ok | 3/3 | 23,639 (23,469-23,817) | 39.1 | 45.0 | 94.5 |  |
| D-SafeLogger | async | ok | 3/3 | 42,816 (42,298-43,147) | 19.3 | 38.3 | 62.2 |  |
| stdlib logging | sync | ok | 3/3 | 29,514 (28,803-30,006) | 30.6 | 36.0 | 76.3 |  |
| stdlib logging | async | ok | 3/3 | 39,050 (38,676-39,436) | 21.3 | 40.3 | 70.0 |  |
| loguru | sync | ok | 3/3 | 15,874 (15,793-15,936) | 58.5 | 70.8 | 131.5 |  |
| loguru | async | ok | 3/3 | 7,857 (7,813-7,910) | 118.0 | 145.1 | 231.9 |  |
| structlog | sync | ok | 3/3 | 30,656 (30,430-30,830) | 30.2 | 33.4 | 69.9 |  |
| structlog | async | ok | 3/3 | 4,844 (4,782-4,903) | 196.8 | 236.5 | 292.6 |  |

#### multi-thread

##### text

| Backend | Mode | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Notes |
|---------|------|--------|------|---------------------------|---------:|---------:|---------:|-------|
| D-SafeLogger | sync | ok | 3/3 | 18,217 (18,101-18,330) | 424.7 | 493.1 | 599.1 |  |
| D-SafeLogger | async | ok | 3/3 | 42,178 (41,451-42,841) | 175.8 | 411.2 | 863.6 |  |
| stdlib logging | sync | ok | 3/3 | 24,243 (24,055-24,367) | 320.9 | 382.2 | 647.1 |  |
| stdlib logging | async | ok | 3/3 | 34,394 (34,039-34,911) | 222.9 | 474.6 | 913.5 |  |
| loguru | sync | ok | 3/3 | 33,572 (33,359-33,965) | 244.0 | 353.1 | 1121.8 |  |
| loguru | async | ok | 3/3 | 10,627 (10,595-10,646) | 737.3 | 821.5 | 995.3 |  |
| structlog | sync | ok | 3/3 | 41,102 (40,843-41,400) | 201.0 | 309.9 | 608.0 |  |
| structlog | async | ok | 3/3 | 26,701 (26,344-27,011) | 281.4 | 360.2 | 538.2 |  |

##### json

| Backend | Mode | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Notes |
|---------|------|--------|------|---------------------------|---------:|---------:|---------:|-------|
| D-SafeLogger | sync | ok | 3/3 | 15,439 (15,188-15,570) | 499.7 | 571.6 | 669.8 |  |
| D-SafeLogger | async | ok | 3/3 | 41,334 (41,012-41,607) | 177.4 | 414.3 | 893.3 |  |
| stdlib logging | sync | ok | 3/3 | 19,190 (19,169-19,206) | 404.2 | 466.3 | 555.2 |  |
| stdlib logging | async | ok | 3/3 | 34,929 (34,495-35,507) | 217.2 | 483.5 | 913.7 |  |
| loguru | sync | ok | 3/3 | 27,937 (27,841-28,089) | 280.8 | 475.2 | 800.2 |  |
| loguru | async | ok | 3/3 | 10,048 (9,475-10,409) | 772.3 | 1320.2 | 1564.2 |  |
| structlog | sync | ok | 3/3 | 42,383 (42,115-42,636) | 179.7 | 364.0 | 661.4 |  |
| structlog | async | ok | 3/3 | 24,834 (24,687-25,049) | 305.7 | 389.9 | 544.1 |  |

## Results

- Combined summary JSON: [`benchmarks/results/benchmark_20260506_180018/summary.json`](benchmarks/results/benchmark_20260506_180018/summary.json)
- Raw environment JSON: [`benchmarks/results/benchmark_20260506_180018/raw/py313_gil_disabled.json`](benchmarks/results/benchmark_20260506_180018/raw/py313_gil_disabled.json)
- Raw environment JSON: [`benchmarks/results/benchmark_20260506_180018/raw/py313_gil_enabled.json`](benchmarks/results/benchmark_20260506_180018/raw/py313_gil_enabled.json)
- Raw environment JSON: [`benchmarks/results/benchmark_20260506_180018/raw/py314_gil_disabled.json`](benchmarks/results/benchmark_20260506_180018/raw/py314_gil_disabled.json)
- Raw environment JSON: [`benchmarks/results/benchmark_20260506_180018/raw/py314_gil_enabled.json`](benchmarks/results/benchmark_20260506_180018/raw/py314_gil_enabled.json)
