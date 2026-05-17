# Multiprocess Integrity Profile Summary

- Latest session: `benchmarks_multi_integ_20260506_185947`
- Artifacts: [`benchmarks/results/benchmarks_multi_integ_20260506_185947/summary.md`](../results/benchmarks_multi_integ_20260506_185947/summary.md), [`benchmarks/results/benchmarks_multi_integ_20260506_185947/summary.json`](../results/benchmarks_multi_integ_20260506_185947/summary.json)
- Integrity summary rows: 96. Bad rows: 0.
- Raw runs: 288. Non-ok runs: 0.
- Aggregate delivery anomalies: missing=0, duplicates=0.

| Backend | Raw Runs | Failures | Missing | Duplicates | JSON Parse | Route Mismatch |
|---------|---------:|---------:|--------:|-----------:|-----------:|---------------:|
| D-SafeLogger | 96 | 0 | 0 | 0 | 0 | 0 |
| loguru | 96 | 0 | 0 | 0 | 0 | 0 |
| stdlib logging | 96 | 0 | 0 | 0 | 0 | 0 |

#### Python 3.13

##### GIL enabled

###### text

| Pattern | Backend | Mode | Procs | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Delivered | IntegrityFail | Notes |
|---------|---------|------|------:|--------|------|---------------------------|---------:|---------:|---------:|----------:|--------------:|-------|
| root_p1 | D-SafeLogger | sync | 1 | ok | 3/3 | 764 (752-781) | 24.6 | 28.0 | 60.4 | 500 | 0 |  |
| root_p1 | stdlib logging | sync | 1 | ok | 3/3 | 1,233 (1,210-1,245) | 23.6 | 28.3 | 57.0 | 500 | 0 |  |
| root_p1 | loguru | sync | 1 | ok | 3/3 | 884 (776-962) | 32.5 | 36.9 | 72.6 | 500 | 0 |  |
| root_p4 | D-SafeLogger | sync | 4 | ok | 3/3 | 635 (599-662) | 25.4 | 34.5 | 98.8 | 500 | 0 |  |
| root_p4 | stdlib logging | sync | 4 | ok | 3/3 | 1,076 (1,031-1,127) | 24.6 | 44.5 | 99.6 | 500 | 0 |  |
| root_p4 | loguru | sync | 4 | ok | 3/3 | 854 (847-860) | 34.7 | 59.8 | 116.3 | 500 | 0 |  |
| root_p8 | D-SafeLogger | sync | 8 | ok | 3/3 | 472 (470-476) | 27.1 | 52.2 | 456.8 | 500 | 0 |  |
| root_p8 | stdlib logging | sync | 8 | ok | 3/3 | 880 (873-894) | 29.4 | 63.1 | 1758.8 | 500 | 0 |  |
| root_p8 | loguru | sync | 8 | ok | 3/3 | 668 (647-688) | 51.2 | 88.5 | 2095.3 | 500 | 0 |  |
| module_p4 | D-SafeLogger | sync | 4 | ok | 3/3 | 649 (640-657) | 25.3 | 34.7 | 95.3 | 500 | 0 |  |
| module_p4 | stdlib logging | sync | 4 | ok | 3/3 | 1,084 (1,069-1,092) | 24.5 | 30.4 | 115.2 | 500 | 0 |  |
| module_p4 | loguru | sync | 4 | ok | 3/3 | 837 (822-852) | 34.7 | 64.0 | 152.5 | 500 | 0 |  |

###### json

