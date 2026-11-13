# EoT Model Comparison

## Pareto Frontier

![Pareto frontier](pareto_frontier.png)

## Best Cutoff Rate at Latency Budget

![Best cutoff rate at latency budgets](cutoff_rate_at_latency_budget_300_600ms.png)

| Model | Best cutoff rate @ 0.3s latency | Best cutoff rate @ 0.6s latency |
| --- | --- | --- |
| LiveKit Turn Detector v1.1 | **13.4%** | **7.5%** |
| p99lab turn-1 | 19.3% | 8.7% |
| Cartesia Ink 2 | - | - |
| JoinIn AI Baton | 26.1% | 13.6% |
| Gradium | 79.3% | 23.2% |
| LiveKit Turn Detector v1.1-mini | 25.6% | 12.9% |
| p99lab turn-1-mini | 39.6% | 18.7% |
| ultraVAD | 39.7% | 20.8% |
| AssemblyAI | - | 21.7% |
| SmartTurn v3.2 | 46.8% | 22.9% |
| Deepgram Flux | 22.3% | 13.5% |
| VAP (silent agent) | 63.5% | 29.0% |
| OpenAI GPT Realtime 2 | - | - |
| Soniox | - | 13.3% |
| VAD baseline | 79.3% | 33.4% |

## Best Latency at Cutoff Budget

![Best latency at cutoff budgets](latency_at_cutoff_budget_5_10pct.png)

| Model | Best mean latency @ 5% cutoff | Best mean latency @ 10% cutoff |
| --- | --- | --- |
| LiveKit Turn Detector v1.1 | **810 ms** | **414 ms** |
| p99lab turn-1 | 912 ms | 529 ms |
| Cartesia Ink 2 | 1027 ms | 968 ms |
| JoinIn AI Baton | 1111 ms | 749 ms |
| Gradium | 1112 ms | 785 ms |
| LiveKit Turn Detector v1.1-mini | 1124 ms | 738 ms |
| p99lab turn-1-mini | 1169 ms | 862 ms |
| ultraVAD | 1321 ms | 891 ms |
| AssemblyAI | 1381 ms | 906 ms |
| SmartTurn v3.2 | 1384 ms | 956 ms |
| Deepgram Flux | 1409 ms | 826 ms |
| VAP (silent agent) | 1724 ms | 1048 ms |
| OpenAI GPT Realtime 2 | 2000 ms | 959 ms |
| Soniox | 2000 ms | 789 ms |
| VAD baseline | 1600 ms | 1130 ms |

## Operating Points

