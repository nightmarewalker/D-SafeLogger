# Multiprocess Comparison Benchmark — v23a

- Generated: 2026-05-06 19:10:44 UTC
- Profile: **performance_profile**
- Messages per run: 500
- Repeats: 3
- Backends: D-SafeLogger, stdlib logging, loguru
- Patterns: root_p1, root_p4, root_p8, module_p4

## Environment

- OS: Windows 11
- Python: 3.14.3 (G:\マイドライブ\00_個人開発\pyDev\D-Logger\.venv\Scripts\python.exe)
- GIL: enabled
- CPU logical count: 16
- scratch_root: C:\TempX\D-SafeLogger-bench\benchmarks_multi_perf_20260506_190518

## Pattern Legend

- `root_p1`: 1 child -> root sink. Multiprocess IPC baseline without fan-in contention.
- `root_p4`: 4 children -> shared root sink. Moderate fan-in onto one parent writer.
- `root_p8`: 8 children -> shared root sink. High fan-in stress case for single-writer scaling.
- `module_p4`: 4 children -> module-specific route (bench.module) and dedicated module sink.

## Results

### Python 3.13

#### GIL enabled

##### text

| Pattern | Backend | Procs | Status | Runs | Throughput avg (min-max) | p50 (µs) | p90 (µs) | p99 (µs) | Delivered | IntegrityFail | Notes |
|---------|---------|------:|--------|------|--------------------------|--------:|--------:|--------:|----------:|-------------:|-------|
| root_p1 | D-SafeLogger | 1 | ok | 3/3 | 765 (744-779) | 24.9 | 28.1 | 47.0 | 500 | 0 |  |
| root_p1 | stdlib logging | 1 | ok | 3/3 | 1,235 (1,229-1,243) | 23.7 | 26.1 | 52.5 | 500 | 0 |  |
| root_p1 | loguru | 1 | ok | 3/3 | 960 (938-979) | 32.5 | 35.7 | 73.0 | 500 | 0 |  |
| root_p4 | D-SafeLogger | 4 | ok | 3/3 | 642 (630-652) | 25.3 | 33.8 | 89.7 | 500 | 0 |  |
| root_p4 | stdlib logging | 4 | ok | 3/3 | 1,138 (1,076-1,207) | 24.4 | 28.0 | 111.6 | 500 | 0 |  |
| root_p4 | loguru | 4 | ok | 3/3 | 859 (836-899) | 33.0 | 39.2 | 111.5 | 500 | 0 |  |
| root_p8 | D-SafeLogger | 8 | ok | 3/3 | 476 (463-483) | 30.5 | 59.0 | 500.8 | 500 | 0 |  |
| root_p8 | stdlib logging | 8 | ok | 3/3 | 852 (842-857) | 26.0 | 58.9 | 1750.9 | 500 | 0 |  |
| root_p8 | loguru | 8 | ok | 3/3 | 647 (625-687) | 39.3 | 80.3 | 2153.2 | 500 | 0 |  |
| module_p4 | D-SafeLogger | 4 | ok | 3/3 | 646 (620-664) | 25.3 | 35.2 | 84.1 | 500 | 0 |  |
| module_p4 | stdlib logging | 4 | ok | 3/3 | 1,112 (1,059-1,152) | 24.7 | 52.6 | 107.8 | 500 | 0 |  |
| module_p4 | loguru | 4 | ok | 3/3 | 862 (840-885) | 33.3 | 38.0 | 116.3 | 500 | 0 |  |

##### json