| Pattern | Backend | Mode | Procs | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Delivered | IntegrityFail | Notes |
|---------|---------|------|------:|--------|------|---------------------------|---------:|---------:|---------:|----------:|--------------:|-------|
| root_p1 | D-SafeLogger | sync | 1 | ok | 3/3 | 784 (777-792) | 25.0 | 27.2 | 44.2 | 500 | 0 |  |
| root_p1 | stdlib logging | sync | 1 | ok | 3/3 | 1,222 (1,181-1,255) | 23.7 | 25.7 | 42.0 | 500 | 0 |  |
| root_p1 | loguru | sync | 1 | ok | 3/3 | 986 (980-991) | 32.4 | 35.8 | 64.4 | 500 | 0 |  |
| root_p4 | D-SafeLogger | sync | 4 | ok | 3/3 | 646 (640-658) | 26.0 | 43.7 | 98.5 | 500 | 0 |  |
| root_p4 | stdlib logging | sync | 4 | ok | 3/3 | 1,115 (1,083-1,134) | 24.9 | 40.3 | 120.6 | 500 | 0 |  |
| root_p4 | loguru | sync | 4 | ok | 3/3 | 828 (817-848) | 33.7 | 47.9 | 145.4 | 500 | 0 |  |
| root_p8 | D-SafeLogger | sync | 8 | ok | 3/3 | 467 (448-478) | 32.7 | 57.0 | 492.7 | 500 | 0 |  |
| root_p8 | stdlib logging | sync | 8 | ok | 3/3 | 839 (763-879) | 37.0 | 62.1 | 1867.6 | 500 | 0 |  |
| root_p8 | loguru | sync | 8 | ok | 3/3 | 683 (678-691) | 35.8 | 68.3 | 1962.3 | 500 | 0 |  |
| module_p4 | D-SafeLogger | sync | 4 | ok | 3/3 | 650 (625-663) | 26.2 | 46.1 | 92.2 | 500 | 0 |  |
| module_p4 | stdlib logging | sync | 4 | ok | 3/3 | 1,093 (1,011-1,134) | 24.4 | 30.5 | 103.0 | 500 | 0 |  |
| module_p4 | loguru | sync | 4 | ok | 3/3 | 889 (882-894) | 33.2 | 39.2 | 116.9 | 500 | 0 |  |

##### GIL disabled

###### text

| Pattern | Backend | Mode | Procs | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Delivered | IntegrityFail | Notes |
|---------|---------|------|------:|--------|------|---------------------------|---------:|---------:|---------:|----------:|--------------:|-------|
| root_p1 | D-SafeLogger | sync | 1 | ok | 3/3 | 807 (786-829) | 25.5 | 31.4 | 72.2 | 500 | 0 |  |
| root_p1 | stdlib logging | sync | 1 | ok | 3/3 | 1,296 (1,279-1,311) | 25.1 | 28.4 | 57.9 | 500 | 0 |  |
| root_p1 | loguru | sync | 1 | ok | 3/3 | 1,017 (993-1,037) | 35.5 | 56.6 | 101.5 | 500 | 0 |  |
| root_p4 | D-SafeLogger | sync | 4 | ok | 3/3 | 671 (664-678) | 25.3 | 29.7 | 100.1 | 500 | 0 |  |
| root_p4 | stdlib logging | sync | 4 | ok | 3/3 | 1,151 (1,129-1,171) | 25.0 | 41.3 | 115.0 | 500 | 0 |  |
| root_p4 | loguru | sync | 4 | ok | 3/3 | 865 (840-904) | 46.9 | 70.3 | 171.7 | 500 | 0 |  |
| root_p8 | D-SafeLogger | sync | 8 | ok | 3/3 | 423 (342-473) | 45.7 | 63.7 | 492.5 | 500 | 0 |  |
| root_p8 | stdlib logging | sync | 8 | ok | 3/3 | 794 (763-819) | 44.8 | 81.1 | 1889.8 | 500 | 0 |  |
| root_p8 | loguru | sync | 8 | ok | 3/3 | 663 (615-699) | 49.6 | 103.0 | 2114.5 | 500 | 0 |  |
| module_p4 | D-SafeLogger | sync | 4 | ok | 3/3 | 636 (610-656) | 25.5 | 38.3 | 101.7 | 500 | 0 |  |
| module_p4 | stdlib logging | sync | 4 | ok | 3/3 | 1,082 (1,028-1,116) | 25.5 | 51.3 | 135.0 | 500 | 0 |  |
| module_p4 | loguru | sync | 4 | ok | 3/3 | 871 (838-901) | 34.0 | 54.0 | 149.5 | 500 | 0 |  |