| Type | Budget | Model | Mean Latency | Cutoff | Detect | Threshold | Action Delay | Timeout |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Cutoff | 5.0% | LiveKit Turn Detector v1.1 | 0.810 | 4.9% | 92.8% | 0.490 | 0.600 | 3.500 |
| Cutoff | 5.0% | p99lab turn-1 | 0.912 | 5.0% | 88.6% | 0.620 | 0.600 | 3.000 |
| Cutoff | 5.0% | Cartesia Ink 2 | 1.027 | 4.9% | 97.9% | 0.990 | 0.200 | 3.500 |
| Cutoff | 5.0% | JoinIn AI Baton | 1.111 | 5.0% | 90.0% | 0.560 | 0.900 | 3.000 |
| Cutoff | 5.0% | Gradium | 1.112 | 5.0% | 97.4% | 0.580 | 0.800 | 3.500 |
| Cutoff | 5.0% | LiveKit Turn Detector v1.1-mini | 1.124 | 5.0% | 67.4% | 0.730 | 0.700 | 2.000 |
| Cutoff | 5.0% | p99lab turn-1-mini | 1.169 | 4.8% | 73.9% | 0.540 | 0.700 | 2.000 |
| Cutoff | 5.0% | ultraVAD | 1.321 | 4.9% | 83.9% | 0.330 | 1.000 | 3.000 |
| Cutoff | 5.0% | AssemblyAI | 1.381 | 5.0% | 75.1% | 0.810 | 1.000 | 2.500 |
| Cutoff | 5.0% | SmartTurn v3.2 | 1.384 | 4.8% | 56.0% | 0.910 | 0.900 | 2.000 |
| Cutoff | 5.0% | Deepgram Flux | 1.409 | 4.9% | 40.0% | 0.790 | 0.500 | 2.000 |
| Cutoff | 5.0% | VAP (silent agent) | 1.724 | 5.0% | 30.6% | 0.290 | 1.000 | 2.000 |
| Cutoff | 5.0% | OpenAI GPT Realtime 2 | 2.000 | 2.9% | 0.0% | 1.000 | 0.200 | 2.000 |
| Cutoff | 5.0% | Soniox | 2.000 | 2.9% | 0.0% | 1.000 | 0.200 | 2.000 |
| Cutoff | 10.0% | LiveKit Turn Detector v1.1 | 0.414 | 9.9% | 88.1% | 0.640 | 0.200 | 2.000 |
| Cutoff | 10.0% | p99lab turn-1 | 0.529 | 9.7% | 87.7% | 0.630 | 0.200 | 2.000 |
| Cutoff | 10.0% | Cartesia Ink 2 | 0.968 | 7.7% | 95.4% | 0.990 | 0.200 | 1.500 |
| Cutoff | 10.0% | JoinIn AI Baton | 0.749 | 9.8% | 83.4% | 0.740 | 0.500 | 2.000 |
| Cutoff | 10.0% | Gradium | 0.785 | 10.0% | 99.2% | 0.390 | 0.600 | 2.500 |
| Cutoff | 10.0% | LiveKit Turn Detector v1.1-mini | 0.738 | 9.8% | 84.1% | 0.460 | 0.500 | 2.000 |
| Cutoff | 10.0% | p99lab turn-1-mini | 0.862 | 10.0% | 80.6% | 0.440 | 0.500 | 1.500 |
| Cutoff | 10.0% | ultraVAD | 0.891 | 9.9% | 94.7% | 0.150 | 0.800 | 2.500 |
| Cutoff | 10.0% | AssemblyAI | 0.906 | 9.9% | 93.2% | 0.260 | 0.800 | 2.000 |
| Cutoff | 10.0% | SmartTurn v3.2 | 0.956 | 9.8% | 87.0% | 0.130 | 0.800 | 2.000 |
| Cutoff | 10.0% | Deepgram Flux | 0.826 | 10.0% | 99.2% | 0.690 | 0.800 | 2.500 |
| Cutoff | 10.0% | VAP (silent agent) | 1.048 | 10.0% | 98.7% | 0.040 | 1.000 | 2.000 |
| Cutoff | 10.0% | OpenAI GPT Realtime 2 | 0.959 | 9.1% | 87.7% | 0.990 | 0.800 | 2.000 |
| Cutoff | 10.0% | Soniox | 0.789 | 9.5% | 94.2% | 0.990 | 0.600 | 2.500 |
| Latency | 300ms | LiveKit Turn Detector v1.1 | 0.295 | 13.4% | 94.7% | 0.400 | 0.200 | 2.000 |
| Latency | 300ms | p99lab turn-1 | 0.297 | 19.3% | 97.5% | 0.290 | 0.200 | 2.500 |
| Latency | 300ms | Cartesia Ink 2 | - | - | - | - | - | - |
| Latency | 300ms | JoinIn AI Baton | 0.300 | 26.1% | 87.6% | 0.640 | 0.200 | 1.000 |
| Latency | 300ms | Gradium | 0.300 | 79.3% | 100.0% | 0.000 | 0.300 | 1.000 |
| Latency | 300ms | LiveKit Turn Detector v1.1-mini | 0.298 | 25.6% | 92.5% | 0.300 | 0.200 | 1.500 |
| Latency | 300ms | p99lab turn-1-mini | 0.299 | 39.6% | 98.4% | 0.050 | 0.200 | 2.500 |
| Latency | 300ms | ultraVAD | 0.298 | 39.7% | 87.8% | 0.280 | 0.200 | 1.000 |
| Latency | 300ms | AssemblyAI | - | - | - | - | - | - |
| Latency | 300ms | SmartTurn v3.2 | 0.299 | 46.8% | 87.7% | 0.110 | 0.200 | 1.000 |
| Latency | 300ms | Deepgram Flux | 0.300 | 22.3% | 99.3% | 0.570 | 0.200 | 2.000 |
| Latency | 300ms | VAP (silent agent) | 0.291 | 63.5% | 99.9% | 0.020 | 0.200 | 2.000 |
| Latency | 300ms | OpenAI GPT Realtime 2 | - | - | - | - | - | - |
| Latency | 300ms | Soniox | - | - | - | - | - | - |
| Latency | 600ms | LiveKit Turn Detector v1.1 | 0.588 | 7.5% | 92.8% | 0.490 | 0.400 | 3.000 |
| Latency | 600ms | p99lab turn-1 | 0.591 | 8.7% | 87.7% | 0.630 | 0.200 | 2.500 |
| Latency | 600ms | Cartesia Ink 2 | - | - | - | - | - | - |
| Latency | 600ms | JoinIn AI Baton | 0.599 | 13.6% | 87.6% | 0.640 | 0.400 | 2.000 |
| Latency | 600ms | Gradium | 0.596 | 23.2% | 99.9% | 0.090 | 0.500 | 3.500 |
| Latency | 600ms | LiveKit Turn Detector v1.1-mini | 0.594 | 12.9% | 69.7% | 0.700 | 0.200 | 1.500 |
| Latency | 600ms | p99lab turn-1-mini | 0.593 | 18.7% | 86.9% | 0.290 | 0.200 | 1.500 |
| Latency | 600ms | ultraVAD | 0.593 | 20.8% | 90.7% | 0.230 | 0.500 | 1.500 |
| Latency | 600ms | AssemblyAI | 0.599 | 21.7% | 92.8% | 0.260 | 0.400 | 1.500 |
| Latency | 600ms | SmartTurn v3.2 | 0.599 | 22.9% | 80.1% | 0.340 | 0.500 | 1.000 |
| Latency | 600ms | Deepgram Flux | 0.559 | 13.5% | 99.4% | 0.700 | 0.500 | 3.500 |
| Latency | 600ms | VAP (silent agent) | 0.599 | 29.0% | 89.7% | 0.040 | 0.500 | 1.000 |
| Latency | 600ms | OpenAI GPT Realtime 2 | - | - | - | - | - | - |
| Latency | 600ms | Soniox | 0.597 | 13.3% | 94.2% | 0.990 | 0.200 | 2.500 |