| Pattern | Backend | Procs | Status | Runs | Throughput avg (min-max) | p50 (µs) | p90 (µs) | p99 (µs) | Delivered | IntegrityFail | Notes |
|---------|---------|------:|--------|------|--------------------------|--------:|--------:|--------:|----------:|-------------:|-------|
| root_p1 | D-SafeLogger | 1 | ok | 3/3 | 782 (774-793) | 24.6 | 26.6 | 41.7 | 500 | 0 |  |
| root_p1 | stdlib logging | 1 | ok | 3/3 | 1,231 (1,213-1,244) | 24.1 | 27.4 | 56.7 | 500 | 0 |  |
| root_p1 | loguru | 1 | ok | 3/3 | 997 (987-1,008) | 32.6 | 38.0 | 74.0 | 500 | 0 |  |
| root_p4 | D-SafeLogger | 4 | ok | 3/3 | 661 (649-669) | 25.4 | 35.0 | 87.4 | 500 | 0 |  |
| root_p4 | stdlib logging | 4 | ok | 3/3 | 1,110 (1,085-1,150) | 25.2 | 44.6 | 118.9 | 500 | 0 |  |
| root_p4 | loguru | 4 | ok | 3/3 | 879 (838-916) | 34.5 | 40.8 | 124.5 | 500 | 0 |  |
| root_p8 | D-SafeLogger | 8 | ok | 3/3 | 472 (455-482) | 26.4 | 41.2 | 456.0 | 500 | 0 |  |
| root_p8 | stdlib logging | 8 | ok | 3/3 | 866 (835-883) | 27.3 | 58.5 | 1711.5 | 500 | 0 |  |
| root_p8 | loguru | 8 | ok | 3/3 | 667 (621-697) | 50.7 | 82.0 | 2025.4 | 500 | 0 |  |
| module_p4 | D-SafeLogger | 4 | ok | 3/3 | 625 (585-668) | 25.1 | 33.1 | 93.0 | 500 | 0 |  |
| module_p4 | stdlib logging | 4 | ok | 3/3 | 1,046 (985-1,088) | 26.0 | 50.7 | 130.8 | 500 | 0 |  |
| module_p4 | loguru | 4 | ok | 3/3 | 860 (837-903) | 33.3 | 41.3 | 118.0 | 500 | 0 |  |

#### GIL disabled

##### text

| Pattern | Backend | Procs | Status | Runs | Throughput avg (min-max) | p50 (µs) | p90 (µs) | p99 (µs) | Delivered | IntegrityFail | Notes |
|---------|---------|------:|--------|------|--------------------------|--------:|--------:|--------:|----------:|-------------:|-------|
| root_p1 | D-SafeLogger | 1 | ok | 3/3 | 807 (774-825) | 25.6 | 30.0 | 66.2 | 500 | 0 |  |
| root_p1 | stdlib logging | 1 | ok | 3/3 | 1,297 (1,291-1,301) | 25.1 | 30.9 | 65.9 | 500 | 0 |  |
| root_p1 | loguru | 1 | ok | 3/3 | 1,021 (1,002-1,033) | 34.8 | 55.7 | 83.1 | 500 | 0 |  |
| root_p4 | D-SafeLogger | 4 | ok | 3/3 | 644 (608-680) | 46.0 | 50.9 | 112.3 | 500 | 0 |  |
| root_p4 | stdlib logging | 4 | ok | 3/3 | 1,110 (1,095-1,119) | 24.7 | 32.2 | 99.7 | 500 | 0 |  |
| root_p4 | loguru | 4 | ok | 3/3 | 838 (798-890) | 35.5 | 60.7 | 146.9 | 500 | 0 |  |
| root_p8 | D-SafeLogger | 8 | ok | 3/3 | 467 (463-472) | 42.3 | 60.5 | 463.2 | 500 | 0 |  |
| root_p8 | stdlib logging | 8 | ok | 3/3 | 880 (861-892) | 38.9 | 77.0 | 1694.3 | 500 | 0 |  |
| root_p8 | loguru | 8 | ok | 3/3 | 670 (645-690) | 54.6 | 96.5 | 1997.4 | 500 | 0 |  |
| module_p4 | D-SafeLogger | 4 | ok | 3/3 | 627 (602-657) | 25.6 | 51.5 | 88.2 | 500 | 0 |  |
| module_p4 | stdlib logging | 4 | ok | 3/3 | 1,117 (1,088-1,137) | 25.3 | 41.9 | 127.0 | 500 | 0 |  |
| module_p4 | loguru | 4 | ok | 3/3 | 890 (840-928) | 35.5 | 64.0 | 137.8 | 500 | 0 |  |