###### json

| Pattern | Backend | Mode | Procs | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Delivered | IntegrityFail | Notes |
|---------|---------|------|------:|--------|------|---------------------------|---------:|---------:|---------:|----------:|--------------:|-------|
| root_p1 | D-SafeLogger | sync | 1 | ok | 3/3 | 813 (805-824) | 25.3 | 28.3 | 42.2 | 500 | 0 |  |
| root_p1 | stdlib logging | sync | 1 | ok | 3/3 | 1,294 (1,282-1,308) | 24.3 | 27.3 | 57.5 | 500 | 0 |  |
| root_p1 | loguru | sync | 1 | ok | 3/3 | 1,027 (1,015-1,040) | 34.8 | 56.2 | 90.5 | 500 | 0 |  |
| root_p4 | D-SafeLogger | sync | 4 | ok | 3/3 | 651 (638-673) | 25.4 | 33.3 | 105.1 | 500 | 0 |  |
| root_p4 | stdlib logging | sync | 4 | ok | 3/3 | 1,110 (1,067-1,182) | 25.3 | 35.6 | 131.7 | 500 | 0 |  |
| root_p4 | loguru | sync | 4 | ok | 3/3 | 859 (837-886) | 33.0 | 43.1 | 147.2 | 500 | 0 |  |
| root_p8 | D-SafeLogger | sync | 8 | ok | 3/3 | 455 (428-473) | 31.5 | 62.2 | 440.2 | 500 | 0 |  |
| root_p8 | stdlib logging | sync | 8 | ok | 3/3 | 866 (814-900) | 44.4 | 75.4 | 1695.7 | 500 | 0 |  |
| root_p8 | loguru | sync | 8 | ok | 3/3 | 676 (658-689) | 62.1 | 100.1 | 1878.8 | 500 | 0 |  |
| module_p4 | D-SafeLogger | sync | 4 | ok | 3/3 | 651 (638-664) | 26.7 | 61.3 | 130.8 | 500 | 0 |  |
| module_p4 | stdlib logging | sync | 4 | ok | 3/3 | 1,137 (1,050-1,185) | 25.3 | 36.2 | 115.8 | 500 | 0 |  |
| module_p4 | loguru | sync | 4 | ok | 3/3 | 869 (848-901) | 33.3 | 43.4 | 159.0 | 500 | 0 |  |

#### Python 3.14

##### GIL enabled

###### text

| Pattern | Backend | Mode | Procs | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Delivered | IntegrityFail | Notes |
|---------|---------|------|------:|--------|------|---------------------------|---------:|---------:|---------:|----------:|--------------:|-------|
| root_p1 | D-SafeLogger | sync | 1 | ok | 3/3 | 797 (788-802) | 19.1 | 21.8 | 32.5 | 500 | 0 |  |
| root_p1 | stdlib logging | sync | 1 | ok | 3/3 | 1,282 (1,275-1,286) | 17.6 | 18.8 | 33.8 | 500 | 0 |  |
| root_p1 | loguru | sync | 1 | ok | 3/3 | 966 (939-1,003) | 29.1 | 32.0 | 50.4 | 500 | 0 |  |
| root_p4 | D-SafeLogger | sync | 4 | ok | 3/3 | 662 (656-673) | 19.6 | 23.1 | 84.8 | 500 | 0 |  |
| root_p4 | stdlib logging | sync | 4 | ok | 3/3 | 1,105 (1,040-1,140) | 18.9 | 24.1 | 109.4 | 500 | 0 |  |
| root_p4 | loguru | sync | 4 | ok | 3/3 | 889 (849-916) | 31.3 | 40.6 | 122.6 | 500 | 0 |  |
| root_p8 | D-SafeLogger | sync | 8 | ok | 3/3 | 476 (471-479) | 23.7 | 42.3 | 572.8 | 500 | 0 |  |
| root_p8 | stdlib logging | sync | 8 | ok | 3/3 | 786 (756-814) | 28.6 | 47.8 | 1271.8 | 500 | 0 |  |
| root_p8 | loguru | sync | 8 | ok | 3/3 | 653 (615-694) | 46.4 | 70.1 | 1272.9 | 500 | 0 |  |
| module_p4 | D-SafeLogger | sync | 4 | ok | 3/3 | 654 (628-672) | 19.8 | 47.0 | 129.4 | 500 | 0 |  |
| module_p4 | stdlib logging | sync | 4 | ok | 3/3 | 1,094 (1,070-1,121) | 18.4 | 24.8 | 91.2 | 500 | 0 |  |
| module_p4 | loguru | sync | 4 | ok | 3/3 | 877 (853-908) | 30.3 | 46.9 | 123.9 | 500 | 0 |  |