## By Cohort

### `accented`

800 rows, 911 hold spans, 800 eot spans.

| Model | Best cutoff rate @ 0.3s latency | Best cutoff rate @ 0.6s latency | Best mean latency @ 5% cutoff | Best mean latency @ 10% cutoff |
| --- | --- | --- | --- | --- |
| LiveKit Turn Detector v1.1 | **12.4%** | **6.4%** | **700 ms** | **360 ms** |
| p99lab turn-1 | 19.1% | 8.5% | 878 ms | 520 ms |
| Cartesia Ink 2 | - | - | 980 ms | 964 ms |
| JoinIn AI Baton | 24.9% | 12.2% | 958 ms | 682 ms |
| Gradium | 89.5% | 23.4% | 941 ms | 737 ms |
| LiveKit Turn Detector v1.1-mini | 24.3% | 11.2% | 999 ms | 676 ms |
| p99lab turn-1-mini | 38.2% | 17.6% | 1027 ms | 817 ms |
| ultraVAD | 40.4% | 21.5% | 1165 ms | 904 ms |
| AssemblyAI | - | 22.8% | 1232 ms | 898 ms |
| SmartTurn v3.2 | 51.3% | 24.3% | 1224 ms | 945 ms |
| Deepgram Flux | 22.6% | 12.4% | 1084 ms | 734 ms |
| VAP (silent agent) | 68.5% | 33.0% | 1396 ms | 1011 ms |
| OpenAI GPT Realtime 2 | - | - | 1500 ms | 891 ms |
| Soniox | - | 12.5% | 1154 ms | 762 ms |
| VAD baseline | 89.5% | 37.3% | 1350 ms | 1060 ms |