##### json

| Pattern | Backend | Procs | Status | Runs | Throughput avg (min-max) | p50 (µs) | p90 (µs) | p99 (µs) | Delivered | IntegrityFail | Notes |
|---------|---------|------:|--------|------|--------------------------|--------:|--------:|--------:|----------:|-------------:|-------|
| root_p1 | D-SafeLogger | 1 | ok | 3/3 | 805 (786-818) | 25.2 | 31.1 | 57.2 | 500 | 0 |  |
| root_p1 | stdlib logging | 1 | ok | 3/3 | 1,234 (1,195-1,287) | 24.5 | 27.5 | 68.2 | 500 | 0 |  |
| root_p1 | loguru | 1 | ok | 3/3 | 1,028 (1,023-1,032) | 34.5 | 51.0 | 89.9 | 500 | 0 |  |
| root_p4 | D-SafeLogger | 4 | ok | 3/3 | 664 (623-687) | 26.8 | 57.7 | 121.0 | 500 | 0 |  |
| root_p4 | stdlib logging | 4 | ok | 3/3 | 1,159 (1,133-1,174) | 25.8 | 41.7 | 151.0 | 500 | 0 |  |
| root_p4 | loguru | 4 | ok | 3/3 | 882 (857-913) | 34.8 | 56.3 | 130.3 | 500 | 0 |  |
| root_p8 | D-SafeLogger | 8 | ok | 3/3 | 465 (444-480) | 35.3 | 61.3 | 415.4 | 500 | 0 |  |
| root_p8 | stdlib logging | 8 | ok | 3/3 | 853 (789-892) | 47.1 | 77.0 | 1715.5 | 500 | 0 |  |
| root_p8 | loguru | 8 | ok | 3/3 | 668 (623-695) | 60.9 | 102.8 | 2309.2 | 500 | 0 |  |
| module_p4 | D-SafeLogger | 4 | ok | 3/3 | 648 (640-658) | 25.5 | 54.6 | 114.2 | 500 | 0 |  |
| module_p4 | stdlib logging | 4 | ok | 3/3 | 1,113 (1,071-1,169) | 24.2 | 29.3 | 115.1 | 500 | 0 |  |
| module_p4 | loguru | 4 | ok | 3/3 | 890 (856-926) | 35.5 | 62.8 | 145.5 | 500 | 0 |  |

### Python 3.14

#### GIL enabled

##### text

| Pattern | Backend | Procs | Status | Runs | Throughput avg (min-max) | p50 (µs) | p90 (µs) | p99 (µs) | Delivered | IntegrityFail | Notes |
|---------|---------|------:|--------|------|--------------------------|--------:|--------:|--------:|----------:|-------------:|-------|
| root_p1 | D-SafeLogger | 1 | ok | 3/3 | 811 (810-812) | 19.3 | 21.2 | 33.2 | 500 | 0 |  |
| root_p1 | stdlib logging | 1 | ok | 3/3 | 1,293 (1,285-1,302) | 17.9 | 20.4 | 33.5 | 500 | 0 |  |
| root_p1 | loguru | 1 | ok | 3/3 | 998 (994-1,004) | 28.8 | 32.3 | 70.7 | 500 | 0 |  |
| root_p4 | D-SafeLogger | 4 | ok | 3/3 | 656 (654-658) | 19.6 | 22.4 | 90.8 | 500 | 0 |  |
| root_p4 | stdlib logging | 4 | ok | 3/3 | 1,109 (1,064-1,139) | 18.9 | 25.8 | 105.7 | 500 | 0 |  |
| root_p4 | loguru | 4 | ok | 3/3 | 861 (847-881) | 31.7 | 47.7 | 124.3 | 500 | 0 |  |
| root_p8 | D-SafeLogger | 8 | ok | 3/3 | 466 (450-482) | 25.1 | 48.9 | 543.7 | 500 | 0 |  |
| root_p8 | stdlib logging | 8 | ok | 3/3 | 817 (806-830) | 21.1 | 44.9 | 1115.8 | 500 | 0 |  |
| root_p8 | loguru | 8 | ok | 3/3 | 647 (620-669) | 40.7 | 71.9 | 1284.7 | 500 | 0 |  |
| module_p4 | D-SafeLogger | 4 | ok | 3/3 | 651 (636-661) | 19.4 | 22.5 | 80.9 | 500 | 0 |  |
| module_p4 | stdlib logging | 4 | ok | 3/3 | 1,113 (1,088-1,130) | 18.6 | 25.0 | 99.0 | 500 | 0 |  |
| module_p4 | loguru | 4 | ok | 3/3 | 895 (852-921) | 30.8 | 37.0 | 126.0 | 500 | 0 |  |