###### json

| Pattern | Backend | Mode | Procs | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Delivered | IntegrityFail | Notes |
|---------|---------|------|------:|--------|------|---------------------------|---------:|---------:|---------:|----------:|--------------:|-------|
| root_p1 | D-SafeLogger | sync | 1 | ok | 3/3 | 812 (807-815) | 19.2 | 21.5 | 69.2 | 500 | 0 |  |
| root_p1 | stdlib logging | sync | 1 | ok | 3/3 | 1,248 (1,194-1,290) | 17.9 | 19.5 | 33.8 | 500 | 0 |  |
| root_p1 | loguru | sync | 1 | ok | 3/3 | 1,001 (999-1,002) | 28.7 | 31.7 | 54.2 | 500 | 0 |  |
| root_p4 | D-SafeLogger | sync | 4 | ok | 3/3 | 681 (665-695) | 19.7 | 23.6 | 86.9 | 500 | 0 |  |
| root_p4 | stdlib logging | sync | 4 | ok | 3/3 | 1,125 (1,065-1,159) | 18.9 | 28.8 | 104.0 | 500 | 0 |  |
| root_p4 | loguru | sync | 4 | ok | 3/3 | 865 (845-877) | 29.9 | 36.0 | 129.3 | 500 | 0 |  |
| root_p8 | D-SafeLogger | sync | 8 | ok | 3/3 | 457 (425-479) | 27.6 | 47.1 | 581.0 | 500 | 0 |  |
| root_p8 | stdlib logging | sync | 8 | ok | 3/3 | 800 (769-847) | 30.8 | 48.5 | 1261.8 | 500 | 0 |  |
| root_p8 | loguru | sync | 8 | ok | 3/3 | 655 (644-669) | 35.4 | 73.2 | 1305.2 | 500 | 0 |  |
| module_p4 | D-SafeLogger | sync | 4 | ok | 3/3 | 669 (661-678) | 19.4 | 22.8 | 105.0 | 500 | 0 |  |
| module_p4 | stdlib logging | sync | 4 | ok | 3/3 | 1,128 (1,058-1,185) | 19.1 | 26.6 | 108.9 | 500 | 0 |  |
| module_p4 | loguru | sync | 4 | ok | 3/3 | 845 (829-862) | 30.6 | 36.7 | 126.4 | 500 | 0 |  |

##### GIL disabled

###### text

