# EoT Model Comparison

## Pareto Frontier

![Pareto frontier](pareto_frontier.png)

## Best Cutoff Rate at Latency Budget

![Best cutoff rate at latency budgets](cutoff_rate_at_latency_budget_300_600ms.png)

| Model | Best cutoff rate @ 0.3s latency | Best cutoff rate @ 0.6s latency |
| --- | --- | --- |
| LiveKit Turn Detector v1.1 | **15.3%** | **5.1%** |
| Soniox | - | 6.0% |
| Gradium | 54.3% | 9.6% |
| LiveKit Turn Detector v1.1-mini | 21.5% | 8.0% |
| Deepgram Flux | 19.3% | 8.8% |
| SmartTurn v3.2 | 42.7% | 13.1% |
| ultraVAD | 42.8% | 14.5% |
| AssemblyAI | - | 13.1% |
| OpenAI GPT Realtime 2 | - | - |
| VAP (silent agent) | 55.3% | 17.8% |
| VAD baseline | 59.8% | 17.8% |

## Best Latency at Cutoff Budget

![Best latency at cutoff budgets](latency_at_cutoff_budget_5_10pct.png)

| Model | Best mean latency @ 5% cutoff | Best mean latency @ 10% cutoff |
| --- | --- | --- |
| LiveKit Turn Detector v1.1 | **618 ms** | **412 ms** |
| Soniox | 702 ms | 453 ms |
| Gradium | 728 ms | 596 ms |
| LiveKit Turn Detector v1.1-mini | 735 ms | 538 ms |
| Deepgram Flux | 766 ms | 571 ms |
| SmartTurn v3.2 | 836 ms | 668 ms |
| ultraVAD | 849 ms | 679 ms |
| AssemblyAI | 858 ms | 672 ms |
| OpenAI GPT Realtime 2 | 888 ms | 749 ms |
| VAP (silent agent) | 899 ms | 731 ms |
| VAD baseline | 1000 ms | 800 ms |

## Operating Points