##### json

| Pattern | Backend | Procs | Status | Runs | Throughput avg (min-max) | p50 (µs) | p90 (µs) | p99 (µs) | Delivered | IntegrityFail | Notes |
|---------|---------|------:|--------|------|--------------------------|--------:|--------:|--------:|----------:|-------------:|-------|
| root_p1 | D-SafeLogger | 1 | ok | 3/3 | 802 (783-813) | 19.3 | 21.3 | 34.5 | 500 | 0 |  |
| root_p1 | stdlib logging | 1 | ok | 3/3 | 1,253 (1,206-1,276) | 17.9 | 19.4 | 35.0 | 500 | 0 |  |
| root_p1 | loguru | 1 | ok | 3/3 | 995 (993-998) | 29.0 | 33.6 | 89.0 | 500 | 0 |  |
| root_p4 | D-SafeLogger | 4 | ok | 3/3 | 640 (603-669) | 19.6 | 22.7 | 86.1 | 500 | 0 |  |
| root_p4 | stdlib logging | 4 | ok | 3/3 | 1,145 (1,077-1,193) | 18.9 | 33.0 | 99.6 | 500 | 0 |  |
| root_p4 | loguru | 4 | ok | 3/3 | 876 (837-902) | 30.0 | 35.5 | 121.3 | 500 | 0 |  |
| root_p8 | D-SafeLogger | 8 | ok | 3/3 | 459 (451-464) | 23.3 | 46.5 | 548.6 | 500 | 0 |  |
| root_p8 | stdlib logging | 8 | ok | 3/3 | 813 (759-847) | 33.4 | 51.3 | 1286.6 | 500 | 0 |  |
| root_p8 | loguru | 8 | ok | 3/3 | 632 (616-650) | 41.1 | 78.6 | 1268.5 | 500 | 0 |  |
| module_p4 | D-SafeLogger | 4 | ok | 3/3 | 646 (628-659) | 19.5 | 23.4 | 89.6 | 500 | 0 |  |
| module_p4 | stdlib logging | 4 | ok | 3/3 | 1,090 (1,007-1,143) | 19.3 | 41.4 | 153.0 | 500 | 0 |  |
| module_p4 | loguru | 4 | ok | 3/3 | 883 (851-914) | 30.0 | 40.1 | 126.1 | 500 | 0 |  |

#### GIL disabled

##### text