| Pattern | Backend | Mode | Procs | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Delivered | IntegrityFail | Notes |
|---------|---------|------|------:|--------|------|---------------------------|---------:|---------:|---------:|----------:|--------------:|-------|
| root_p1 | D-SafeLogger | sync | 1 | ok | 3/3 | 829 (827-830) | 20.3 | 23.1 | 52.8 | 500 | 0 |  |
| root_p1 | stdlib logging | sync | 1 | ok | 3/3 | 1,314 (1,308-1,320) | 20.2 | 24.8 | 55.9 | 500 | 0 |  |
| root_p1 | loguru | sync | 1 | ok | 3/3 | 1,012 (996-1,021) | 31.3 | 50.9 | 109.2 | 500 | 0 |  |
| root_p4 | D-SafeLogger | sync | 4 | ok | 3/3 | 672 (664-676) | 21.7 | 41.0 | 93.7 | 500 | 0 |  |
| root_p4 | stdlib logging | sync | 4 | ok | 3/3 | 1,086 (1,051-1,156) | 34.2 | 57.8 | 141.0 | 500 | 0 |  |
| root_p4 | loguru | sync | 4 | ok | 3/3 | 923 (922-924) | 32.4 | 54.1 | 163.9 | 500 | 0 |  |
| root_p8 | D-SafeLogger | sync | 8 | ok | 3/3 | 474 (464-487) | 34.3 | 57.4 | 509.5 | 500 | 0 |  |
| root_p8 | stdlib logging | sync | 8 | ok | 3/3 | 830 (808-845) | 41.8 | 72.5 | 1204.1 | 500 | 0 |  |
| root_p8 | loguru | sync | 8 | ok | 3/3 | 664 (653-682) | 56.9 | 93.8 | 1225.2 | 500 | 0 |  |
| module_p4 | D-SafeLogger | sync | 4 | ok | 3/3 | 674 (667-686) | 19.8 | 40.6 | 108.9 | 500 | 0 |  |
| module_p4 | stdlib logging | sync | 4 | ok | 3/3 | 1,153 (1,133-1,169) | 21.2 | 44.7 | 113.0 | 500 | 0 |  |
| module_p4 | loguru | sync | 4 | ok | 3/3 | 872 (867-879) | 33.1 | 67.8 | 124.3 | 500 | 0 |  |

###### json

| Pattern | Backend | Mode | Procs | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Delivered | IntegrityFail | Notes |
|---------|---------|------|------:|--------|------|---------------------------|---------:|---------:|---------:|----------:|--------------:|-------|
| root_p1 | D-SafeLogger | sync | 1 | ok | 3/3 | 832 (823-839) | 20.1 | 23.0 | 57.2 | 500 | 0 |  |
| root_p1 | stdlib logging | sync | 1 | ok | 3/3 | 1,278 (1,269-1,289) | 19.8 | 32.4 | 52.9 | 500 | 0 |  |
| root_p1 | loguru | sync | 1 | ok | 3/3 | 1,009 (999-1,021) | 31.1 | 39.6 | 71.3 | 500 | 0 |  |
| root_p4 | D-SafeLogger | sync | 4 | ok | 3/3 | 649 (645-652) | 20.8 | 47.0 | 108.2 | 500 | 0 |  |
| root_p4 | stdlib logging | sync | 4 | ok | 3/3 | 1,116 (1,089-1,145) | 20.9 | 42.3 | 117.5 | 500 | 0 |  |
| root_p4 | loguru | sync | 4 | ok | 3/3 | 821 (735-879) | 42.1 | 73.8 | 178.6 | 500 | 0 |  |
| root_p8 | D-SafeLogger | sync | 8 | ok | 3/3 | 470 (457-480) | 31.6 | 57.2 | 492.6 | 500 | 0 |  |
| root_p8 | stdlib logging | sync | 8 | ok | 3/3 | 859 (843-868) | 37.8 | 64.2 | 1109.8 | 500 | 0 |  |
| root_p8 | loguru | sync | 8 | ok | 3/3 | 674 (669-680) | 48.3 | 92.0 | 1213.4 | 500 | 0 |  |
| module_p4 | D-SafeLogger | sync | 4 | ok | 3/3 | 658 (642-670) | 20.6 | 39.0 | 111.2 | 500 | 0 |  |
| module_p4 | stdlib logging | sync | 4 | ok | 3/3 | 1,094 (1,043-1,126) | 21.9 | 50.9 | 158.6 | 500 | 0 |  |
| module_p4 | loguru | sync | 4 | ok | 3/3 | 869 (822-903) | 32.8 | 68.0 | 150.2 | 500 | 0 |  |

## Source

- Manifest key: `multiprocess_integrity`
- Selected session: `benchmarks_multi_integ_20260506_185947`
- Session artifacts: [`benchmarks/results/benchmarks_multi_integ_20260506_185947/summary.md`](../results/benchmarks_multi_integ_20260506_185947/summary.md), [`benchmarks/results/benchmarks_multi_integ_20260506_185947/summary.json`](../results/benchmarks_multi_integ_20260506_185947/summary.json)
