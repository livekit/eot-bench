# EoT Model Comparison

## Pareto Frontier

![Pareto frontier](pareto_frontier.png)

## Best Cutoff Rate at Latency Budget

![Best cutoff rate at latency budgets](cutoff_rate_at_latency_budget_300_600ms.png)

| Model | Best cutoff rate @ 0.3s latency | Best cutoff rate @ 0.6s latency |
| --- | --- | --- |
| LiveKit Turn Detector v1.1 | **10.9%** | **1.6%** |
| LiveKit Turn Detector v1.1-mini | 15.0% | 2.9% |
| Soniox | - | 3.4% |
| Deepgram Flux | 19.2% | 4.5% |
| ultraVAD | 39.1% | 6.5% |
| Gradium | 49.5% | 5.8% |
| SmartTurn v3.2 | 42.6% | 6.5% |
| OpenAI GPT Realtime 2 | - | - |
| VAP (silent agent) | 49.5% | 7.4% |
| VAD baseline | 49.5% | 7.4% |

## Best Latency at Cutoff Budget

![Best latency at cutoff budgets](latency_at_cutoff_budget_5_10pct.png)

| Model | Best mean latency @ 5% cutoff | Best mean latency @ 10% cutoff |
| --- | --- | --- |
| LiveKit Turn Detector v1.1 | **416 ms** | **320 ms** |
| LiveKit Turn Detector v1.1-mini | 490 ms | 344 ms |
| Soniox | 553 ms | 553 ms |
| Deepgram Flux | 583 ms | 459 ms |
| ultraVAD | 616 ms | 509 ms |
| Gradium | 618 ms | 530 ms |
| SmartTurn v3.2 | 639 ms | 532 ms |
| OpenAI GPT Realtime 2 | 641 ms | 641 ms |
| VAP (silent agent) | 655 ms | 539 ms |
| VAD baseline | 700 ms | 600 ms |

## Operating Points

| Type | Budget | Model | Mean Latency | Cutoff | Detect | Threshold | Action Delay | Timeout |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Cutoff | 5.0% | LiveKit Turn Detector v1.1 | 0.416 | 4.9% | 73.0% | 0.700 | 0.200 | 1.000 |
| Cutoff | 5.0% | LiveKit Turn Detector v1.1-mini | 0.490 | 4.9% | 85.0% | 0.540 | 0.400 | 1.000 |
| Cutoff | 5.0% | Soniox | 0.553 | 3.6% | 70.5% | 0.990 | 0.200 | 1.000 |
| Cutoff | 5.0% | Deepgram Flux | 0.583 | 4.9% | 87.5% | 0.610 | 0.400 | 1.000 |
| Cutoff | 5.0% | ultraVAD | 0.616 | 4.9% | 98.2% | 0.060 | 0.600 | 1.500 |
| Cutoff | 5.0% | Gradium | 0.618 | 4.7% | 91.2% | 0.190 | 0.500 | 1.000 |
| Cutoff | 5.0% | SmartTurn v3.2 | 0.639 | 4.7% | 90.2% | 0.040 | 0.600 | 1.000 |
| Cutoff | 5.0% | OpenAI GPT Realtime 2 | 0.641 | 4.9% | 89.8% | 0.990 | 0.200 | 1.000 |
| Cutoff | 5.0% | VAP (silent agent) | 0.655 | 4.9% | 80.5% | 0.080 | 0.500 | 1.000 |
| Cutoff | 10.0% | LiveKit Turn Detector v1.1 | 0.320 | 10.0% | 85.0% | 0.530 | 0.200 | 1.000 |
| Cutoff | 10.0% | LiveKit Turn Detector v1.1-mini | 0.344 | 10.0% | 82.0% | 0.570 | 0.200 | 1.000 |
| Cutoff | 10.0% | Soniox | 0.553 | 3.6% | 70.5% | 0.990 | 0.200 | 1.000 |
| Cutoff | 10.0% | Deepgram Flux | 0.459 | 9.6% | 92.5% | 0.470 | 0.200 | 1.000 |
| Cutoff | 10.0% | ultraVAD | 0.509 | 9.8% | 98.2% | 0.060 | 0.500 | 1.000 |
| Cutoff | 10.0% | Gradium | 0.530 | 9.8% | 95.5% | 0.120 | 0.400 | 1.000 |
| Cutoff | 10.0% | SmartTurn v3.2 | 0.532 | 9.2% | 93.5% | 0.020 | 0.500 | 1.000 |
| Cutoff | 10.0% | OpenAI GPT Realtime 2 | 0.641 | 4.9% | 89.8% | 0.990 | 0.200 | 1.000 |
| Cutoff | 10.0% | VAP (silent agent) | 0.539 | 9.2% | 96.0% | 0.030 | 0.500 | 1.000 |
| Latency | 300ms | LiveKit Turn Detector v1.1 | 0.296 | 10.9% | 88.0% | 0.450 | 0.200 | 1.000 |
| Latency | 300ms | LiveKit Turn Detector v1.1-mini | 0.298 | 15.0% | 87.8% | 0.500 | 0.200 | 1.000 |
| Latency | 300ms | Soniox | - | - | - | - | - | - |
| Latency | 300ms | Deepgram Flux | 0.294 | 19.2% | 97.8% | 0.240 | 0.200 | 1.000 |
| Latency | 300ms | ultraVAD | 0.298 | 39.1% | 87.8% | 0.170 | 0.200 | 1.000 |
| Latency | 300ms | Gradium | 0.300 | 49.5% | 100.0% | 0.000 | 0.300 | 1.000 |
| Latency | 300ms | SmartTurn v3.2 | 0.294 | 42.6% | 88.2% | 0.050 | 0.200 | 1.000 |
| Latency | 300ms | OpenAI GPT Realtime 2 | - | - | - | - | - | - |
| Latency | 300ms | VAP (silent agent) | 0.300 | 49.5% | 100.0% | 0.000 | 0.300 | 1.000 |
| Latency | 600ms | LiveKit Turn Detector v1.1 | 0.596 | 1.6% | 57.8% | 0.850 | 0.300 | 1.000 |
| Latency | 600ms | LiveKit Turn Detector v1.1-mini | 0.590 | 2.9% | 82.0% | 0.570 | 0.500 | 1.000 |
| Latency | 600ms | Soniox | 0.570 | 3.4% | 70.5% | 0.990 | 0.300 | 1.000 |
| Latency | 600ms | Deepgram Flux | 0.598 | 4.5% | 89.5% | 0.550 | 0.500 | 1.000 |
| Latency | 600ms | ultraVAD | 0.590 | 6.5% | 91.0% | 0.130 | 0.500 | 1.500 |
| Latency | 600ms | Gradium | 0.586 | 5.8% | 93.8% | 0.150 | 0.500 | 1.000 |
| Latency | 600ms | SmartTurn v3.2 | 0.589 | 6.5% | 82.2% | 0.110 | 0.500 | 1.000 |
| Latency | 600ms | OpenAI GPT Realtime 2 | - | - | - | - | - | - |
| Latency | 600ms | VAP (silent agent) | 0.579 | 7.4% | 90.8% | 0.050 | 0.500 | 1.000 |