| Pattern | Backend | Procs | Status | Runs | Throughput avg (min-max) | p50 (µs) | p90 (µs) | p99 (µs) | Delivered | IntegrityFail | Notes |
|---------|---------|------:|--------|------|--------------------------|--------:|--------:|--------:|----------:|-------------:|-------|
| root_p1 | D-SafeLogger | 1 | ok | 3/3 | 806 (788-836) | 20.3 | 25.6 | 57.7 | 500 | 0 |  |
| root_p1 | stdlib logging | 1 | ok | 3/3 | 1,293 (1,285-1,306) | 19.8 | 24.4 | 53.0 | 500 | 0 |  |
| root_p1 | loguru | 1 | ok | 3/3 | 1,001 (974-1,027) | 31.1 | 46.2 | 77.9 | 500 | 0 |  |
| root_p4 | D-SafeLogger | 4 | ok | 3/3 | 669 (665-672) | 34.0 | 46.8 | 119.5 | 500 | 0 |  |
| root_p4 | stdlib logging | 4 | ok | 3/3 | 1,084 (1,036-1,144) | 20.6 | 45.1 | 117.0 | 500 | 0 |  |
| root_p4 | loguru | 4 | ok | 3/3 | 837 (810-861) | 32.0 | 52.9 | 139.5 | 500 | 0 |  |
| root_p8 | D-SafeLogger | 8 | ok | 3/3 | 465 (456-476) | 31.9 | 56.2 | 507.4 | 500 | 0 |  |
| root_p8 | stdlib logging | 8 | ok | 3/3 | 859 (844-874) | 39.6 | 70.5 | 1163.1 | 500 | 0 |  |
| root_p8 | loguru | 8 | ok | 3/3 | 637 (598-679) | 55.6 | 103.6 | 1370.3 | 500 | 0 |  |
| module_p4 | D-SafeLogger | 4 | ok | 3/3 | 653 (638-669) | 21.9 | 46.5 | 130.7 | 500 | 0 |  |
| module_p4 | stdlib logging | 4 | ok | 3/3 | 1,137 (1,101-1,180) | 22.1 | 50.4 | 136.1 | 500 | 0 |  |
| module_p4 | loguru | 4 | ok | 3/3 | 842 (802-893) | 34.0 | 81.8 | 196.6 | 500 | 0 |  |

##### json

| Pattern | Backend | Procs | Status | Runs | Throughput avg (min-max) | p50 (µs) | p90 (µs) | p99 (µs) | Delivered | IntegrityFail | Notes |
|---------|---------|------:|--------|------|--------------------------|--------:|--------:|--------:|----------:|-------------:|-------|
| root_p1 | D-SafeLogger | 1 | ok | 3/3 | 824 (821-827) | 20.2 | 22.7 | 50.0 | 500 | 0 |  |
| root_p1 | stdlib logging | 1 | ok | 3/3 | 1,295 (1,264-1,320) | 19.8 | 22.3 | 56.0 | 500 | 0 |  |
| root_p1 | loguru | 1 | ok | 3/3 | 1,016 (1,014-1,019) | 31.5 | 48.7 | 87.5 | 500 | 0 |  |
| root_p4 | D-SafeLogger | 4 | ok | 3/3 | 671 (660-684) | 22.3 | 51.8 | 99.5 | 500 | 0 |  |
| root_p4 | stdlib logging | 4 | ok | 3/3 | 1,123 (1,096-1,151) | 20.7 | 41.4 | 113.5 | 500 | 0 |  |
| root_p4 | loguru | 4 | ok | 3/3 | 857 (845-872) | 34.2 | 72.9 | 174.5 | 500 | 0 |  |
| root_p8 | D-SafeLogger | 8 | ok | 3/3 | 428 (409-454) | 40.6 | 67.8 | 559.5 | 500 | 0 |  |
| root_p8 | stdlib logging | 8 | ok | 3/3 | 676 (476-802) | 44.4 | 76.0 | 1216.2 | 500 | 0 |  |
| root_p8 | loguru | 8 | ok | 3/3 | 658 (629-685) | 50.6 | 92.8 | 1120.3 | 500 | 0 |  |
| module_p4 | D-SafeLogger | 4 | ok | 3/3 | 653 (642-663) | 27.4 | 49.4 | 133.6 | 500 | 0 |  |
| module_p4 | stdlib logging | 4 | ok | 3/3 | 1,087 (1,001-1,182) | 20.7 | 32.7 | 145.7 | 500 | 0 |  |
| module_p4 | loguru | 4 | ok | 3/3 | 878 (855-891) | 31.8 | 60.1 | 135.8 | 500 | 0 |  |