### `general`

400 rows, 850 hold spans, 400 eot spans.

| Model | Best cutoff rate @ 0.3s latency | Best cutoff rate @ 0.6s latency | Best mean latency @ 5% cutoff | Best mean latency @ 10% cutoff |
| --- | --- | --- | --- | --- |
| LiveKit Turn Detector v1.1 | **7.8%** | **4.1%** | **462 ms** | **250 ms** |
| p99lab turn-1 | 10.6% | 4.5% | 553 ms | 321 ms |
| Cartesia Ink 2 | - | - | 1056 ms | 911 ms |
| JoinIn AI Baton | 12.3% | 4.8% | 577 ms | 350 ms |
| Gradium | 55.6% | 12.6% | 913 ms | 656 ms |
| LiveKit Turn Detector v1.1-mini | 17.7% | 8.2% | 812 ms | 504 ms |
| p99lab turn-1-mini | 22.6% | 9.6% | 849 ms | 580 ms |
| ultraVAD | 27.7% | 11.9% | 899 ms | 663 ms |
| AssemblyAI | 49.4% | 14.6% | 1049 ms | 713 ms |
| SmartTurn v3.2 | 35.2% | 14.8% | 1051 ms | 739 ms |
| Deepgram Flux | 12.9% | 9.9% | 1151 ms | 548 ms |
| VAP (silent agent) | 47.0% | 14.6% | 1131 ms | 749 ms |
| OpenAI GPT Realtime 2 | - | - | 1143 ms | 824 ms |
| Soniox | - | 5.5% | 647 ms | 512 ms |
| VAD baseline | 55.6% | 21.7% | 1600 ms | 1000 ms |

### `short_turns`

1088 rows, 544 hold spans, 544 eot spans.

| Model | Best cutoff rate @ 0.3s latency | Best cutoff rate @ 0.6s latency | Best mean latency @ 5% cutoff | Best mean latency @ 10% cutoff |
| --- | --- | --- | --- | --- |
| LiveKit Turn Detector v1.1 | **19.5%** | **10.8%** | **1096 ms** | **635 ms** |
| p99lab turn-1 | 28.3% | 13.2% | 1181 ms | 759 ms |
| Cartesia Ink 2 | - | - | 2500 ms | 979 ms |
| JoinIn AI Baton | 44.5% | 24.8% | 1689 ms | 1112 ms |
| Gradium | 90.6% | 35.7% | 1525 ms | 1017 ms |
| LiveKit Turn Detector v1.1-mini | 35.1% | 17.6% | 1237 ms | 893 ms |
| p99lab turn-1-mini | 60.7% | 26.5% | 1600 ms | 1098 ms |
| ultraVAD | 52.8% | 28.7% | 1876 ms | 1152 ms |
| AssemblyAI | - | 26.8% | 1918 ms | 1064 ms |
| SmartTurn v3.2 | 54.8% | 27.4% | 1761 ms | 1195 ms |
| Deepgram Flux | 33.3% | 20.0% | 1995 ms | 1167 ms |
| VAP (silent agent) | 78.7% | 39.3% | 2256 ms | 1403 ms |
| OpenAI GPT Realtime 2 | - | - | 2500 ms | 1500 ms |
| Soniox | - | 23.5% | 2500 ms | 1090 ms |
| VAD baseline | 92.8% | 42.1% | 2060 ms | 1450 ms |