| Type | Budget | Model | Mean Latency | Cutoff | Detect | Threshold | Action Delay | Timeout |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Cutoff | 5.0% | LiveKit Turn Detector v1.1 | 0.618 | 4.8% | 73.5% | 0.650 | 0.300 | 1.500 |
| Cutoff | 5.0% | Soniox | 0.702 | 4.9% | 80.2% | 0.990 | 0.500 | 1.500 |
| Cutoff | 5.0% | Gradium | 0.728 | 4.9% | 89.0% | 0.400 | 0.500 | 1.500 |
| Cutoff | 5.0% | LiveKit Turn Detector v1.1-mini | 0.735 | 4.9% | 85.0% | 0.500 | 0.600 | 1.500 |
| Cutoff | 5.0% | Deepgram Flux | 0.766 | 4.9% | 93.2% | 0.710 | 0.700 | 1.500 |
| Cutoff | 5.0% | SmartTurn v3.2 | 0.836 | 4.9% | 83.0% | 0.470 | 0.700 | 1.500 |
| Cutoff | 5.0% | ultraVAD | 0.849 | 4.9% | 50.2% | 0.440 | 0.700 | 1.000 |
| Cutoff | 5.0% | AssemblyAI | 0.858 | 4.9% | 49.0% | 0.950 | 0.700 | 1.000 |
| Cutoff | 5.0% | OpenAI GPT Realtime 2 | 0.888 | 4.6% | 88.8% | 0.990 | 0.800 | 1.500 |
| Cutoff | 5.0% | VAP (silent agent) | 0.899 | 4.6% | 59.2% | 0.100 | 0.800 | 1.000 |
| Cutoff | 10.0% | LiveKit Turn Detector v1.1 | 0.412 | 9.7% | 73.5% | 0.650 | 0.200 | 1.000 |
| Cutoff | 10.0% | Soniox | 0.453 | 9.0% | 80.2% | 0.990 | 0.200 | 1.000 |
| Cutoff | 10.0% | Gradium | 0.596 | 9.6% | 93.2% | 0.250 | 0.500 | 1.000 |
| Cutoff | 10.0% | LiveKit Turn Detector v1.1-mini | 0.538 | 9.7% | 57.8% | 0.700 | 0.200 | 1.000 |
| Cutoff | 10.0% | Deepgram Flux | 0.571 | 9.9% | 88.5% | 0.720 | 0.400 | 1.500 |
| Cutoff | 10.0% | SmartTurn v3.2 | 0.668 | 9.7% | 83.0% | 0.470 | 0.600 | 1.000 |
| Cutoff | 10.0% | ultraVAD | 0.679 | 9.7% | 80.2% | 0.240 | 0.600 | 1.000 |
| Cutoff | 10.0% | AssemblyAI | 0.672 | 9.7% | 70.8% | 0.840 | 0.500 | 1.000 |
| Cutoff | 10.0% | OpenAI GPT Realtime 2 | 0.749 | 9.1% | 88.8% | 0.990 | 0.600 | 1.500 |
| Cutoff | 10.0% | VAP (silent agent) | 0.731 | 9.7% | 98.0% | 0.030 | 0.700 | 1.500 |
| Latency | 300ms | LiveKit Turn Detector v1.1 | 0.298 | 15.3% | 87.8% | 0.410 | 0.200 | 1.000 |
| Latency | 300ms | Soniox | - | - | - | - | - | - |
| Latency | 300ms | Gradium | 0.263 | 54.3% | 98.8% | 0.010 | 0.200 | 1.000 |
| Latency | 300ms | LiveKit Turn Detector v1.1-mini | 0.300 | 21.5% | 87.5% | 0.450 | 0.200 | 1.000 |
| Latency | 300ms | Deepgram Flux | 0.296 | 19.3% | 98.8% | 0.570 | 0.200 | 1.500 |
| Latency | 300ms | SmartTurn v3.2 | 0.298 | 42.7% | 87.8% | 0.220 | 0.200 | 1.000 |
| Latency | 300ms | ultraVAD | 0.296 | 42.8% | 88.0% | 0.180 | 0.200 | 1.000 |
| Latency | 300ms | AssemblyAI | - | - | - | - | - | - |
| Latency | 300ms | OpenAI GPT Realtime 2 | - | - | - | - | - | - |
| Latency | 300ms | VAP (silent agent) | 0.266 | 55.3% | 99.0% | 0.020 | 0.200 | 1.000 |
| Latency | 600ms | LiveKit Turn Detector v1.1 | 0.586 | 5.1% | 51.7% | 0.860 | 0.200 | 1.000 |
| Latency | 600ms | Soniox | 0.579 | 6.0% | 80.2% | 0.990 | 0.300 | 1.500 |
| Latency | 600ms | Gradium | 0.596 | 9.6% | 93.2% | 0.250 | 0.500 | 1.000 |
| Latency | 600ms | LiveKit Turn Detector v1.1-mini | 0.582 | 8.0% | 52.2% | 0.730 | 0.200 | 1.000 |
| Latency | 600ms | Deepgram Flux | 0.598 | 8.8% | 93.2% | 0.710 | 0.500 | 1.500 |
| Latency | 600ms | SmartTurn v3.2 | 0.599 | 13.1% | 80.2% | 0.630 | 0.500 | 1.000 |
| Latency | 600ms | ultraVAD | 0.599 | 14.5% | 80.2% | 0.240 | 0.500 | 1.000 |
| Latency | 600ms | AssemblyAI | 0.596 | 13.1% | 75.8% | 0.790 | 0.400 | 1.000 |
| Latency | 600ms | OpenAI GPT Realtime 2 | - | - | - | - | - | - |
| Latency | 600ms | VAP (silent agent) | 0.600 | 17.8% | 100.0% | 0.000 | 0.600 | 1.000 |
